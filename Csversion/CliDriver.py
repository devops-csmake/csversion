# <copyright>
# (c) Copyright 2018 Cardinal Peak Technologies
# (c) Copyright 2017 Hewlett Packard Enterprise Development LP
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# </copyright>

import ConfigParser
import getopt
import logging
import os
import os.path
import re
import sys
import xml.sax.saxutils
import json
import yaml

from os import environ
from Settings import Setting
from Settings import Settings
from sys import stderr
from sys import stdout

class CliDriver(object):

    #=====================================================
    # Defaults
    #=====================================================
    #Set this if you have an underlying version number to expose that
    #is separate from the tool's version
    _LIBRARY_VERSION = None

    #Put a list of desired config paths in the subclass
    #Process them in __init__ if necessary before calling super's __init__
    DEFAULT_CONFIG_PATHS = []

    #Command line usage default: %s is required and is the name of the
    #                            program
    DEFAULT_COMMAND_LINE_USAGE = "     %s [OPTIONS]"
    
    #Input command values to redact (re list)
    DEFAULT_CONFIG_KEY_REDACT_VALUE_REGEX = []

    #============================================================
    # Default settings
    #============================================================
    # These are the default settings options
    # Any option's keys and settings entry can be overridden
    #   if the option is not desired in the subclass, set the KEY to
    #   none.

    #----------- synonym list --------------------
    #Allow synonyms for settings.
    #Format is { <synonym> : <actual option> }
    #  NOTE: Don't put '--' in front.
    #        Synonyms are for main settings keys only, not group keys
    DEFAULT_CONFIG_SYNONYMS = {}

    #----------- configuration setting defaults ---------------
    #This key will be added to settings if it is not otherwise defined
    #in the settings.  This key needs to be the key used for adding
    #configuration files.
    #Set DEFAULT_CONFIG_PATHS to None if you need to turn this completely off
    DEFAULT_CONFIG_FILE_KEY = 'configuration'

    #These will be filled out in __init__
    DEFAULT_CONFIG_FILE_ENTRY = [
        None,
        """Specifies one or more configuration files (comma separated)
           to read from.  Configurations are ini files where the options
           are the command-line flags and the values are the desired defaults.
           All definitions go under the section 'settings', e.g.:
           [settings]
           mysetting=setting_value,other_setting_value

           The order of processing is:
               %(files)sConfiguration files specified by the '%(key)s' flag in order

           NOTE: Configuration files change command-line behavior""",
        False,
        "Specifies configuration file(s) to use"]

    DEFAULT_CONFIG_FILE_ENTRY_DICTIONARY = {
        'files' : None,
        'key' : None }

    #--------- version setting defaults ----------
    DEFAULT_CONFIG_VERSION_KEY = 'version'

    DEFAULT_CONFIG_VERSION_ENTRY = [
        None,
        """Shows version of program and exits""",
        True ]

    #---------- settings setting defaults ---------
    DEFAULT_CONFIG_SETTINGS_KEY = 'settings'

    DEFAULT_CONFIG_SETTINGS_ENTRY = [
        None,
        """JSON specification of settings to allow settings to be conveyed
           via a single string.  These settings will override all other 
           settings.  Example: --settings={"setting" : "mysetting"}""",
        False,
        "JSON specification of settings" ]

    #---------- help-long setting defaults --------
    DEFAULT_CONFIG_LONG_HELP_KEY = 'help-long'

    DEFAULT_CONFIG_LONG_HELP_ENTRY = [
        False,
        """Displays the long help text and usage""",
        True ]

    #---------- help setting defaults -------------
    DEFAULT_CONFIG_HELP_KEY = 'help'

    DEFAULT_CONFIG_HELP_ENTRY = [
        False,
        """Displays the short help text and usage""",
        True ]

    #------------ log setting defaults -------------
    DEFAULT_CONFIG_LOG_KEY = 'log'

    DEFAULT_CONFIG_LOG_ENTRY = [
        None,
        """Sends all logging to specified file, Default: stdout""",
        False ]

    #---------- quiet setting defaults -------------
    DEFAULT_CONFIG_QUIET_KEY = 'quiet'

    DEFAULT_CONFIG_QUIET_ENTRY = [
        False,
        """Suppress all logging output""",
        True ]

    #---------- verbose setting defaults -----------
    DEFAULT_CONFIG_VERBOSE_KEY = 'verbose'

    DEFAULT_CONFIG_VERBOSE_ENTRY = [
        False,
        """Turn on verbose output""",
        True ]

    #---------- debug setting defaults -------------
    DEFAULT_CONFIG_DEBUG_KEY = 'debug'

    DEFAULT_CONFIG_DEBUG_ENTRY = [
        False,
        """Turn on debugging output""",
        True ]

    #------------------------------------------
    # Settings functions
    def _setupDefaultConfigFileEntries(self, settings):
        #Filling out class "constants"
        #Assumes we're really doing configfiles as a precondition
        self.DEFAULT_CONFIG_FILE_ENTRY_DICTIONARY['files'] = '\n    '.join(
            self.DEFAULT_CONFIG_PATHS )
        if len(self.DEFAULT_CONFIG_FILE_ENTRY_DICTIONARY['files']) != 0:
            self.DEFAULT_CONFIG_FILE_ENTRY_DICTIONARY['files'] += "\n    "
        self.DEFAULT_CONFIG_FILE_ENTRY_DICTIONARY['key'] = self.DEFAULT_CONFIG_FILE_KEY

    def _setupDefaultSettingsList(self):
        defaultList = [
            (self.DEFAULT_CONFIG_SETTINGS_KEY,
                 self.DEFAULT_CONFIG_SETTINGS_ENTRY,
                 None),
            (self.DEFAULT_CONFIG_LONG_HELP_KEY,
                 self.DEFAULT_CONFIG_LONG_HELP_ENTRY,
                 None),
            (self.DEFAULT_CONFIG_HELP_KEY,
                 self.DEFAULT_CONFIG_HELP_ENTRY,
                 None),
            (self.DEFAULT_CONFIG_LOG_KEY,
                 self.DEFAULT_CONFIG_LOG_ENTRY,
                 None),
            (self.DEFAULT_CONFIG_VERBOSE_KEY,
                 self.DEFAULT_CONFIG_VERBOSE_ENTRY,
                 None),
            (self.DEFAULT_CONFIG_DEBUG_KEY,
                 self.DEFAULT_CONFIG_DEBUG_ENTRY,
                 None),
            (self.DEFAULT_CONFIG_QUIET_KEY,
                 self.DEFAULT_CONFIG_QUIET_ENTRY,
                 None),
            (self.DEFAULT_CONFIG_VERSION_KEY,
                 self.DEFAULT_CONFIG_VERSION_ENTRY,
                 None)
        ]
        if self.DEFAULT_CONFIG_PATHS is not None:
            defaultList.append(
                (self.DEFAULT_CONFIG_FILE_KEY,
                     self.DEFAULT_CONFIG_FILE_ENTRY,
                     self.DEFAULT_CONFIG_FILE_ENTRY_DICTIONARY))
        return defaultList


    def _setupDefaultSettings(self, settings, defaultSettings=[]):
        for key, entry, dictionary in defaultSettings:
            if key is None:
                continue
            if key not in settings:
                if dictionary is not None:
                    entry[1] = entry[1] % dictionary
                settings[key] = entry
                
    #======================================================
    # Settings processing
    #======================================================
    def _getOptions(self):
        self._getFileOptions(self.DEFAULT_CONFIG_PATHS)
        self._getCommandLineOptions()
        if self.DEFAULT_CONFIG_FILE_KEY is not None:
            configFile = self.settings[self.DEFAULT_CONFIG_FILE_KEY]
            if configFile is not None:
                if self._getFileOptions(configFile.split(':')):
                    #We successfully loaded a user specified config file
                    #  The command line takes precedence, so reload it.
                    self._getCommandLineOptions()
        self._processSettingsOptions()

    def _processSettingsOptions(self):
        if self.DEFAULT_CONFIG_SETTINGS_KEY is None:
            return
        if self.settings[self.DEFAULT_CONFIG_SETTINGS_KEY] is None:
            return
        for (key, value) in json.loads(self.settings[self.DEFAULT_CONFIG_SETTINGS_KEY]).items():
            if isinstance(value, dict):
                self.settings[key] = value
                for subkey in value.keys():
                    self.settings[key][subkey] = Setting(
                        "%s:%s" % (
                            key,
                            subkey ),
                        value[subkey], "", False )
            else:
                self.settings[key] = value

    def _getFileOptions(self, filenames):
        parser = ConfigParser.RawConfigParser()
        parser.read(filenames)
        try:
            sections = parser.sections()
            for section in sections:
                params = parser.items(section)
                for option, arg in params:
                    if section == self.DEFAULT_CONFIG_SETTINGS_KEY:
                        if option in self.settings.keys():
                            if self.settings.getObject(option).isFlag:
                                self.settings[option] = True
                            else:
                                self.settings[option] = arg.strip()
                        else:
                            stderr.write(
                                "WARNING: option '%s' not found (FILE)" % option)
                    else:
                        if section not in self.settings.keys():
                            self.settings[section] = {}
                        if option not in self.settings[section]:
                            self.settings[section][option] = Setting(
                                "%s:%s" % (
                                    section,
                                    option ),
                                None, "", False )
                        if self.settings[section][option].isFlag:
                            self.settings[section][option].value = True
                        else:
                            self.settings[section][option].value = arg.strip()
        except:
            #If there's problems, just move along
            self.log.info("Config files may not be loaded")
            pass

    def _getSettingsOptions(self):
        result = []
        for key in self.settings.keys():
            option = key
            if isinstance(self.settings[key], dict):
                for subkey in self.settings[key].keys():
                    entry = option + ":" + subkey
                    if not self.settings[key][subkey].isFlag:
                        entry = entry + "="
                    result.append(entry)
            else:
                if not self.settings.getObject(key).isFlag:
                    option = option + "="
                result.append(option)
        return result

    def _injectSynonyms(self, longOptions):
        result = list(longOptions)
        for synonym, orig  in self.DEFAULT_CONFIG_SYNONYMS.iteritems():
            if orig + '=' in longOptions:
                synonym = synonym + '='
            result.append(synonym)
        return result

    def _handleSynonyms(self, options):
        #This maps any synonyms into the original options
        addins = {}
        for option, arg in options:
            strippedOption = option.lstrip('-')
            if strippedOption in self.DEFAULT_CONFIG_SYNONYMS:
                addins['--'+self.DEFAULT_CONFIG_SYNONYMS[strippedOption]] = arg
            else:
                addins[option] = arg
        options = [ (option,addins[option]) for option in addins.keys() ]
        return options

    def _getCommandLineOptions(self):
        longOptions = self._getSettingsOptions()
        options = None
        remaining = None
        longOptions = self._injectSynonyms(longOptions)
        try:
            options, remaining = getopt.getopt(sys.argv[1:], "", longOptions)
            self.settings['*'] = remaining
        except Exception, e:
            self.log.critical(str(e))
            self.usage(str(e))
            sys.exit(1)
        options = self._handleSynonyms(options)

        for option, arg in options:
            key = option[2:]
            subkey = None
            setting = None
            if ':' in option:
                parts = key.split(':')
                key = parts[0]
                subkey = parts[1]
            if subkey == None:
                if self.settings.getObject(key).isFlag:
                    self.settings[key] = True
                else:
                    self.settings[key] = arg.strip()
            else:
                if self.settings[key][subkey].isFlag:
                    self.settings[key][subkey].value = True
                else:
                    self.settings[key][subkey].value = arg.strip()

    def _setupDefaultLoggingConfiguration(self):
        logging.basicConfig(format=None)
        self.chatlog = logging.getLogger('__chat')
        logging.basicConfig()
        self.log = logging
        self.log.devdebug = self.log.debug

    #==========================================================
    # Immediate options actions
    #==========================================================
    def showVersion(self):
        if self._LIBRARY_VERSION is not None:
            stderr.write("%s version: %s (lib: v%s)\n" % (
                self.scriptName,
                self.scriptVersion,
                self._LIBRARY_VERSION))
        else:
            stderr.write("%s version: %s\n" % (
                self.scriptName,
                self.scriptVersion ))

    def _setupLogging(self):
        logConfig = {"level" : logging.WARNING}
        key = self.DEFAULT_CONFIG_VERBOSE_KEY
        if key is not None and self.settings[key]:
            logConfig['level'] = logging.INFO
        key = self.DEFAULT_CONFIG_DEBUG_KEY
        if key is not None and self.settings[key]:
            logConfig['level'] = logging.DEBUG
        key = self.DEFAULT_CONFIG_QUIET_KEY
        if key is not None and self.settings[key]:
            logConfig['level'] = 99999

        logkey = self.DEFAULT_CONFIG_LOG_KEY
        if logkey is not None and self.settings[logkey] is not None:
            try:
                self.logfile = open(self.settings[logkey], 'w')
            except Exception as e:
                self.log.critical("Log file '%s' could not be opened: (%s) %s", self.settings['log'], e.__class__.__name__, str(e))
                sys.exit(2)
        else:
            self.logfile = sys.stdout
        logConfig['stream'] = self.logfile
        if self.logFormat is not None:
            logConfig['format'] = self.logFormat
        logging.basicConfig(**logConfig)
        self.log = logging.getLogger("%s.%s" % (
            self.__class__.__module__,
            self.__class__.__name__ ) )
        self.log.setLevel(logConfig['level'])

    def _forceQuiet(self):
        key = self.DEFAULT_CONFIG_QUIET_KEY
        if key is not None:
            self.settings[key] = True
        self.log.setLevel(99999)
        self.chat.setLevel(99999)

    def _executeOptions(self):
        if self.DEFAULT_CONFIG_VERSION_KEY is not None:
            if self.settings[self.DEFAULT_CONFIG_VERSION_KEY]:
                self.showVersion()
                self._forceQuiet()
                sys.exit(0)

        key = self.DEFAULT_CONFIG_VERBOSE_KEY
        verbosityRequired = key is None or self.settings[key]
        key = self.DEFAULT_CONFIG_HELP_KEY
        if key is not None:
            if self.settings[key]:
                self.usage(None, verbosityRequired)
                self._forceQuiet()
                sys.exit(0)

        key = self.DEFAULT_CONFIG_LONG_HELP_KEY
        if key is not None:
            if self.settings[key]:
                self.usage(None, True)
                self._forceQuiet()
                sys.exit(0)


    def usage(self, message, useLong=False):
        """Output a generic usage message"""

        useLong = useLong or self.DEFAULT_CONFIG_LONG_HELP_KEY is None
        if message != None:
            self.chat(message)

        if useLong:
            self.chat("Usage (Defaults shown for values):")
        else:
            self.chat("Brief usage (use --%s for more information):" % \
                self.DEFAULT_CONFIG_LONG_HELP_KEY)

        self.chat("")
        self.chat(self.DEFAULT_COMMAND_LINE_USAGE % self.scriptName)

        self.chat("")
        self.chat('================= Basic Options ==================')

        groupKeys = []
        keys = sorted(self.settings.keys())
        synonymTargets = None
        if self.DEFAULT_CONFIG_SYNONYMS is not None:
            synonymTargets = self.DEFAULT_CONFIG_SYNONYMS.values()
        for key in keys:
            setting = self.settings.getObject(key)

            if key == '*':
                continue
            if isinstance(self.settings[key], dict):
                groupKeys.append(key)
                continue

            description = setting.short
            if useLong:
                description = setting.description
                if not setting.isFlag:
                    if self.redactre.match(key) is not None:
                        self.settings[key] = "<REDACTED>"
                    self.chat( "    --%s=%s : " % (
                        key,
                        self.settings[key]))
                else:
                    self.chat( "    --%s : " % key)
                self.chat( "        %s" % description)
            else:
                self.chat("    --%s: %s" % (key, description))
            if synonymTargets is not None and key in synonymTargets:
                synonyms = []
                for synonym, target in self.DEFAULT_CONFIG_SYNONYMS.iteritems():
                    if target == key:
                        synonyms.append('--' + synonym)
                self.chat("       Synonyms: %s" % ', '.join(synonyms))
        for key in groupKeys:
            self.chat("")
            self.chat( "  ==== %s options ====" % key)
            for subkey, value in self.settings[key].iteritems():
                description = value.short
                if useLong:
                    description = value.description
                    if self.redactre.match(subkey) is not None:
                        self.settings[key][subkey] = "<REDACTED>"
                    if not value.isFlag:
                        self.chat( "    --%s:%s=%s :" % (
                            key,
                            subkey,
                            value.value))
                    else:
                        self.chat( "    --%s:%s :" % (
                        key,
                        subkey))
                    self.chat( "        %s" % description)
                else:
                    self.chat("    --%s:%s - %s" % (
                        key,
                        subkey,
                        description ) )
        self.chat("")

        self._usagePostscript(useLong)

    def _usagePostscript(self, useLong):
        pass

    #===========================================================
    # Main methods
    #===========================================================
    def __init__(self, settings={}, name='<name>', version='<version>'):
        self.logFormat = None
        self.outstream = sys.stdout
        self.scriptName = name
        self.scriptVersion = version
        self._setupDefaultLoggingConfiguration()

        if self.DEFAULT_CONFIG_PATHS is not None and \
           self.DEFAULT_CONFIG_FILE_KEY is not None:
            self._setupDefaultConfigFileEntries(settings)

        self._setupDefaultSettings(settings, self._setupDefaultSettingsList())

        self.settings = Settings(settings)
        self.redactre = None

    def chat(self, text, cr=True):
        try:
            self.log.chat(text, cr)
        except:
            try:
                self.chatlog.critical(text)
            except:
                try:
                    self.outstream.write('x ' + text + '\n' if cr else '')
                except:
                    sys.stderr.write('x ' + text + '\n' if cr else '')

    def main(self):
        returncode = -1
        redactre = 'a^'
        if len(self.DEFAULT_CONFIG_KEY_REDACT_VALUE_REGEX) != 0:
            redactre = '(' + ')|('.join(self.DEFAULT_CONFIG_KEY_REDACT_VALUE_REGEX) + ')'
        self.redactre = re.compile(redactre)
        try:
            self._getOptions()
            self._setupLogging()
            self._executeOptions()
            self._mainSetup()
            returncode = self._realmain()
        except SystemExit as sysexit:
            if str(sysexit) != '0':
                self.log.error("%s exited with code %s:", self.scriptName, str(sysexit))
                returncode = int(str(sysexit))
            else:
                returncode = 0
        except BaseException as e:
            self.log.exception("%s exited on exception", self.scriptName)
            returncode = 1
        finally:
            try:
                self._mainEnd()
            except:
                logging.exception("_mainEnd cleanup execution failed")
            try:
                logging.shutdown()
            except:
                pass

        sys.exit(returncode)

    def _mainSetup(self):
        pass

    def _mainEnd(self):
        pass

    def _realmain(self):
        self.log.critical("This is the stub application - you shouldn't be seeing this message")
        pass
