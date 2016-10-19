#!/usr/bin/python
# vim: set fileencoding=utf-8 ts=2 sw=2 expandtab :

import os
import sys
from optparse import OptionParser, make_option
from urlparse import urlparse
from syslog import *
from pyinotify import *
from time import sleep
import threading
import Queue
import datetime
from configparser import ConfigParser

__author__ = "Benedikt Böhm"
__copyright__ = "Copyright (c) 2007-2008 Benedikt Böhm <bb@xnull.de>"
__version__ = 0, 2, 3

OPTION_LIST = [
    make_option(
        "-c", dest="config",
        default="/etc/inosync/default.py",
        metavar="FILE",
        help="load configuration from FILE"),
    make_option(
        "-d", dest="daemonize",
        action="store_true",
        default=False,
        help="daemonize %prog"),
    make_option(
        "-p", dest="pretend",
        action="store_true",
        default=False,
        help="do not actually call rsync"),
    make_option(
        "-v", dest="verbose",
        action="store_true",
        default=False,
        help="print debugging information"),
]

DEFAULT_EVENTS = [
    "IN_CLOSE_WRITE",
    "IN_CREATE",
    "IN_DELETE",
    "IN_MOVED_FROM",
    "IN_MOVED_TO"
]

changed_paths = Queue.Queue()

def purge(directory):
    """
    Purge all old inosync temp files.
    Cool thing is if rsync is still running it can still read the file.
    """
    for f in os.listdir(directory):
        if "inosync_" in f:
            os.remove(os.path.join(directory, f))


def sync_changes(pretend, sleep_time):
    """
    Main sync changes threads, that over a given time period processes a batch
    of changed files.
    """
    global config

    while True:
        # remove old changed files.
        purge("/tmp/")

        q_len = changed_paths.qsize()
        wpath_path_map = {}
        if q_len > 0:
            syslog(LOG_DEBUG, "There have been changes.")
            file_list = []
            for i in range(0, q_len):
                item = changed_paths.get()
                if item not in file_list:
                    file_list.append(item)
            syslog(LOG_DEBUG, str(file_list))

            # seperate rsync should occur for each wpath.
            for wpath in config.wpaths:
                while len(file_list) > 0:
                    _filepath = file_list.pop()
                    r_path = wpath if wpath[len(wpath) - 1] == "/" else wpath + "/"
                    if r_path in _filepath:
                        wpath_path_map[wpath] = set()
                    _filepath = _filepath.replace(r_path, '')
                    if len(_filepath) == 0:
                        _filepath = "./"
                    wpath_path_map[wpath].update([_filepath])

            syslog(LOG_DEBUG, str(wpath_path_map))

            for wpath, paths in wpath_path_map.items():
                sync_filepath = "/tmp/inosync_%s" % (datetime.datetime.now().strftime('%H-%M-%s'))

                with open(sync_filepath, "w") as f:
                    f.write("\n".join(paths))
                r_sync(pretend=pretend, wpath=wpath, from_file=sync_filepath)
        else:
            syslog(LOG_DEBUG, "Nothing to sync.")

        sleep(sleep_time)


def uri_parse(url):
    """
    Getting str URI in format 'schema://username:password@host:port/path/name'
    and returning dict with parsed values
    """
    uri = {}
    conn = urlparse(url)
    uri['port'] = conn.port
    uri['scheme'] = conn.scheme
    uri['hostname'] = conn.hostname
    uri['username'] = conn.username
    uri['password'] = conn.password
    uri['path'] = conn.path
    if conn.scheme == 'ssh':
        uri['port'] = conn.port if conn.port else 22
    if conn.scheme == 'ftp':
        uri['port'] = conn.port if conn.port else 21
    return uri


def r_sync(pretend, wpath, from_file=None, delete_from_file=False):
    for node in config.rnodes:
        uri = uri_parse(node)
        args = [config.rsync, "-avz", "--delete"]
        if uri['scheme'] == 'ssh':
            args.append('-e "ssh -p {} -T -o Compression=no -x"'.format(uri['port']))
            rpath = config.rpaths[config.wpaths.index(wpath)]
            rhost = (str(uri['username'] + '@' + str(uri['hostname']) + ':' + rpath))
        if config.extra:
            args.append(config.extra)
        args.append("--bwlimit=%s" % config.rspeed)
        if config.logfile:
            args.append("--log-file=%s" % config.logfile)
        if "rexcludes" in dir(config):
            for rexclude in config.rexcludes:
                args.append("--exclude=%s" % rexclude)
        if from_file is not None:
            args.append("--files-from=%s" % from_file)
        args.append(wpath)
        args.append(rhost)
        cmd = " ".join(args)
        if pretend:
            syslog("would execute `%s'" % (cmd))
        else:
            syslog(LOG_DEBUG, "executing %s" % (cmd))
            proc = os.popen(cmd)
            for line in proc:
                syslog(LOG_DEBUG, "[rsync] %s" % line.strip())


class RsyncEvent(ProcessEvent):
    pretend = None

    def sync(self, wpath):
        r_sync(self.pretend, wpath)

    def __init__(self, pretend=False):
        self.pretend = pretend

    def process_default(self, event):
        syslog(LOG_DEBUG, "caught %s on %s" %
               (event.maskname, os.path.join(event.path, event.name)))
        for wpath in config.wpaths:
            if os.path.realpath(wpath) in os.path.realpath(event.path):
                path_str = str(os.path.realpath(event.path)) + os.sep
                changed_paths.put(path_str)
                #changed_paths.put(os.path.join(path_str, event.name))


