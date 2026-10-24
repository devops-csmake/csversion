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
"""Joining several manifests (subsuming older versions) and diffing them.

All in memory: Manifest accepts already-loaded dicts as `preprocessed`.
"""
import copy
import itertools
import unittest

from . import support

if support.yaml is None:
    raise unittest.SkipTest("PyYAML is not installed")

from Csversion.Csversion import DiffProcessor
from Csversion.Csversion import Manifest


def snapshot(version, date, libversion, extra=None):
    """A captured manifest of product `prod` at one version."""
    data = {
        'product': {
            'metadata': {'prod': {'name': 'prod', 'version-full': version}},
            'build': {'prod': {'time': date}}},
        'sources': {
            'libfoo': {'prod': {'pip': {'__global': {
                'PACKAGE': 'libfoo', 'VERSION': libversion}}}},
            'stable': {'prod': {'pip': {'__global': {
                'PACKAGE': 'stable', 'VERSION': '1'}}}}}}
    if extra:
        data['sources'].update(extra)
    return data


NEWLIB = {'newlib': {'prod': {'pip': {'__global': {
    'PACKAGE': 'newlib', 'VERSION': '9.9'}}}}}

V100 = snapshot('1.0.0', '2018-01-01T00:00:00Z', '1.0')
V110 = snapshot('1.1.0', '2018-02-01T00:00:00Z', '1.1')
V120 = snapshot('1.2.0', '2018-03-01T00:00:00Z', '1.2', NEWLIB)


def join(*snapshots):
    return Manifest([], copy.deepcopy(list(snapshots)), log=support.mockLog())


def libfoo(diff):
    entry = diff['diff']['sources']['libfoo']['prod']

    def version(side):
        return entry[side].get('pip', {}).get('__global', {}).get('VERSION')
    return version('old'), version('new')


def productVersions(diff):
    entry = diff['diff']['product']['metadata']['prod']
    return entry['old'].get('version-full'), entry['new'].get('version-full')


class JoinTests(unittest.TestCase):
    def test_join_keeps_the_newest_values(self):
        manifest = join(V100, V110)
        prod = manifest['product']['metadata']['prod']
        self.assertEqual(prod['version-full'], '1.1.0')
        self.assertEqual(
            manifest['sources']['libfoo']['prod']['pip']['__global']
            ['VERSION'], '1.1')

    def test_join_stashes_the_older_version_by_version_and_time(self):
        prod = join(V100, V110)['product']['metadata']['prod']
        self.assertEqual(
            prod['__older'],
            {'1.0.0__2018-01-01T00:00:00Z': {
                'name': 'prod', 'version-full': '1.0.0'}})

    def test_join_stashes_every_older_version(self):
        prod = join(V100, V110, V120)['product']['metadata']['prod']
        self.assertEqual(prod['version-full'], '1.2.0')
        self.assertEqual(sorted(prod['__older']),
                         ['1.0.0__2018-01-01T00:00:00Z',
                          '1.1.0__2018-02-01T00:00:00Z'])

    def test_join_result_does_not_depend_on_manifest_order(self):
        expected = dict(join(V100, V110, V120))
        for order in itertools.permutations([V100, V110, V120]):
            with self.subTest(order=[s['product']['metadata']['prod']
                                     ['version-full'] for s in order]):
                self.assertEqual(dict(join(*order)), expected)

    def test_join_stashes_older_package_data_under_the_package_tag(self):
        older = join(V100, V110)['sources']['libfoo']['prod']['__older']
        self.assertEqual(
            older['1.0.0__2018-01-01T00:00:00Z']['pip']['__global']['VERSION'],
            '1.0')

    def test_join_unversioned_manifests_are_merged_without_stashing(self):
        manifest = join({'extra': {'part': {'tag': {'a': 1}}}},
                        {'more': {'part': {'tag': {'b': 2}}}})
        self.assertEqual(sorted(manifest), ['extra', 'more'])
        self.assertNotIn('__older', manifest['extra']['part']['tag'])

    def test_join_single_manifest_is_copied_as_is(self):
        self.assertEqual(dict(join(V100)), V100)

    def test_get_product_tags_of_empty_manifest_logs_what_is_missing(self):
        log = support.mockLog()
        self.assertEqual(Manifest([], log=log).getProductTags(), {})
        self.assertEqual(log.info.call_count, 3)


