# <copyright>
# (c) Copyright 2018 Cardinal Peak Technologies
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
import CsversionModules
import datetime
import os.path
import sys

class ConfigDriver(object):

    class EmptyModules:
        def __init__(self):
            self.__dict__ = {}

    def __init__(self, configs, log, manifest):
        self.spec = ConfigParser.RawConfigParser()
        self.log = log
        self.manifest = manifest
        for config in configs:
            if os.path.isfile(config):
                self.log.debug("Loading csversionfile: %s", config)
                self.spec.read(configs)
            else:
                self.log.error("csversionfile '%s', not found", config)
        try:
            import CsversionLocalModules
        except ImportError:
            self.log.debug("""No local modules found in CsversionLocalModules
    If this is unexpected, remember to add __init__.py
    __init__.py must import your modules, see man csversion for details""")
            CsversionLocalModules = self.EmptyModules()
            

    def execute(self):
        tags = []
        for key in self.spec.sections():
            options = { stanza: self.spec.get(key, stanza) for stanza in self.spec.options(key) }
            if ' ' in key:
                key, prefix = key.split()
            else:
                prefix = ''

            if '@' in key:
                key, tag = key.split('@',1)
            else:
                tag = '_'

            if tag not in tags:
                tags.append(tag)
            
            if key in CsversionModules.__dict__:
                targetModule = CsversionModules.__dict__[key]
            elif key in CsversionLocalModules.__dict__:
                targetModule = CsversionLocalModules.__dict__[key]
            else:
                self.log.error("Section '%s' not found", key)
                raise ValueError("Section '%s' not found" % key)

            if key not in targetModule.__dict__:
                self.log.error("'%s' was requested and is defined as a module, but does not have a class with the requested name", key)
                #REVISIT: Do we want to proceed with the rest?
                raise ValueError("Missing class '%s'" % key)

            targetInstance = targetModule.__dict__[key](self.log)
            if len(prefix) == 0:
                prefix = targetInstance.defaultPrefix()
                self.log.debug("   vvv Prefix not specified, using default: %s", prefix)
            manifestPart = self.manifest
            for part in prefix.split('.'):
                part = part.strip()
                if part not in manifestPart:
                    manifestPart[part] = {}
                manifestPart = manifestPart[part]
            self.log.debug("Executing Section: [%s@%s %s]", key, tag, prefix)
            targetInstance.csversionPopulateManifest(manifestPart, options, key, tag, prefix)

        if 'product' not in self.manifest:
            self.manifest['product'] = {}
        if 'capture' not in self.manifest['product']:
            self.manifest['product']['capture'] = {}
        for key in tags:
            if key not in self.manifest['product']['capture']:
                self.manifest['product']['capture'][key] = {}
            self.manifest['product']['capture'][key]={
                'command': '%s' % ' '.join(sys.argv),
                'time' : '%sZ' % datetime.datetime.utcnow().isoformat()}
        self.manifest['product']['capture']
