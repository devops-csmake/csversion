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
import os.path

class CollectPips:
    """Purpose: Record the version of all the pip installations on the
                created image, both global and all virtual envs.
    Options: chroot - (OPTIONAL) Path to the chrootable built environment
             docker - (OPTIONAL) Docker container to interrogate
             find-venvs - (OPTIONAL) Search for venvs, default is False
    """

    #PACKAGE_RE = re.compile(r'(?P<package>[^\s(]*)\s*(\()?(?P<version>[^)]*)(\))?')
    PACKAGE_RE = re.compile(r'(?P<package>[^=]*)==(?P<version>.*)')
    ESCAPE_RE = re.compile(r'( |"|\')')

    def _appendPip(self, tag, versdict, virtualenv, specs):
        for spec in specs:
            preppedspec = spec.strip()
            if len(preppedspec) == 0:
                continue
            m = self.PACKAGE_RE.match(preppedspec)
            if m is None:
                self.log.info('%s was not recognized from pip freeze', preppedspec)
                continue
            package = m.group('package')
            version = m.group('version')
            if package not in versdict:
                versdict[package] = {}
            if tag not in versdict[package]:
                versdict[package][tag] = {}
            if 'pip' not in versdict[package][tag]:
                versdict[package][tag]['pip'] = {}
            if virtualenv in versdict[package][tag]['pip']:
                self.log.debug(
                    "Package: %s, Tag: %s, Type: pip, Venv: %s :: Overwriting %s",
                     package,
                     tag,
                     virtualenv,
                     str(versdict[package][tag]['pip'][virtualenv]) )
            versdict[package][tag]['pip'][virtualenv] = {
                'VENV' : virtualenv,
                'PACKAGE' : package,
                'VERSION' : version }
            self.log.debug(
                "Package: %s, Tag: %s, Type: pip, Venv: %s :: Added %s",
                package,
                tag,
                virtualenv,
                str(versdict[package][tag]['pip'][virtualenv]) )

    def __init__(self, log):
        self.log = log

    def defaultPrefix(self):
        return 'sources'

    def csversionPopulateManifest(self, manifest, options, key, tag, prefix):
        versdict = manifest
        docker = False
        sudo = True
        find_venvs = False
        if 'find-venvs' in options:
            find_venvs = options['find-venvs'].lower() == 'true'
        if 'chroot' in options:
            mountpath = options['chroot']
            chroot = True
        else:
            mountpath = '/'
            chroot = False

        if 'docker' in options:
            docker = True
            container = options['docker']

        commandPrefix = []
        dockerCommand = lambda x: x
        if chroot:
            commandPrefix = ["chroot", mountpath]
        if docker:
            dockerCommand = lambda x : ["docker", "exec", "-it", container, 'bash', '-c', "%s" % ' '.join( [ self.ESCAPE_RE.sub(r'\\\1', y.replace('\\','\\\\\\')) for y in x] ) ]
        if sudo:
            uberCommand = lambda x : ["sudo", "-E"] + dockerCommand(x)
        else:
            uberCommand = dockerCommand

        grockCommand = lambda x: uberCommand(commandPrefix + x)

        venvs = []
        if find_venvs:
            command = grockCommand(["find", "/", "|", "grep", "'bin/activate_this'"])
            p = subprocess.Popen(
                ' '.join(command),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE )
            out, err = p.communicate()
            if p.returncode != 0:
                self.log.info("Search for virtual environments failed")
                self.log.info("   It is possible that there are no virtual environments")
                self.log.debug(err)
            else:
                venvraw = out.split('\n')
                for raw in venvraw:
                    preppedpath = raw.strip().strip('.')
                    if len(preppedpath) == 0:
                        continue
                    venv, _ = os.path.split(os.path.split(preppedpath)[0])
                    venvs.append(venv)
            self.log.info("CollectPips will inspect the following virtualenvs: %s", str(venvs))
        command = grockCommand(['pip', 'freeze'])
        p = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE )
        out, err = p.communicate()
        #Iterate through all the freeze results
        specs = out.split('\n')
        self._appendPip(tag, versdict, '__global', specs)

        #Iterate through all the venvs
        delim = "=-=-=-=-=-=-=-=-="
        for venv in venvs:
            command = grockCommand([
                '/bin/bash',
                '-c',
                "'source %s/bin/activate; echo %s; pip freeze; deactivate;'" % (
                    venv, delim ) ])
            p = subprocess.Popen(
                ' '.join(command),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE )
            out, err = p.communicate()
            if p.returncode != 0:
                self.log.info("Could not get information on %s", venv)
                self.log.debug(err)
                continue
            done = False
            piplines = out.split('\n')
            count = 0
            while not done and count < len(piplines):
                done = piplines[count].strip() == delim
                count = count + 1
            piplines = piplines[count:]
            self._appendPip(tag, versdict, venv, piplines)
        return versdict