def daemonize():
    try:
        pid = os.fork()
    except OSError, e:
        raise Exception("%s [%d]" % (e.strerror, e.errno))

    if pid == 0:
        os.setsid()
        try:
            pid = os.fork()
        except OSError, e:
            raise Exception("%s [%d]" % (e.strerror, e.errno))
        if (pid == 0):
            os.chdir('/')
            os.umask(0)
        else:
            os._exit(0)
    else:
        os._exit(0)

    os.open("/dev/null", os.O_RDWR)
    os.dup2(0, 1)
    os.dup2(0, 2)

    return 0


def load_config(filename):
    if not os.path.isfile(filename):
        raise RuntimeError("Configuration file does not exist: %s" % filename)

    configdir = os.path.dirname(filename)
    configfile = os.path.basename(filename)

    if configfile.endswith(".py"):
        configfile = configfile[0:-3]
    else:
        raise RuntimeError("Configuration file must be a importable python file ending in .py")

    sys.path.append(configdir)
    exec ("import %s as __config__" % configfile)
    sys.path.remove(configdir)

    global config
    config = __config__

    if "wpaths" not in dir(config):
        raise RuntimeError("No paths given to watch")
    for wpath in config.wpaths:
        if not os.path.isdir(wpath):
            raise RuntimeError("One of the watch paths does not exist: %s" % wpath)
        if not os.path.isabs(wpath):
            config.wpaths[config.wpaths.index(wpath)] = os.path.abspath(wpath)

    for owpath in config.wpaths:
        for wpath in config.wpaths:
            if os.path.realpath(owpath) in os.path.realpath(wpath) and wpath != owpath and len(
                    os.path.split(wpath)) != len(os.path.split(owpath)):
                raise RuntimeError(
                    "You cannot specify %s in wpaths which is a subdirectory of %s since it is already synced." % (
                    wpath, owpath))

    if "rpaths" not in dir(config):
        raise RuntimeError("No paths given for the transfer")
    if len(config.wpaths) != len(config.rpaths):
        raise RuntimeError("The no. of remote paths must be equal to the number of watched paths")

    if "rnodes" not in dir(config) or len(config.rnodes) < 1:
        raise RuntimeError("No remote nodes given")

    if "rspeed" not in dir(config) or config.rspeed < 0:
        config.rspeed = 0

    if "inotify_excludes" not in dir(config):
        config.inotify_excludes = []

    if "emask" not in dir(config):
        config.emask = DEFAULT_EVENTS
    for event in config.emask:
        if event not in EventsCodes.ALL_FLAGS.keys():
            raise RuntimeError("Invalid inotify event: %s" % event)

    if "edelay" not in dir(config):
        config.edelay = 10
    if config.edelay < 0:
        raise RuntimeError("Event delay needs to be greater or equal to 0")

    if "logfile" not in dir(config):
        config.logfile = None

    if "extra" not in dir(config):
        config.extra = ""
    if "extra" not in dir(config):
        config.inotify_excludes = []
    if "sleep_time" not in dir(config):
        config.sleep_time = 10
    if "rsync" not in dir(config):
        config.rsync = "/usr/bin/rsync"
    if not os.path.isabs(config.rsync):
        raise RuntimeError("rsync path needs to be absolute")
    if not os.path.isfile(config.rsync):
        raise RuntimeError("rsync binary does not exist: %s" % config.rsync)


class StringExclusionFilter:
    def __init__(self, paths):
        assert (isinstance(paths, list))
        self.paths = paths

    def __call__(self, watch_path):
        for _path in self.paths:
            if _path in watch_path:
                return True
        return False


def main():
    version = ".".join(map(str, __version__))
    parser = OptionParser(option_list=OPTION_LIST, version="%prog " + version)
    (options, args) = parser.parse_args()

    if len(args) > 0:
        parser.error("too many arguments")

    logopt = LOG_PID | LOG_CONS
    if not options.daemonize:
        logopt |= LOG_PERROR
    openlog("inosync", logopt, LOG_DAEMON)
    if options.verbose:
        setlogmask(LOG_UPTO(LOG_DEBUG))
    else:
        setlogmask(LOG_UPTO(LOG_INFO))

    load_config(options.config)

    if options.daemonize:
        daemonize()

    wm = WatchManager()
    ev = RsyncEvent(options.pretend)
    AsyncNotifier(wm, ev, read_freq=config.edelay)
    mask = reduce(lambda x, y: x | y, [EventsCodes.ALL_FLAGS[e] for e in config.emask])
    print("Excluding: %s " % (str(config.inotify_excludes)))
    wm.add_watch(
        config.wpaths,
        mask,
        rec=True,
        auto_add=True,
        exclude_filter=StringExclusionFilter(config.inotify_excludes)
    )
    for wpath in config.wpaths:
        syslog(LOG_DEBUG, "starting initial synchronization on %s" % wpath)
        ev.sync(wpath)
        syslog(LOG_DEBUG, "initial synchronization on %s done" % wpath)
        syslog("resuming normal operations on %s" % wpath)

    write_out_thread = threading.Thread(target=sync_changes, args=(options.pretend, config.sleep_time,))
    write_out_thread.daemon = True
    write_out_thread.start()

    asyncore.loop()
    sys.exit(0)


if __name__ == "__main__":
    main()
