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
import subprocess
import re

class Sheller:
    """Purpose: Set specified shell script output to manifest paths
       Options: The option keys define the manifest part
                below the key to set.
       Note:    If no prefix is defined, the default will be product.capture
                The shells must succeed with a success (0) return code
                Uses /bin/bash as the execution environment
       Example:
            [Sheller@myProduct product.metadata]
            version.build = echo 33
            modified = echo $HOME
                date
                echo "What a lovely day!"
            
          This will set product.metadata.myProduct.version.build to 33
          and product.metadata.myProduct.modified to the current value
          of $HOME, followed by the result of the 'date' command
          followed by the string: What a lovely day
          The following dictionary entry would result assuming:
             HOME is the value 'auser'
             and the date is 'Tue Nov  6 10:29:08 MST 2018'

           {'product' : {'metadata' : {'myProduct' : { 'modified' : "auser\nTue Nov  6 10:29:08 MST 2018\nWhat a lovely day!" } } } }
        """

    def __init__(self, log):
        self.log = log

    def defaultPrefix(self):
        return 'product.capture'

    def csversionPopulateManifest(self, manifest, options, key, tag, prefix):
        if tag not in manifest:
            manifest[tag] = {}
        versdict = manifest[tag]
        for option, value in options.iteritems():
            if option.startswith('**'):
                continue
            manifestPart = versdict
            previousManifestPart = versdict
            part = option
            for part in option.split('.'):
                previousManifestPart = manifestPart
                if part not in manifestPart:
                    manifestPart[part] = {}
                manifestPart = manifestPart[part]
            try:
                previousManifestPart[part] = subprocess.check_output(
                    value,
                    shell=True ).strip()
            except subprocess.CalledProcessError as cpe:
                previousManifestPart[part] = "<<<Sheller FAILED>>> Return code: %d, Execution attempted: %s" % (cpe.returncode, cpe.cmd)
                self.log.error("Sheller FAILED for tag '%s' prefix '%s' entry '%s' (Return code: %d) when attempting: %s",
                    tag,
                    prefix,
                    option,
                    cpe.returncode,
                    cpe.cmd )
        return manifest
