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
"""Manifest loading, version comparison and merging/diffing.

Csversion.Manifest holds the yaml-loaded data and does the work behind
--diff, so these exercise real yaml files on disk and the dict-walking code
(`.items()` loops that mutate neighbouring dicts) end to end.
"""
import shutil
import tempfile
import unittest

from . import support

if support.yaml is None:
    raise unittest.SkipTest("PyYAML is not installed")

yaml = support.yaml
from Csversion.Csversion import DiffProcessor
from Csversion.Csversion import Manifest

MANIFEST_V1 = """\
product:
  metadata:
    prod:
      name: prod
      version-full: 1.0.0
  build:
    prod:
      time: '2018-01-01T00:00:00Z'
sources:
  libfoo:
    prod:
      pip:
        __global:
          PACKAGE: libfoo
          VERSION: '1.0'
"""

MANIFEST_V2 = MANIFEST_V1.replace('1.0.0', '1.1.0').replace(
    '2018-01-01', '2018-02-01').replace("'1.0'", "'1.1'")


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='csversion-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_load_manifest_reads_yaml_with_the_safe_loader(self):
        # A bare yaml.load(f) is a TypeError on modern PyYAML (Loader is
        # required), and the unsafe loaders would construct python objects
        path = support.writeFile(self.tmp, 'v1.csversion', MANIFEST_V1)
        manifest = Manifest([path])
        self.assertEqual(
            manifest['product']['metadata']['prod']['version-full'], '1.0.0')
        self.assertEqual(
            manifest[('sources', 'libfoo', 'prod', 'pip', '__global')],
            {'PACKAGE': 'libfoo', 'VERSION': '1.0'})

        evil = support.writeFile(
            self.tmp, 'evil.csversion',
            'product: !!python/object/apply:os.getcwd []\n')
        with self.assertRaises(yaml.YAMLError):
            Manifest([evil])

    def test_old_style_sources_are_translated_to_the_new_layout(self):
        path = support.writeFile(
            self.tmp, 'old.csversion',
            "sources:\n"
            "  libfoo:\n"
            "    prod_ctx:\n"
            "      - pip\n"
            "      - {PACKAGE: libfoo, VERSION: '1.0'}\n")
        manifest = Manifest([path])
        self.assertEqual(
            manifest['sources'],
            {'libfoo': {'prod': {'pip': {'ctx': {
                'PACKAGE': 'libfoo', 'VERSION': '1.0'}}}}})

    def test_compare_versions_orders_numeric_segments(self):
        compare = Manifest([]).compareVersions
        self.assertLess(compare('1.0.0', '1.1.0'), 0)
        self.assertGreater(compare('1.1.0', '1.0.0'), 0)
        self.assertGreater(compare('1.10.0', '1.9.0'), 0)
        self.assertEqual(compare('1.0.0', '1.0.0'), 0)
        self.assertLess(compare('1.0', '1.0.1'), 0)
        self.assertEqual(compare(None, None), 0)
        self.assertLess(compare(None, '1.0'), 0)
        self.assertGreater(compare('1.0', None), 0)

    def test_compare_versions_does_not_order_none_against_text(self):
        # Python 2 let None sort against anything; Python 3 raises TypeError
        compare = Manifest([]).compareVersions
        self.assertEqual(compare('1.2.rc', '1.2.rc'), 0)
        snapshot = '1.0.1.20181114121212.3f516e0'
        self.assertEqual(compare(snapshot, snapshot), 0)
        self.assertGreater(compare('1.2.rc-1', '1.2.rc'), 0)
        self.assertLess(compare('1.2.rc', '1.2.rc-1'), 0)
        self.assertLess(compare('1.2.rc-1', '1.2.rc-2'), 0)
        self.assertLess(compare('1.2.a', '1.2.b'), 0)

    def test_joining_manifests_keeps_the_newest_and_diff_reports_changes(self):
        v1 = support.writeFile(self.tmp, 'v1.csversion', MANIFEST_V1)
        v2 = support.writeFile(self.tmp, 'v2.csversion', MANIFEST_V2)
        for paths in ([v1, v2], [v2, v1]):
            with self.subTest(order=[p[-12:] for p in paths]):
                manifest = Manifest(paths)
                prod = manifest['product']['metadata']['prod']
                self.assertEqual(prod['version-full'], '1.1.0')
                self.assertEqual(
                    prod['__older'],
                    {'1.0.0__2018-01-01T00:00:00Z': {
                        'name': 'prod', 'version-full': '1.0.0'}})

                calls = []
                processor = DiffProcessor()
                processor.registerHandler(
                    ('sources', 'libfoo', 'prod'), calls.append)
                diff = manifest.diffManifest(processor)['diff']
                libfoo = diff['sources']['libfoo']['prod']
                self.assertEqual(
                    libfoo['old']['pip']['__global']['VERSION'], '1.0')
                self.assertEqual(
                    libfoo['new']['pip']['__global']['VERSION'], '1.1')
                self.assertEqual(calls, [libfoo])
                self.assertNotIn('__older', libfoo['new'])


if __name__ == '__main__':
    unittest.main()
