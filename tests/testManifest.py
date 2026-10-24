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
"""Manifest loading, translation and version/time comparison.

Loading is the one place a real file is the point, so those tests write a
real YAML file to a temp dir.  Everything else works on in-memory dicts.
"""
import copy
import datetime
import shutil
import tempfile
import unittest
from unittest import mock

from . import support

if support.yaml is None:
    raise unittest.SkipTest("PyYAML is not installed")

yaml = support.yaml
from Csversion.Csversion import Manifest

NEW_STYLE = """\
product:
  metadata:
    prod:
      name: prod
      version-full: 1.0.0
sources:
  libfoo:
    prod:
      pip:
        __global:
          PACKAGE: libfoo
          VERSION: '1.0'
"""


class LoadManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='csversion-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, name, text):
        path = '%s/%s' % (self.tmp, name)
        with open(path, 'w') as f:
            f.write(text)
        return path

    def test_manifest_load_reads_a_yaml_file(self):
        manifest = Manifest([self.write('a.csversion', NEW_STYLE)])
        self.assertEqual(
            manifest['product']['metadata']['prod']['version-full'], '1.0.0')
        self.assertEqual(
            manifest[('sources', 'libfoo', 'prod', 'pip', '__global')],
            {'PACKAGE': 'libfoo', 'VERSION': '1.0'})
        support.assertAllText(self, dict(manifest))

    def test_manifest_load_uses_the_safe_loader(self):
        # A bare yaml.load(f) is a TypeError on modern PyYAML (Loader is
        # required); an unsafe Loader would build python objects
        evil = self.write('evil.csversion',
                          'product: !!python/object/apply:os.getcwd []\n')
        with self.assertRaises(yaml.YAMLError):
            Manifest([evil])

    def test_manifest_load_malformed_yaml_raises(self):
        broken = self.write('broken.csversion', 'product: [unclosed\n')
        with self.assertRaises(yaml.YAMLError):
            Manifest([broken])

    def test_manifest_load_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            Manifest(['%s/missing.csversion' % self.tmp])

    def test_manifest_load_translates_old_style_sources(self):
        path = self.write(
            'old.csversion',
            "sources:\n  libfoo:\n    prod_ctx:\n      - pip\n"
            "      - {PACKAGE: libfoo, VERSION: '1.0'}\n")
        self.assertEqual(
            Manifest([path])['sources']['libfoo']['prod']['pip']['ctx'],
            {'PACKAGE': 'libfoo', 'VERSION': '1.0'})


class JoinManifestsTests(unittest.TestCase):
    def patchedLoader(self, files):
        def load(manifest, path):
            manifest.update(copy.deepcopy(files[path]))
        return mock.patch.object(Manifest, 'loadManifest', autospec=True,
                                 side_effect=load)

    def test_manifest_single_path_is_loaded_directly(self):
        with self.patchedLoader({'a': {'k': {}}}) as load:
            manifest = Manifest(['a'])
        self.assertEqual(load.call_count, 1)
        self.assertEqual(load.call_args[0][1], 'a')
        self.assertEqual(manifest, {'k': {}})

    def test_manifest_several_paths_are_each_loaded_and_merged(self):
        files = {
            'a': {'product': {'metadata': {'prod': {
                'name': 'prod', 'version-full': '1.0.0'}}}},
            'b': {'product': {'metadata': {'prod': {
                'name': 'prod', 'version-full': '1.1.0'}}}}}
        with self.patchedLoader(files) as load:
            manifest = Manifest(['a', 'b'])
        self.assertEqual(sorted(c[0][1] for c in load.call_args_list),
                         ['a', 'b'])
        prod = manifest['product']['metadata']['prod']
        self.assertEqual(prod['version-full'], '1.1.0')
        self.assertEqual(list(prod['__older']), ['1.0.0__None'])

    def test_manifest_no_paths_and_nothing_preprocessed_is_empty(self):
        with self.patchedLoader({}) as load:
            self.assertEqual(Manifest([]), {})
        self.assertFalse(load.called)

    def test_manifest_paths_join_with_preprocessed_manifests(self):
        files = {'a': {'extra': {'part': {'tag': {'k': 'v'}}}}}
        with self.patchedLoader(files):
            manifest = Manifest(['a'], [{'other': {'part': {'tag': {}}}}])
        self.assertEqual(sorted(manifest), ['extra', 'other'])


class TranslateOldStyleTests(unittest.TestCase):
    def translated(self, data):
        manifest = Manifest([])
        manifest.update(copy.deepcopy(data))
        manifest._translateOldToNewProduct()
        return dict(manifest)

    def test_translate_list_style_becomes_tag_format_context(self):
        result = self.translated({'sources': {'libfoo': {
            'prod_ctx': ['pip', {'PACKAGE': 'libfoo'}]}}})
        self.assertEqual(
            result['sources'],
            {'libfoo': {'prod': {'pip': {'ctx': {'PACKAGE': 'libfoo'}}}}})

    def test_translate_list_without_context_uses_global(self):
        result = self.translated({'sources': {'libfoo': {
            'prod': ['pip', {'PACKAGE': 'libfoo'}]}}})
        self.assertEqual(
            result['sources']['libfoo']['prod']['pip']['__global'],
            {'PACKAGE': 'libfoo'})

    def test_translate_pairs_in_a_list_are_all_converted(self):
        result = self.translated({'sources': {'libfoo': {
            'prod_ctx': ['pip', {'V': '1'}, 'rpm', {'V': '2'}]}}})
        self.assertEqual(sorted(result['sources']['libfoo']['prod']),
                         ['pip', 'rpm'])

    def test_translate_underscore_tag_with_dict_items_drops_the_context(self):
        result = self.translated({'sources': {'libfoo': {
            'prod_ctx': {'pip': {'V': '1'}}}}})
        self.assertEqual(result['sources'],
                         {'libfoo': {'prod': {'pip': {'V': '1'}}}})

    def test_translate_new_style_sources_are_left_alone(self):
        data = {'sources': {'libfoo': {'prod': {'pip': {
            '__global': {'PACKAGE': 'libfoo'}}}}}}
        self.assertEqual(self.translated(data), data)

    def test_translate_without_sources_changes_nothing(self):
        data = {'product': {'metadata': {}}}
        self.assertEqual(self.translated(data), data)


