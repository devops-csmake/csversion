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
"""Setter writes option values into the manifest part it is given."""
import unittest

from . import support
from CsversionModules.Setter import Setter


def setter(options, manifest=None):
    manifest = {} if manifest is None else manifest
    returned = Setter(support.mockLog()).csversionPopulateManifest(
        manifest, options, 'Setter', 'prod', 'product.metadata')
    assert returned is manifest
    return manifest


class SetterTests(unittest.TestCase):
    def test_setter_stores_values_under_the_tag(self):
        self.assertEqual(
            setter({'name': 'prod', 'modified': 'by csversion'}),
            {'prod': {'name': 'prod', 'modified': 'by csversion'}})

    def test_setter_dotted_option_builds_nested_manifest_path(self):
        self.assertEqual(
            setter({'version.build': '33', 'version.major': '1'}),
            {'prod': {'version': {'build': '33', 'major': '1'}}})

    def test_setter_ignores_double_star_options(self):
        self.assertEqual(setter({'**note': 'x', 'a': 'b'}),
                         {'prod': {'a': 'b'}})

    def test_setter_adds_to_an_existing_tag_dictionary(self):
        manifest = setter({'b': '2'}, {'prod': {'a': '1'}})
        self.assertEqual(manifest, {'prod': {'a': '1', 'b': '2'}})

    def test_setter_overwrites_an_existing_value(self):
        self.assertEqual(setter({'a': 'new'}, {'prod': {'a': 'old'}}),
                         {'prod': {'a': 'new'}})

    def test_setter_no_options_still_creates_the_tag(self):
        self.assertEqual(setter({}), {'prod': {}})

    def test_setter_non_ascii_values_stay_text(self):
        manifest = setter({'name': 'café'})
        self.assertEqual(manifest['prod']['name'], 'café')

    def test_setter_default_prefix_is_product_capture(self):
        self.assertEqual(Setter(support.mockLog()).defaultPrefix(),
                         'product.capture')


if __name__ == '__main__':
    unittest.main()
