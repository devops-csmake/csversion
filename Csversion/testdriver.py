#!/usr/bin/env python3
# Run as: python3 -m Csversion.testdriver (from the repo root), since this
# module is part of the Csversion package and uses package-relative imports.
from . import CliDriver

class MyCli(CliDriver.CliDriver):
    DEFAULT_CONFIG_LONG_HELP_KEY = 'long-help'
    DEFAULT_CONFIG_SYNONYMS = { 'xyzzt' : 'help' }
    #DEFAULT_CONFIG_HELP_KEY = None

MyCli(name="test",version="11.1.1.9").main()

