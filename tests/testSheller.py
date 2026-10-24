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
"""Sheller, with subprocess.check_output replaced by a type-faithful fake.

Like the real call, the fake returns bytes unless text mode is requested and
raises CalledProcessError for a non-zero exit.
"""
import unittest

from . import fakes
from . import support
from CsversionModules.Sheller import Sheller


def shell(options, *script, **kwargs):
    """Returns (manifest, processes, log); the manifest is the prefix part
       Sheller was handed."""
    manifest = kwargs.get('manifest', {})
    log = support.mockLog()
    with fakes.patchSubprocess(*script) as processes:
        returned = Sheller(log).csversionPopulateManifest(
            manifest, options, 'Sheller', 'prod', 'product.metadata')
    assert returned is manifest
    return manifest, processes, log


class ShellerTests(unittest.TestCase):
    def test_sheller_runs_each_option_through_a_shell_in_text_mode(self):
        manifest, processes, _ = shell(
            {'greeting': 'echo hello'}, fakes.Completed('hello\n'))
        self.assertEqual(len(processes.calls), 1)
        call = processes.calls[0]
        self.assertEqual(call.args, 'echo hello')
        self.assertIs(call.kwargs['shell'], True)
        self.assertTrue(call.kwargs.get('universal_newlines') or
                        call.kwargs.get('text'))

    def test_sheller_stores_stripped_text_not_bytes(self):
        manifest, _, _ = shell(
            {'greeting': 'echo hello'}, fakes.Completed('hello\n'))
        self.assertEqual(manifest, {'prod': {'greeting': 'hello'}})
        self.assertIsInstance(manifest['prod']['greeting'], str)

    def test_sheller_keeps_interior_newlines_of_multiline_output(self):
        manifest, _, _ = shell(
            {'multi': 'echo one; echo two'}, fakes.Completed('one\ntwo\n\n'))
        self.assertEqual(manifest['prod']['multi'], 'one\ntwo')

    def test_sheller_windows_newlines_are_translated(self):
        manifest, _, _ = shell(
            {'multi': 'x'}, fakes.Completed('one\r\ntwo\r\n'))
        self.assertEqual(manifest['prod']['multi'], 'one\ntwo')

    def test_sheller_empty_output_is_stored_as_empty_string(self):
        manifest, _, _ = shell({'nothing': 'true'}, fakes.Completed(''))
        self.assertEqual(manifest['prod']['nothing'], '')

    def test_sheller_non_ascii_output_stays_text(self):
        manifest, _, _ = shell(
            {'name': 'echo'}, fakes.Completed('café\n'))
        self.assertEqual(manifest['prod']['name'], 'café')

    def test_sheller_undecodable_output_raises_unicode_error(self):
        with self.assertRaises(UnicodeDecodeError):
            shell({'name': 'echo'}, fakes.Completed(b'\xff\n'))

    def test_sheller_dotted_option_builds_nested_manifest_path(self):
        manifest, _, _ = shell(
            {'version.build': 'echo 33'}, fakes.Completed('33\n'))
        self.assertEqual(manifest, {'prod': {'version': {'build': '33'}}})

    def test_sheller_ignores_double_star_options(self):
        manifest, processes, _ = shell(
            {'**note': 'echo ignored', 'a': 'echo a'}, fakes.Completed('a\n'))
        self.assertEqual(manifest, {'prod': {'a': 'a'}})
        self.assertEqual([c.args for c in processes.calls], ['echo a'])

    def test_sheller_adds_to_an_existing_tag_dictionary(self):
        manifest, _, _ = shell(
            {'b': 'echo b'}, fakes.Completed('b\n'),
            manifest={'prod': {'a': 'kept'}})
        self.assertEqual(manifest, {'prod': {'a': 'kept', 'b': 'b'}})

    def test_sheller_default_prefix_is_product_capture(self):
        self.assertEqual(Sheller(support.mockLog()).defaultPrefix(),
                         'product.capture')

    def test_sheller_failed_command_records_failure_text(self):
        manifest, _, _ = shell(
            {'broken': 'exit 3'}, fakes.Completed('partial\n', returncode=3))
        self.assertEqual(
            manifest['prod']['broken'],
            '<<<Sheller FAILED>>> Return code: 3, Execution attempted: '
            'exit 3')

    def test_sheller_failed_command_is_logged_as_an_error(self):
        manifest, _, log = shell(
            {'broken': 'exit 3'}, fakes.Completed('', returncode=3))
        self.assertEqual(log.error.call_count, 1)
        args = log.error.call_args[0]
        self.assertEqual(args[1:], ('prod', 'product.metadata', 'broken', 3,
                                    'exit 3'))

    def test_sheller_failure_does_not_stop_the_remaining_options(self):
        options = {'first': 'exit 1', 'second': 'echo ok'}
        manifest, processes, _ = shell(
            options, fakes.Completed('', returncode=1),
            fakes.Completed('ok\n'))
        self.assertEqual(len(processes.calls), 2)
        self.assertEqual(manifest['prod']['second'], 'ok')
        self.assertTrue(manifest['prod']['first'].startswith(
            '<<<Sheller FAILED>>>'))


if __name__ == '__main__':
    unittest.main()
