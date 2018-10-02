#!/usr/bin/python
import CliDriver

class MyCli(CliDriver.CliDriver):
    DEFAULT_CONFIG_LONG_HELP_KEY = 'long-help'
    DEFAULT_CONFIG_SYNONYMS = { 'xyzzt' : 'help' }
    #DEFAULT_CONFIG_HELP_KEY = None

MyCli(name="test",version="11.1.1.9").main()

