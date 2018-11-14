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
import subprocess
import re

class CollectRpms:
    """Purpose: Record the version of all the rpm installations on the
                created image.
    Options: chroot - (OPTIONAL) Path to the chroot environment to query
             docker - (OPTIONAL) Name of container
        """

    PACKAGE_RE = re.compile(r'(?P<package>[^\s]*)\s*(?P<version>[^\s]*)\s*(?P<release>[^\s]*)\s*(?P<arch>[^\s]*)')
    ESCAPE_RE = re.compile(r'( |"|\')')

    def __init__(self, log):
        self.log = log

    def defaultPrefix(self):
        return 'sources'

    def csversionPopulateManifest(self, manifest, options, key, tag, prefix):
        versdict = manifest
        docker = False
        sudo = True
        if 'chroot' in options:
            mountpath = options['chroot']
            chroot = True
        else:
            mountpath = '/'
            chroot = False

        if 'docker' in options:
            docker = True
            container = options['docker']

        command = ["rpm", "-qa", "--qf", "%{NAME} %{VERSION} %{RELEASE} %{ARCH}\\n"]
        if chroot:
            command = ["chroot", mountpath]
        if docker:
            command = [ self.ESCAPE_RE.sub(r'\\\1', x.replace('\\','\\\\\\')) for x in command ]
            command = ["docker", "exec", "-it", container, 'bash', '-c', "%s" % ' '.join(command)]
        if sudo:
            command = ["sudo", "-E"] + command

        self.log.debug("Executing: %s", " ".join(command))
        p = subprocess.Popen(command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE )
            
        out, err = p.communicate()
        dpkgs = out.split('\n')
        for dpkg in dpkgs:
            dpkg = dpkg.strip()
            if len(dpkg) == 0:
                continue
            match = self.PACKAGE_RE.match(dpkg)
            if match is None:
                self.log.debug("Didn't match: %s", dpkg)
                continue
            package = match.group('package')
            version = match.group('version')
            arch = match.group('arch')
            release = match.group('release')
            if len(arch) > 0:
                arch = arch.lstrip(':')
            else:
                arch = '__global'
            if package not in versdict:
                versdict[package] = {}
            if tag not in versdict[package]:
                versdict[package][tag] = {}
            if 'rpm' not in versdict[package][tag]:
                versdict[package][tag]['rpm'] = {}
            if arch in versdict[package][tag]['rpm']:
                self.log.debug(
                    "Package: %s, Tag: %s, Type: rpm, Arch: %s :: Overwriting %s",
                    package,
                    tag,
                    arch,
                    str(versdict[package][tag]['rpm'][arch]))

            versdict[package][tag]['rpm'][arch] = {
                 'PACKAGE' : package,
                 'VERSION' : version,
                 'RELEASE' : release }
            if arch != '__global':
                versdict[package][tag]['rpm'][arch]['ARCH'] = arch
            self.log.debug(
                "Package: %s, Tag: %s, Type: rpm, Arch: %s :: Added %s",
                package,
                tag,
                arch,
                str(versdict[package][tag]['rpm'][arch]) )
        return versdict

