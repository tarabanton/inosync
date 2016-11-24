# -*- coding: utf-8 -*-
import os
import logging
import sys

try:
    import ConfigParser as configparser
except:
    import configparser

class DefaultConfig():

    @staticmethod
    def default_config_path():
        return '/etc/inosync/inosync.conf'

    @staticmethod
    def get_logger_level(level):
        result = logging.INFO
        level = level.upper()
        if level == 'DEBUG':
            return logging.DEBUG
        if level == 'WARNING' or level == 'WARN':
            return logging.WARN
        return result


class Config(DefaultConfig):

    def __init__(self, cfg_file=None):

        config = configparser.ConfigParser(defaults={
            'parameters': '',
            'rsync_path': '/usr/bin/rsync',
            'rsync_include': '',
            'rsync_exclude': '',
            'inotify_events': 'IN_CLOSE_WRITE,IN_CREATE,IN_DELETE,IN_MOVED_FROM,IN_MOVED_TO',
            'inotify_exclude': '',
            'inotify_delay': '10',
        })

        config.add_section('inosync')
        config.set('inosync', 'dry-run', str(False))

        config.add_section('log')
        config.set('log', 'file', str(None))
        config.set('log', 'level', 'INFO')
        config.set('log', 'format',
                    '[%(levelname)s] %(asctime)s - %(name)s\t-\t%(message)s')

        self.config = config

        if cfg_file and not os.path.isfile(cfg_file):
            sys.stderr.write('Can\'t found file: {0}'.format(cfg_file))
            sys.exit(1)
        else:
            if cfg_file is not None:
                self.config.read(cfg_file)

        #self.apply_log_setting()

    def fetch(self, sec, key, klass=None, raw=False):
        try:
            if klass == float:
                return self.config.getfloat(sec, key)
            if klass == int:
                return self.config.getint(sec, key)
            if klass == bool:
                return self.config.getboolean(sec, key)
            if self.config.get(sec, key, raw=raw) == 'None':
                return None
            return self.config.get(sec, key, raw=raw)
        except KeyError:
            return None

    def deliver(self, sec, key, value):
        self.config.set(sec, key, value)

    def fetch_sections(self, raw=False):
        try:
            return self.config.sections()
        except:
            return None

    def fetch_items(self, sec, raw=False):
        try:
            return self.config.items(sec)
        except configparser.NoSectionError:
            return None

    def apply_log_setting(self):
        logging.basicConfig(
            format=self.fetch('log', 'format', raw=True),
            filename=self.fetch('log', 'file'),
            level=self.get_logger_level(self.fetch('log', 'level')))
