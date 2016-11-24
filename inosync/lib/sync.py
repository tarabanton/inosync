# -*- coding: utf-8 -*-

import sys
import os
import logging
from threading import Thread
from urlparse import urlparse
from pyinotify import *
import Queue
from time import sleep

changed_paths = Queue.Queue()

class RsyncEvent(ProcessEvent):

    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger(
            self.__class__.__name__.upper())
        self.pretend = config.fetch('inosync', 'dry-run')

    def sync(self, wpath):
        Sync.sync_do(self.pretend, wpath)

    def process_default(self, event):
        self.log.debug("Caught {} on {}".format(event.maskname, os.path.join(event.path, event.name)))
        for wpath in config.wpaths:
            if os.path.realpath(wpath) in os.path.realpath(event.path):
                path_str = str(os.path.realpath(event.path)) + os.sep
                changed_paths.put(path_str)
                #changed_paths.put(os.path.join(path_str, event.name))

class Sync():
    Interval = 10

    def __init__(self, config, sync):
        self.config = config
        self.log = logging.getLogger(
            self.__class__.__name__.upper())
        self.pretend = config.fetch('inosync', 'dry-run')
        self.wpath = self.config(sync, 'source')
        self.target = []
        for k, v in self.config.fetch_items(sync):
            if 'target' in k:
                self.target.append(v)
        self.config.fetch(sync,'parameters')

    def cleanup(self, directory):
        """
        Purge all old inosync temp files.
        Cool thing is if rsync is still running it can still read the file.
        """
        for f in os.listdir(directory):
            if "inosync_" in f:
                os.remove(os.path.join(directory, f))

    def uri_parse(self, url):
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

    def sync_prepare(self, pretend):
        """
        Main sync changes threads, that over a given time period processes a batch
        of changed files.
        """
        # remove old changed files.
        self.cleanup("/tmp/")

        q_len = changed_paths.qsize()
        wpath_path_map = {}
        if q_len > 0:
            self.log.debug("There have been {} changes.".format(q_len))
            file_list = []
            for i in range(0, q_len):
                item = changed_paths.get()
                if item not in file_list:
                    file_list.append(item)
            self.log.debug(str(file_list))

            # separate rsync should occur for each wpath.
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

            self.log.debug(str(wpath_path_map))

            for wpath, paths in wpath_path_map.items():
                sync_filepath = "/tmp/inosync_%s" % (datetime.datetime.now().strftime('%H-%M-%s'))

                with open(sync_filepath, "w") as f:
                    f.write("\n".join(paths))
                self.sync_do(pretend=pretend, wpath=wpath, from_file=sync_filepath)
        else:
            self.log.debug("Nothing to sync.")

    def sync_do(self, wpath, pretend=False, from_file=None, delete_from_file=False):
        for node in config.rnodes:
            uri = self.uri_parse(node)
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
                self.log.debug("would execute '{}'".format(cmd))
            else:
                self.log.debug("executing {}".format(cmd))
                proc = os.popen(cmd)
                for line in proc:
                    self.log.debug("[rsync] %s".format(line.strip()))

    def start(self):
        self._thread = Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()

    def is_alive(self):
        if self._thread is not None:
            return self._thread.is_alive()
        return False

    def run(self):
        self.sync_prepare()

    def _log_exception(self, e, trace):
        name = e.__class__.__name__
        self.last_error_text = 'Sync exception [{0}]: {1}.'.format(name, e)
        self.log.error(self.last_error_text)
        self.log.debug(trace)

    def _loop(self):
        while (True):
            last_start = time.time()
            try:
                self.run()
            except Exception as e:
                trace = traceback.format_exc()
                self._log_exception(e, trace)
                return
            sleep_time = self.Interval - int(time.time() - last_start)
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                self.log.error(
                    'Timeout: {0}s'.format(int(time.time() - last_start)))
                return
