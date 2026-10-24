# <copyright>
# (c) Copyright 2026 Autumn Patterson
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
"""The collectors run real subprocesses and parse their output.

Under Python 3 a bare Popen/check_output yields bytes, which breaks the
`out.split('\\n')` parsing and would put bytes (yaml !!binary) in the
manifest.  These tests drop fake `sudo`, `dpkg-query`, `rpm`, `pip` and
`find` scripts first on PATH, so the code under test spawns real child
processes (no mocking of subprocess) and the parsed result is deterministic.
"""
import json
import os
import shutil
import tempfile
import unittest

from . import support
from CsversionModules.CollectDpkgs import CollectDpkgs
from CsversionModules.CollectPips import CollectPips
from CsversionModules.CollectRpms import CollectRpms


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.log = support.quietLogger()
        self.tmp = tempfile.mkdtemp(prefix='csversion-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def assertSerialisable(self, manifest):
        support.assertAllText(self, manifest)
        json.dumps(manifest)

    def test_dpkg_query_output_is_parsed_as_text(self):
        fake = {
            'sudo': support.FAKE_SUDO,
            'dpkg-query': 'cat <<\'EOF\'\n'
                          'bash (5.0-4) (amd64)\n'
                          'libc6:amd64 (2.31-0ubuntu9) (amd64)\n'
                          'tzdata (2021a+deb10u1) (all)\n'
                          'this line does not match\n'
                          '\n'
                          'EOF\n' }
        manifest = {}
        with support.fakeCommands(fake):
            CollectDpkgs(self.log).csversionPopulateManifest(
                manifest, {}, 'CollectDpkgs', 'prod', 'sources')
        self.assertEqual(
            manifest['bash']['prod']['dpkg']['amd64'],
            {'PACKAGE': 'bash', 'VERSION': '5.0', 'RELEASE': '4',
             'ARCH': 'amd64'})
        self.assertEqual(
            manifest['libc6']['prod']['dpkg']['amd64']['RELEASE'],
            '0ubuntu9')
        self.assertEqual(
            manifest['tzdata']['prod']['dpkg']['all']['VERSION'], '2021a')
        self.assertEqual(sorted(manifest), ['bash', 'libc6', 'tzdata'])
        self.assertSerialisable(manifest)

    def test_rpm_output_is_parsed_as_text(self):
        fake = {
            'sudo': support.FAKE_SUDO,
            'rpm': 'echo "bash 5.0 4.el8 x86_64"\n'
                   'echo "glibc 2.28 72.el8 x86_64"\n' }
        manifest = {}
        with support.fakeCommands(fake):
            CollectRpms(self.log).csversionPopulateManifest(
                manifest, {}, 'CollectRpms', 'prod', 'sources')
        self.assertEqual(
            manifest['bash']['prod']['rpm']['x86_64'],
            {'PACKAGE': 'bash', 'VERSION': '5.0', 'RELEASE': '4.el8',
             'ARCH': 'x86_64'})
        self.assertEqual(sorted(manifest), ['bash', 'glibc'])
        self.assertSerialisable(manifest)

    def test_pip_freeze_global_and_virtualenv_output_is_parsed_as_text(self):
        # find-venvs exercises all of CollectPips' Popen calls: the shell
        # pipeline that finds venvs, the global freeze, and the per-venv one
        venv = os.path.join(self.tmp, 'venvA')
        os.makedirs(os.path.join(venv, 'bin'))
        support.writeFile(
            os.path.join(venv, 'bin'), 'activate',
            'export FAKE_VENV=venvA\ndeactivate() { unset FAKE_VENV; }\n')
        fake = {
            'sudo': support.FAKE_SUDO,
            'find': "echo '%s/bin/activate_this.py'\n" % venv,
            'pip': '[ "$1" = freeze ] || exit 2\n'
                   'if [ "$FAKE_VENV" = venvA ]; then\n'
                   '  echo flask==2.0.1\n'
                   'else\n'
                   '  echo requests==2.31.0\n'
                   '  echo "-e git+https://example.invalid/x.git#egg=x"\n'
                   'fi\n' }
        manifest = {}
        with support.fakeCommands(fake):
            CollectPips(self.log).csversionPopulateManifest(
                manifest, {'find-venvs': 'true'}, 'CollectPips', 'prod',
                'sources')
        self.assertEqual(
            manifest['requests']['prod']['pip'],
            {'__global': {'VENV': '__global', 'PACKAGE': 'requests',
                          'VERSION': '2.31.0'}})
        self.assertEqual(
            manifest['flask']['prod']['pip'],
            {venv: {'VENV': venv, 'PACKAGE': 'flask', 'VERSION': '2.0.1'}})
        self.assertEqual(sorted(manifest), ['flask', 'requests'])
        self.assertSerialisable(manifest)


if __name__ == '__main__':
    unittest.main()
