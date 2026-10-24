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
"""Run csversion the way a user does: as a separate python3 process.

Covers the CLI end to end under Python 3: option handling in CliDriver,
configparser based configuration files, a --capture through the real
Setter/Sheller collectors dumped as yaml/json/xml, and --diff over several
manifests.  Everything runs in a temp dir and uses --manifests/--manifests-ignore
so nothing under /etc is read.
"""
import json
import os
import shutil
import tempfile
import unittest

from . import support

if support.yaml is None:
    raise unittest.SkipTest("PyYAML is not installed")

yaml = support.yaml

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

CSVERSIONFILE = """\
[Setter@prod product.metadata]
name = prod
version-full = 1.2.3
version.build = 33

[Sheller@prod product.metadata]
greeting = echo hello
multi = echo one
    echo two
"""


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='csversion-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, name, text):
        return support.writeFile(self.tmp, name, text)

    def test_help_runs_under_python3(self):
        with open(support.CSVERSION) as f:
            shebang = f.readline()
        self.assertTrue(
            shebang.startswith('#!') and 'python3' in shebang, shebang)
        # NOTE: csversion exits 1 even for --help (CliDriver._forceQuiet calls
        # .setLevel on the bound method self.chat); that is independent of
        # the Python 3 port, so only the output is checked here.
        rc, out, err = support.runCsversion(['--help'], self.tmp)
        text = out + err
        self.assertNotIn('Traceback', text)
        for expected in ('Basic Options', '--capture', '--csversionfile',
                         '--manifests', '--stdout'):
            self.assertIn(expected, text)

    def test_driver_module_runs_with_package_relative_imports(self):
        # python3 -m Csversion.testdriver; its CLI defines a help synonym
        rc, out, err = support.runPython(
            ['-m', 'Csversion.testdriver', '--long-help'], support.REPO_ROOT)
        self.assertNotIn('Traceback', out + err)
        self.assertIn('Synonyms: --xyzzt', out + err)
        rc, out, err = support.runPython(
            ['-m', 'Csversion.testdriver', '--xyzzt'], support.REPO_ROOT)
        self.assertIn('Brief usage', out + err)

    def test_capture_writes_text_in_yaml_json_and_xml(self):
        conf = self.write('capture.csversion', CSVERSIONFILE)
        yamlpath = os.path.join(self.tmp, 'out.yaml')
        jsonpath = os.path.join(self.tmp, 'out.json')
        xmlpath = os.path.join(self.tmp, 'out.xml')
        rc, out, err = support.runCsversion(
            ['--capture', '--csversionfile=' + conf, '--manifests-ignore',
             '--verbose', '--stdout=none', '--yaml=' + yamlpath,
             '--json=' + jsonpath, '--xml=' + xmlpath],
            self.tmp)
        self.assertEqual(rc, 0, out + err)

        with open(yamlpath) as f:
            yamltext = f.read()
        self.assertNotIn('!!binary', yamltext)
        data = yaml.safe_load(yamltext)
        support.assertAllText(self, data)
        self.assertEqual(
            data['product']['metadata']['prod'],
            {'name': 'prod', 'version-full': '1.2.3',
             'version': {'build': '33'}, 'greeting': 'hello',
             'multi': 'one\ntwo'})
        self.assertRegex(
            data['product']['capture']['prod']['time'],
            r'^\d{4}-\d\d-\d\dT[\d:.]+Z$')

        with open(jsonpath) as f:
            self.assertEqual(json.load(f), data)

        with open(xmlpath) as f:
            xmltext = f.read()
        self.assertIn('<greeting>', xmltext)
        self.assertRegex(xmltext, r'<greeting>\s+hello\s+</greeting>')
        self.assertNotIn("b'hello'", xmltext)

    def test_configuration_file_and_json_settings_choose_the_stdout_format(
            self):
        manifest = self.write('v1.csversion', MANIFEST_V1)
        conf = self.write('settings.ini', '[settings]\nstdout = json\n')
        expected = {'version': {'prod': [
            {'name': 'prod', 'version': '1.0.0'}]}}

        rc, out, err = support.runCsversion(
            ['--manifests=' + manifest, '--quiet'], self.tmp)
        self.assertEqual(rc, 0, err)
        self.assertEqual(yaml.safe_load(out), expected)
        with self.assertRaises(ValueError):
            json.loads(out)

        rc, out, err = support.runCsversion(
            ['--manifests=' + manifest, '--quiet', '--configuration=' + conf],
            self.tmp)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), expected)

        rc, out, err = support.runCsversion(
            ['--manifests=' + manifest, '--quiet',
             '--settings={"stdout": "json"}'],
            self.tmp)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), expected)

    def test_diff_of_two_manifests_reports_old_and_new(self):
        v1 = self.write('v1.csversion', MANIFEST_V1)
        v2 = self.write('v2.csversion', MANIFEST_V2)
        for manifests in ((v1, v2), (v2, v1)):
            with self.subTest(manifests=[os.path.basename(m) for m in manifests]):
                rc, out, err = support.runCsversion(
                    ['--manifests=' + ','.join(manifests), '--diff',
                     '--stdout=json', '--quiet'],
                    self.tmp)
                self.assertNotIn('Traceback', err)
                self.assertEqual(rc, 0, err)
                diff = json.loads(out)['diff']
                self.assertEqual(
                    diff['product']['metadata']['prod'],
                    {'old': {'name': 'prod', 'version-full': '1.0.0'},
                     'new': {'name': 'prod', 'version-full': '1.1.0'}})
                libfoo = diff['sources']['libfoo']['prod']
                self.assertEqual(
                    libfoo['old']['pip']['__global']['VERSION'], '1.0')
                self.assertEqual(
                    libfoo['new']['pip']['__global']['VERSION'], '1.1')


if __name__ == '__main__':
    unittest.main()
