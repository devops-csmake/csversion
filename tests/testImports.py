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
"""The packages import cleanly from the repo root.

Csversion/ uses explicit relative imports (`from . import CliDriver`) and
CsversionModules/ registers its collectors through __all__, which
ConfigDriver later looks up by name.
"""
import importlib
import unittest

from . import support


class ImportTests(unittest.TestCase):
    def test_collector_modules_are_registered_by_name(self):
        import CsversionModules
        expected = {'CollectDpkgs', 'CollectPips', 'CollectRpms',
                    'Setter', 'Sheller'}
        self.assertLessEqual(expected, set(CsversionModules.__all__))
        for name in expected:
            # ConfigDriver does CsversionModules.__dict__[name].__dict__[name]
            module = CsversionModules.__dict__[name]
            self.assertIn(name, module.__dict__, "%s has no class %s" % (
                module, name))

    @support.requires_yaml
    def test_csversion_package_modules_import_with_relative_imports(self):
        for name in ('Settings', 'CliDriver', 'ConfigDriver', 'Csversion'):
            with self.subTest(module=name):
                module = importlib.import_module('Csversion.' + name)
                self.assertEqual(module.__name__, 'Csversion.' + name)
        from Csversion.Csversion import CsversionCli
        from Csversion.CliDriver import CliDriver
        self.assertTrue(issubclass(CsversionCli, CliDriver))


if __name__ == '__main__':
    unittest.main()