class DiffTests(unittest.TestCase):
    def test_diff_defaults_to_the_oldest_manifest_as_baseline(self):
        diff = join(V100, V110, V120).diffManifest(DiffProcessor())
        self.assertEqual(libfoo(diff), ('1.0', '1.2'))
        self.assertEqual(productVersions(diff), ('1.0.0', '1.2.0'))

    def test_diff_reports_only_what_changed(self):
        diff = join(V100, V110).diffManifest(DiffProcessor())
        self.assertNotIn('stable', diff['diff']['sources'])

    def test_diff_package_added_since_the_baseline_has_an_empty_old(self):
        diff = join(V100, V110, V120).diffManifest(DiffProcessor())
        entry = diff['diff']['sources']['newlib']['prod']
        self.assertEqual(entry['old'], {})
        self.assertEqual(entry['new']['pip']['__global']['VERSION'], '9.9')

    def test_diff_new_side_never_contains_the_older_stash(self):
        diff = join(V100, V110, V120).diffManifest(DiffProcessor())
        for part in diff['diff'].values():
            for tags in part.values():
                for entry in tags.values():
                    self.assertNotIn('__older', entry['new'])

    def test_diff_is_the_same_whatever_order_the_manifests_were_given(self):
        expected = join(V100, V110, V120).diffManifest(DiffProcessor())
        for order in itertools.permutations([V100, V110, V120]):
            with self.subTest(order=[s['product']['metadata']['prod']
                                     ['version-full'] for s in order]):
                self.assertEqual(join(*order).diffManifest(DiffProcessor()),
                                 expected)

    def test_diff_version_uses_that_manifest_as_the_baseline(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificVersion='1.1.0')
        self.assertEqual(libfoo(diff), ('1.1', '1.2'))
        self.assertEqual(productVersions(diff), ('1.1.0', '1.2.0'))

    def test_diff_version_of_the_oldest_manifest_works_too(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificVersion='1.0.0')
        self.assertEqual(libfoo(diff), ('1.0', '1.2'))

    def test_diff_unknown_version_treats_everything_as_new(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificVersion='9.9.9')
        self.assertEqual(libfoo(diff), (None, '1.2'))
        self.assertEqual(productVersions(diff), (None, '1.2.0'))

    def test_diff_date_uses_the_oldest_manifest_at_or_after_the_date(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificDate='2018-01-15T00:00:00Z')
        self.assertEqual(libfoo(diff), ('1.1', '1.2'))

    def test_diff_date_exactly_on_a_manifest_includes_it(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificDate='2018-02-01T00:00:00Z')
        self.assertEqual(libfoo(diff), ('1.1', '1.2'))

    def test_diff_date_before_every_manifest_uses_the_oldest(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificDate='2017-01-01T00:00:00Z')
        self.assertEqual(libfoo(diff), ('1.0', '1.2'))

    def test_diff_date_after_every_older_manifest_treats_everything_as_new(
            self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificDate='2018-02-15T00:00:00Z')
        self.assertEqual(libfoo(diff), (None, '1.2'))

    def test_diff_version_and_date_must_both_match(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), specificVersion='1.0.0',
            specificDate='2018-01-15T00:00:00Z')
        self.assertEqual(libfoo(diff), (None, '1.2'))

    def test_diff_latest_only_uses_the_previous_manifest(self):
        diff = join(V100, V110, V120).diffManifest(
            DiffProcessor(), latestOnly=True)
        self.assertEqual(libfoo(diff), ('1.1', '1.2'))
        self.assertEqual(productVersions(diff), ('1.1.0', '1.2.0'))

    def test_diff_latest_only_with_nothing_older_treats_everything_as_new(
            self):
        diff = join(V120).diffManifest(DiffProcessor(), latestOnly=True)
        self.assertEqual(libfoo(diff), (None, '1.2'))

    def test_diff_of_a_single_manifest_treats_everything_as_new(self):
        diff = join(V110).diffManifest(DiffProcessor())
        self.assertEqual(libfoo(diff), (None, '1.1'))
        self.assertEqual(sorted(diff['diff']['sources']),
                         ['libfoo', 'stable'])

    def test_diff_calls_the_handler_registered_for_a_changed_tag(self):
        calls = []
        processor = DiffProcessor()
        processor.registerHandler(('sources', 'libfoo', 'prod'), calls.append)
        diff = join(V100, V110).diffManifest(processor)
        self.assertEqual(calls, [diff['diff']['sources']['libfoo']['prod']])

    def test_diff_does_not_call_handlers_for_unchanged_tags(self):
        calls = []
        processor = DiffProcessor()
        processor.registerHandler(('sources', 'stable', 'prod'), calls.append)
        join(V100, V110).diffManifest(processor)
        self.assertEqual(calls, [])


class CompareTagDictTests(unittest.TestCase):
    def setUp(self):
        self.compare = Manifest([]).compareTagDict

    def test_compare_tag_dict_equal_dicts_match(self):
        self.assertTrue(self.compare({'a': {'b': '1'}}, {'a': {'b': '1'}}))

    def test_compare_tag_dict_ignores_the_older_stash(self):
        self.assertTrue(self.compare({'a': '1', '__older': {'x': 1}},
                                     {'a': '1'}))

    def test_compare_tag_dict_changed_value_does_not_match(self):
        self.assertFalse(self.compare({'a': {'b': '1'}}, {'a': {'b': '2'}}))

    def test_compare_tag_dict_missing_key_does_not_match(self):
        self.assertFalse(self.compare({'a': '1'}, {}))

    def test_compare_tag_dict_different_types_do_not_match(self):
        self.assertFalse(self.compare({'a': '1'}, ['a']))


class DiffProcessorTests(unittest.TestCase):
    def test_do_handler_calls_the_exact_path_handler(self):
        processor = DiffProcessor()
        processor.registerHandler(('a', 'b'), lambda data: ('handled', data))
        self.assertEqual(processor.doHandler(('a', 'b'), 7), ('handled', 7))

    def test_do_handler_falls_back_to_a_wildcard_segment(self):
        processor = DiffProcessor()
        processor.registerHandler(('a', '*'), lambda data: 'wild')
        self.assertEqual(processor.doHandler(('a', 'anything'), 7), 'wild')

    def test_do_handler_without_a_handler_returns_false(self):
        self.assertIs(DiffProcessor().doHandler(('a', 'b'), 7), False)


if __name__ == '__main__':
    unittest.main()
