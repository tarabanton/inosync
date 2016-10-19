# -*- coding: utf-8 -*-
import sys
from inosync import __version__
from optparse import OptionParser, BadOptionError

usage_msg = """
Options:
    -c, --config       <file>
    -p, --pid          <pid-file>
    -d                 daemonize
    -t, --dry-run      dry-run, pretend to run sync
    -v                 print debugging information
"""
def print_total_help():
    print(usage_msg.format(prog=sys.argv[0]))
    sys.exit(2)

class MissOptsParser(OptionParser):
    def print_help(self):
        print(usage_msg.format(prog=sys.argv[0]))
        sys.exit(2)

    def _process_long_opt(self, rargs, values):
        try:
            OptionParser._process_long_opt(self, rargs, values)
        except BadOptionError as err:
            self.largs.append(err.opt_str)

    def _process_short_opts(self, rargs, values):
        try:
            OptionParser._process_short_opts(self, rargs, values)
        except BadOptionError as err:
            self.largs.append(err.opt_str)


def parse_args():
    parser = MissOptsParser(
        usage=usage_msg,
        version='%prog {0}'.format(__version__))
    parser.add_option(
        '-c', '--config', dest='config_file', default=None)
    # pid
    parser.add_option(
        '-p', '--pid', dest='pid', default=None)
    # daemonize
    parser.add_option(
        '-d', '--daemon', dest='daemon', action='store_true')
    # dry run, just print info
    parser.add_option(
        '-t', '--dry-run', dest='dry_run', action='store_true')
    # enable debug
    parser.add_option(
        '-v', '--verbose', dest='verbose', action='store_true')
    return parser.parse_args()
