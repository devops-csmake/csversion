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
"""ConfigDriver runs a csversionfile through the real Setter and Sheller.

This is the capture path without the CLI around it: configparser reading
the csversionfile, module lookup through CsversionModules, `.items()` over
the options, and Sheller's shell output landing in the manifest as text.
"""
import shutil
import tempfile
import unittest

from . import support
from Csversion.ConfigDriver import ConfigDriver

CSVERSIONFILE = """\
[Setter@prod product.metadata]
name = prod
version.build = 33
**ignored = not a manifest entry

[Sheller@prod product.metadata]
greeting = echo hello
multi = echo one
    echo two
broken = exit 3
"""


class ConfigDriverTests(unittest.TestCase):
    def test_setter_and_sheller_populate_manifest_with_text(self):
        tmp = tempfile.mkdtemp(prefix='csversion-test-')
        self.addCleanup(shutil.rmtree, tmp, True)
        path = support.writeFile(tmp, 'test.csversion', CSVERSIONFILE)
        manifest = {}
        ConfigDriver([path], support.quietLogger(), manifest).execute()

        metadata = manifest['product']['metadata']['prod']
        self.assertEqual(metadata['name'], 'prod')
        self.assertEqual(metadata['version'], {'build': '33'})
        self.assertNotIn('**ignored', metadata)
        self.assertEqual(metadata['greeting'], 'hello')
        self.assertEqual(metadata['multi'], 'one\ntwo')
        self.assertEqual(
            metadata['broken'],
            '<<<Sheller FAILED>>> Return code: 3, Execution attempted: '
            'exit 3')

        capture = manifest['product']['capture']['prod']
        self.assertRegex(capture['time'], r'^\d{4}-\d\d-\d\dT[\d:.]+Z$')
        self.assertIsInstance(capture['command'], str)
        support.assertAllText(self, manifest)


if __name__ == '__main__':
    unittest.main()
