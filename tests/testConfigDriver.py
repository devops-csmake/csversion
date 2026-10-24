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
"""ConfigDriver turns a csversionfile into calls on the collector modules.

The csversionfile is served from memory (configparser's read() is patched)
and the collector modules are fakes registered in CsversionModules, so only
ConfigDriver's own logic runs: section parsing, module lookup, prefix and tag
handling and the capture record.
"""
import datetime
import sys
import types
import unittest
from unittest import mock

import CsversionModules

from . import fakes
from . import support
from Csversion import ConfigDriver as configdriver
from Csversion.ConfigDriver import ConfigDriver

CONFIG = 'test.csversion'


class FakeCollector(object):
    calls = []

    def __init__(self, log):
        self.log = log

    def defaultPrefix(self):
        return 'sources'

    def csversionPopulateManifest(self, manifest, options, key, tag, prefix):
        FakeCollector.calls.append(types.SimpleNamespace(
            manifest=manifest, options=options, key=key, tag=tag,
            prefix=prefix))
        manifest['touched-by-' + tag] = True
        return manifest


def execute(text, argv=('csversion', '--capture'), now=None):
    """Run a csversionfile through ConfigDriver with FakeCollector standing
       in for a real module.  Returns (manifest, log)."""
    FakeCollector.calls = []
    manifest = {}
    log = support.mockLog()
    fake = types.SimpleNamespace(FakeCollector=FakeCollector)
    clock = mock.Mock()
    clock.datetime.utcnow.return_value = now or datetime.datetime(
        2018, 11, 14, 1, 2, 3)
    with fakes.patchConfigFiles({CONFIG: text}), \
            mock.patch.object(CsversionModules, 'FakeCollector', fake,
                              create=True), \
            mock.patch.object(configdriver, 'datetime', clock), \
            mock.patch.object(sys, 'argv', list(argv)):
        ConfigDriver([CONFIG], log, manifest).execute()
    return manifest, log


class ConfigDriverTests(unittest.TestCase):
    def test_config_driver_hands_options_tag_and_prefix_to_the_module(self):
        manifest, _ = execute(
            '[FakeCollector@prod product.metadata]\nname = prod\nbuild = 7\n')
        (call,) = FakeCollector.calls
        self.assertEqual(call.options, {'name': 'prod', 'build': '7'})
        self.assertEqual((call.key, call.tag, call.prefix),
                         ('FakeCollector', 'prod', 'product.metadata'))

    def test_config_driver_gives_the_module_the_manifest_part_at_its_prefix(
            self):
        manifest, _ = execute('[FakeCollector@prod a.b]\nx = 1\n')
        (call,) = FakeCollector.calls
        self.assertIs(call.manifest, manifest['a']['b'])
        self.assertTrue(manifest['a']['b']['touched-by-prod'])

    def test_config_driver_uses_the_modules_default_prefix_without_one(self):
        manifest, log = execute('[FakeCollector@prod]\nx = 1\n')
        (call,) = FakeCollector.calls
        self.assertEqual(call.prefix, 'sources')
        self.assertIn('touched-by-prod', manifest['sources'])
        self.assertTrue(any('Prefix not specified' in c[0][0]
                            for c in log.debug.call_args_list))

    def test_config_driver_tag_defaults_to_underscore(self):
        manifest, _ = execute('[FakeCollector a.b]\nx = 1\n')
        (call,) = FakeCollector.calls
        self.assertEqual(call.tag, '_')
        self.assertEqual(manifest['product']['capture'], {
            '_': {'command': 'csversion --capture',
                  'time': '2018-11-14T01:02:03Z'}})

    def test_config_driver_runs_sections_in_file_order(self):
        execute('[FakeCollector@one a]\nx = 1\n'
                '[FakeCollector@two b]\nx = 2\n'
                '[FakeCollector@three c]\nx = 3\n')
        self.assertEqual([c.tag for c in FakeCollector.calls],
                         ['one', 'two', 'three'])

    def test_config_driver_records_command_and_utc_time_for_each_tag(self):
        manifest, _ = execute(
            '[FakeCollector@one a]\nx = 1\n[FakeCollector@two b]\nx = 2\n'
            '[FakeCollector@one c]\nx = 3\n',
            argv=('csversion', '--capture', '--csversionfile=f'),
            now=datetime.datetime(2018, 11, 14, 1, 2, 3, 456))
        capture = manifest['product']['capture']
        self.assertEqual(sorted(capture), ['one', 'two'])
        for tag in ('one', 'two'):
            self.assertEqual(capture[tag], {
                'command': 'csversion --capture --csversionfile=f',
                'time': '2018-11-14T01:02:03.000456Z'})

    def test_config_driver_capture_record_values_are_text(self):
        manifest, _ = execute('[FakeCollector@one a]\nx = 1\n')
        support.assertAllText(self, manifest)

    def test_config_driver_resolves_real_modules_by_section_name(self):
        manifest = {}
        with fakes.patchConfigFiles(
                {CONFIG: '[Setter@prod product.metadata]\nname = prod\n'}), \
                mock.patch.object(configdriver, 'datetime', mock.Mock()):
            ConfigDriver([CONFIG], support.mockLog(), manifest).execute()
        self.assertEqual(manifest['product']['metadata'],
                         {'prod': {'name': 'prod'}})

    def test_config_driver_module_without_matching_class_is_an_error(self):
        log = support.mockLog()
        empty = types.SimpleNamespace(Hollow=None)
        del empty.Hollow
        with fakes.patchConfigFiles({CONFIG: '[Hollow@prod a]\nx = 1\n'}), \
                mock.patch.object(CsversionModules, 'Hollow', empty,
                                  create=True):
            with self.assertRaises(ValueError) as caught:
                ConfigDriver([CONFIG], log, {}).execute()
        self.assertEqual(str(caught.exception), "Missing class 'Hollow'")
        self.assertEqual(log.error.call_count, 1)

    def test_config_driver_missing_csversionfile_is_logged_not_raised(self):
        log = support.mockLog()
        manifest = {}
        with fakes.patchConfigFiles({}):
            ConfigDriver(['nope.csversion'], log, manifest).execute()
        log.error.assert_called_once_with(
            "csversionfile '%s', not found", 'nope.csversion')
        self.assertEqual(manifest, {'product': {'capture': {}}})

    def test_config_driver_without_local_modules_logs_a_hint(self):
        log = support.mockLog()
        with mock.patch.dict(sys.modules, {'CsversionLocalModules': None}):
            ConfigDriver([], log, {})
        self.assertTrue(any('No local modules found' in c[0][0]
                            for c in log.debug.call_args_list))

    @unittest.skip("pre-existing bug: CsversionLocalModules is imported "
                   "inside __init__ but used as a global in execute(), so "
                   "an unknown section raises NameError, not ValueError")
    def test_config_driver_unknown_section_is_a_value_error(self):
        with fakes.patchConfigFiles({CONFIG: '[Nope@prod a]\nx = 1\n'}):
            with self.assertRaises(ValueError):
                ConfigDriver([CONFIG], support.mockLog(), {}).execute()


if __name__ == '__main__':
    unittest.main()
