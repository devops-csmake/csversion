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
"""Outputs: the classes that render a manifest as yaml, json or xml.

Streams are in-memory; setFileAsStream gets one real temp file because
opening, writing and closing a file in text mode is exactly what it does.
"""
import io
import json
import shutil
import tempfile
import unittest
from unittest import mock

from . import fakes
from . import support

if support.yaml is None:
    raise unittest.SkipTest("PyYAML is not installed")

yaml = support.yaml
from Csversion import Csversion as csversion
from Csversion.Csversion import JsonOutput
from Csversion.Csversion import Output
from Csversion.Csversion import XmlOutput
from Csversion.Csversion import YamlOutput

DATA = {'product': {'metadata': {'prod': {
    'name': 'prod', 'version-full': '1.2.3', 'version': {'build': '33'}}}}}


def render(outputClass, data):
    out = outputClass()
    out.stream = io.StringIO()
    out.output(data)
    text = out.stream.getvalue()
    out.stream = None
    return text


class YamlOutputTests(unittest.TestCase):
    def test_yaml_output_round_trips(self):
        self.assertEqual(yaml.safe_load(render(YamlOutput, DATA)), DATA)

    def test_yaml_output_of_text_values_has_no_binary_tags(self):
        self.assertNotIn('!!binary', render(YamlOutput, DATA))

    def test_yaml_output_accepts_a_dict_subclass(self):
        manifest = csversion.Manifest([])
        manifest.update(DATA)
        self.assertEqual(yaml.safe_load(render(YamlOutput, manifest)), DATA)

    def test_yaml_output_numeric_looking_text_stays_text(self):
        out = yaml.safe_load(render(YamlOutput, {'a': {'build': '33'}}))
        self.assertEqual(out['a']['build'], '33')


class JsonOutputTests(unittest.TestCase):
    def test_json_output_round_trips(self):
        self.assertEqual(json.loads(render(JsonOutput, DATA)), DATA)

    def test_json_output_accepts_a_dict_subclass(self):
        manifest = csversion.Manifest([])
        manifest.update(DATA)
        self.assertEqual(json.loads(render(JsonOutput, manifest)), DATA)

    def test_json_output_escapes_non_ascii_text(self):
        text = render(JsonOutput, {'name': 'café'})
        self.assertEqual(json.loads(text), {'name': 'café'})

    def test_json_output_refuses_bytes(self):
        # why the collectors must produce text
        with self.assertRaises(TypeError):
            render(JsonOutput, {'name': b'bytes'})


class XmlOutputTests(unittest.TestCase):
    def test_xml_output_nests_dicts_with_indentation(self):
        self.assertEqual(
            render(XmlOutput, {'a': {'b': '1'}}),
            '<a>\n'
            '    <b>\n'
            '        1\n'
            '    </b>\n'
            '</a>\n')

    def test_xml_output_wraps_list_entries_in_item_elements(self):
        self.assertEqual(
            render(XmlOutput, {'a': ['x', {'c': '1'}]}),
            '<a>\n'
            '    <item>\n'
            '        x\n'
            '    </item>\n'
            '    <item>\n'
            '        <c>\n'
            '            1\n'
            '        </c>\n'
            '    </item>\n'
            '</a>\n')

    def test_xml_output_writes_non_string_scalars_as_text(self):
        self.assertIn('        3\n', render(XmlOutput, {'a': {'b': 3}}))

    def test_xml_output_non_ascii_text_is_written_as_text(self):
        self.assertIn('café', render(XmlOutput, {'name': 'café'}))

    def test_xml_output_accepts_a_dict_subclass(self):
        manifest = csversion.Manifest([])
        manifest.update({'a': {'b': '1'}})
        self.assertIn('<b>', render(XmlOutput, manifest))


class OutputStreamTests(unittest.TestCase):
    def test_output_writes_the_dictionary_repr_by_default(self):
        self.assertEqual(render(Output, {'a': 1}), "{'a': 1}")

    def test_output_defaults_to_standard_out(self):
        buffer = fakes.KeepOpen()
        with mock.patch.object(csversion, 'stdout', buffer):
            out = YamlOutput()
            self.assertIs(out.stream, buffer)
            out.output({'a': '1'})
            out.close()
        self.assertEqual(buffer.getvalue(), "a: '1'\n")

    def test_output_close_leaves_standard_out_open(self):
        buffer = io.StringIO()
        with mock.patch.object(csversion, 'stdout', buffer):
            out = YamlOutput()
            out.close()
        self.assertFalse(buffer.closed)

    def test_output_close_closes_its_own_stream_once(self):
        out = YamlOutput()
        out.stream = mock.Mock()
        stream = out.stream
        out.close()
        out.close()
        stream.close.assert_called_once_with()
        self.assertIsNone(out.stream)


class OutputFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='csversion-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_set_file_as_stream_writes_a_text_file(self):
        path = '%s/out.yaml' % self.tmp
        out = YamlOutput()
        out.setFileAsStream(path)
        out.output(DATA)
        out.close()
        with open(path) as f:
            self.assertEqual(yaml.safe_load(f), DATA)

    def test_set_file_as_stream_replaces_an_existing_file(self):
        path = '%s/out.json' % self.tmp
        with open(path, 'w') as f:
            f.write('stale content that is much longer than the new content')
        out = JsonOutput()
        out.setFileAsStream(path)
        out.output({'a': '1'})
        out.close()
        with open(path) as f:
            self.assertEqual(json.load(f), {'a': '1'})

    def test_set_file_as_stream_in_a_missing_directory_raises(self):
        with self.assertRaises(FileNotFoundError):
            JsonOutput().setFileAsStream('%s/no/such/dir/out.json' % self.tmp)


if __name__ == '__main__':
    unittest.main()
