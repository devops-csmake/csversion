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

class Setter:
    """Purpose: Set specified values into the manifest
       Options: The option keys define the manifest part
                below the key to set.
       Note:    If no prefix is defined, the default will be product.capture
       Example:
            [Setter@myProduct product.metadata]
            version.build = 33
            modified = by csversion
            
          This will set product.metadata.myProduct.version.build to 33
          and product.metadata.myProduct.modified to "by csversion"
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
            previousManifestPart[part] = value
        return manifest