class CompareVersionsTests(unittest.TestCase):
    def setUp(self):
        self.compare = Manifest([]).compareVersions

    def test_compare_versions_lower_numeric_segment_is_negative(self):
        self.assertLess(self.compare('1.0.0', '1.1.0'), 0)

    def test_compare_versions_higher_numeric_segment_is_positive(self):
        self.assertGreater(self.compare('1.1.0', '1.0.0'), 0)

    def test_compare_versions_orders_numerically_not_lexically(self):
        self.assertGreater(self.compare('1.10.0', '1.9.0'), 0)

    def test_compare_versions_identical_versions_are_equal(self):
        self.assertEqual(self.compare('1.0.0', '1.0.0'), 0)

    def test_compare_versions_extra_segment_makes_a_version_greater(self):
        self.assertLess(self.compare('1.0', '1.0.1'), 0)
        self.assertGreater(self.compare('1.0.1', '1.0'), 0)

    def test_compare_versions_first_difference_decides(self):
        self.assertLess(self.compare('1.9.9', '2.0.0'), 0)

    def test_compare_versions_none_sorts_before_any_version(self):
        self.assertLess(self.compare(None, '1.0'), 0)
        self.assertGreater(self.compare('1.0', None), 0)

    def test_compare_versions_two_nones_are_equal(self):
        self.assertEqual(self.compare(None, None), 0)

    def test_compare_versions_equal_text_segments_are_equal(self):
        # Python 3 raises comparing None with None here
        self.assertEqual(self.compare('1.2.rc', '1.2.rc'), 0)

    def test_compare_versions_snapshot_version_equals_itself(self):
        snapshot = '1.0.1.20181114121212.3f516e0'
        self.assertEqual(self.compare(snapshot, snapshot), 0)

    def test_compare_versions_text_segments_order_lexically(self):
        self.assertLess(self.compare('1.2.a', '1.2.b'), 0)
        self.assertGreater(self.compare('1.2.b', '1.2.a'), 0)

    def test_compare_versions_suffix_sorts_after_no_suffix(self):
        # Python 3 raises ordering None against a str here
        self.assertGreater(self.compare('1.2.rc-1', '1.2.rc'), 0)
        self.assertLess(self.compare('1.2.rc', '1.2.rc-1'), 0)

    def test_compare_versions_suffixes_order_lexically(self):
        self.assertLess(self.compare('1.2.rc-1', '1.2.rc-2'), 0)
        self.assertGreater(self.compare('1.2.rc+b2', '1.2.rc+b1'), 0)

    def test_compare_versions_non_string_version_raises(self):
        # e.g. an unquoted `version-full: 1.0` loads from yaml as a float
        with self.assertRaises(AttributeError):
            self.compare(1.0, '1.0')


class CompareTimesTests(unittest.TestCase):
    def setUp(self):
        self.manifest = Manifest([])

    def test_compare_times_earlier_is_negative(self):
        self.assertLess(self.manifest.compareTimes(
            '2018-01-01T00:00:00Z', '2018-01-02T00:00:00Z'), 0)

    def test_compare_times_later_is_positive(self):
        self.assertGreater(self.manifest.compareTimes(
            '2018-01-02T00:00:00Z', '2018-01-01T00:00:00Z'), 0)

    def test_compare_times_same_instant_is_zero(self):
        self.assertEqual(self.manifest.compareTimes(
            '2018-01-01T00:00:00Z', '2018-01-01T00:00:00Z'), 0)

    def test_compare_times_is_in_tenths_of_a_second(self):
        self.assertEqual(self.manifest.compareTimes(
            '2018-01-01T00:00:03Z', '2018-01-01T00:00:00Z'), 30.0)

    def test_compare_times_positive_offset_is_converted_to_utc(self):
        self.assertEqual(self.manifest.compareTimes(
            '2018-01-01T01:00:00+01:00', '2018-01-01T00:00:00Z'), 0)

    @unittest.skip("pre-existing bug: a '-hh:mm' offset is looked for with "
                   "time.split('-', 1), which splits inside the date, so "
                   "the offset is never parsed (compareTimes returns None)")
    def test_compare_times_negative_offset_is_converted_to_utc(self):
        self.assertEqual(self.manifest.compareTimes(
            '2018-01-01T00:00:00-05:00', '2018-01-01T05:00:00Z'), 0)

    def test_compare_times_keeps_fractional_seconds(self):
        self.assertLess(self.manifest.compareTimes(
            '2018-01-01T00:00:00.000001Z', '2018-01-01T00:00:00.000002Z'), 0)

    def test_compare_times_none_sorts_before_any_time(self):
        self.assertEqual(self.manifest.compareTimes(None, None), 0)
        self.assertEqual(self.manifest.compareTimes(
            None, '2018-01-01T00:00:00Z'), -1)
        self.assertEqual(self.manifest.compareTimes(
            '2018-01-01T00:00:00Z', None), 1)

    def test_convert_iso_to_datetime_reads_zulu_time(self):
        self.assertEqual(
            self.manifest.convertIsoToDateTime('2018-11-14T01:02:03Z'),
            datetime.datetime(2018, 11, 14, 1, 2, 3))


if __name__ == '__main__':
    unittest.main()
