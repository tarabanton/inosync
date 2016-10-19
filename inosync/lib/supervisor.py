# -*- coding: utf-8 -*-
import logging
from time import sleep

class Supervisor(object):

    Running = True

    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger(
            self.__class__.__name__.upper())

    def start(self):
        while self.Running:
            sleep(60)
            self.log.info("Running")
