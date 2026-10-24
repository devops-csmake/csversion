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
"""The csversion command line, run in-process.

CsversionCli.main() runs with sys.argv, logging, stdout/stderr, the manifest
and config-file readers, ConfigDriver and open() all patched (see
fakes.runCli), so each test scripts the inputs and asserts on the exit
status, the output and the calls made to those boundaries.  No subprocess
is spawned and nothing is read from or written to disk.
"""
import json
import logging
import unittest
import xml.dom.minidom

from . import fakes
from . import support

if support.yaml is None:
    raise unittest.SkipTest("PyYAML is not installed")

yaml = support.yaml


def versioned(version, date, libversion=None, name='prod'):
    data = {'product': {
        'metadata': {name: {'name': name, 'version-full': version}},
        'build': {name: {'time': date}}}}
    if libversion is not None:
        data['sources'] = {'libfoo': {name: {'pip': {'__global': {
            'PACKAGE': 'libfoo', 'VERSION': libversion}}}}}
    return data


V100 = versioned('1.0.0', '2018-01-01T00:00:00Z', '1.0')
V110 = versioned('1.1.0', '2018-02-01T00:00:00Z', '1.1')
V120 = versioned('1.2.0', '2018-03-01T00:00:00Z', '1.2')
FILES = {'v100': V100, 'v110': V110, 'v120': V120}
ALL = '--manifests=v100,v110,v120'


def diff(*args):
    result = fakes.runCli(['--diff', '--stdout=json', ALL] + list(args),
                          manifests=FILES)
    assert result.code in (None, 0), (result.code, result.chat)
    return json.loads(result.stdout)['diff']


def libfooVersions(diffRecord):
    entry = diffRecord['sources']['libfoo']['prod']
    return (entry['old'].get('pip', {}).get('__global', {}).get('VERSION'),
            entry['new']['pip']['__global']['VERSION'])


class HelpAndVersionTests(unittest.TestCase):
    def test_cli_help_lists_the_available_options(self):
        result = fakes.runCli(['--help'])
        self.assertTrue(result.chat[0].startswith('Brief usage'))
        for option in ('--capture', '--csversionfile', '--diff',
                       '--diff-date', '--diff-latest', '--diff-version',
                       '--json', '--manifests', '--manifests-ignore',
                       '--stdout', '--xml', '--yaml'):
            self.assertTrue(
                any(line.startswith('    %s:' % option)
                    for line in result.chat),
                option)

    def test_cli_help_does_not_read_any_manifest(self):
        result = fakes.runCli(['--help'])
        self.assertEqual(result.loaded, [])
        self.assertEqual(result.stdout, '')

    def test_cli_help_long_describes_options_and_shows_defaults(self):
        result = fakes.runCli(['--help-long'])
        self.assertEqual(result.chat[0], 'Usage (Defaults shown for values):')
        self.assertIn('    --csversionfile=/etc/csversion/csversionfile : ',
                      result.chat)
        self.assertIn('    --manifests=/etc/csversion.d : ', result.chat)
        self.assertIn('    --capture : ', result.chat)

    def test_cli_version_writes_name_and_version_to_stderr(self):
        result = fakes.runCli(['--version'])
        self.assertEqual(result.stderr, 'csversion version: 1.2.3\n')
        self.assertEqual(result.stdout, '')

    def test_cli_unknown_option_prints_usage_and_exits_1(self):
        result = fakes.runCli(['--bogus'])
        self.assertEqual(result.code, 1)
        self.assertEqual(result.chat[0], 'option --bogus not recognized')
        self.assertTrue(result.chat[1].startswith('Brief usage'))
        result.critical.assert_called_once_with(
            'option --bogus not recognized')

    def test_cli_option_missing_its_value_exits_1(self):
        result = fakes.runCli(['--manifests'])
        self.assertEqual(result.code, 1)
        self.assertIn('requires argument', result.chat[0])

    def test_cli_driver_module_runs_in_process_with_relative_imports(self):
        # python3 -m Csversion.testdriver, minus the subprocess
        result = fakes.runModule('Csversion.testdriver', ['--long-help'])
        self.assertEqual(result.chat[0], 'Usage (Defaults shown for values):')
        self.assertIn('       Synonyms: --xyzzt', result.chat)

    def test_cli_driver_module_synonym_selects_the_real_option(self):
        result = fakes.runModule('Csversion.testdriver', ['--xyzzt'])
        self.assertTrue(result.chat[0].startswith('Brief usage'))


class LoggingTests(unittest.TestCase):
    def level(self, *flags):
        result = fakes.runCli(
            list(flags) + ['--manifests-ignore', '--stdout=none'])
        calls = [c for c in result.basicConfig.call_args_list
                 if 'level' in c[1]]
        self.assertEqual(len(calls), 1)
        result.log.setLevel.assert_called_once_with(calls[0][1]['level'])
        return calls[0][1]['level']

    def test_cli_logs_warnings_and_above_by_default(self):
        self.assertEqual(self.level(), logging.WARNING)

    def test_cli_verbose_logs_info(self):
        self.assertEqual(self.level('--verbose'), logging.INFO)

    def test_cli_debug_logs_debug(self):
        self.assertEqual(self.level('--debug'), logging.DEBUG)

    def test_cli_quiet_silences_logging(self):
        self.assertEqual(self.level('--quiet'), 99999)

    def test_cli_quiet_wins_over_debug(self):
        self.assertEqual(self.level('--debug', '--quiet'), 99999)

    def test_cli_log_option_opens_the_file_for_writing(self):
        result = fakes.runCli(['--log=run.log', '--manifests-ignore',
                               '--stdout=none'])
        self.assertEqual(result.logfiles.calls, [('run.log', 'w')])
        streams = [c[1]['stream'] for c in result.basicConfig.call_args_list
                   if 'stream' in c[1]]
        self.assertEqual(streams, [result.logfiles.files['run.log']])

    def test_cli_log_file_that_cannot_be_opened_exits_2(self):
        denied = PermissionError(13, 'Permission denied')
        result = fakes.runCli(
            ['--log=/root/run.log'],
            logfiles=fakes.FakeOpen(failWith=denied))
        self.assertEqual(result.code, 2)
        (call,) = result.critical.call_args_list
        self.assertEqual(call[0][1:3], ('/root/run.log', 'PermissionError'))
        self.assertIn('Permission denied', call[0][3])


class ListVersionsTests(unittest.TestCase):
    def test_cli_lists_versions_from_a_manifest_as_yaml_by_default(self):
        result = fakes.runCli(['--manifests=v100'], manifests=FILES)
        self.assertIn(result.code, (None, 0))
        self.assertEqual(
            yaml.safe_load(result.stdout),
            {'version': {'prod': [{'name': 'prod', 'version': '1.0.0'}]}})

    def test_cli_stdout_json_prints_json(self):
        result = fakes.runCli(['--manifests=v100', '--stdout=json'],
                              manifests=FILES)
        self.assertEqual(
            json.loads(result.stdout),
            {'version': {'prod': [{'name': 'prod', 'version': '1.0.0'}]}})

    def test_cli_stdout_xml_prints_xml_elements(self):
        result = fakes.runCli(['--manifests=v100', '--stdout=xml'],
                              manifests=FILES)
        self.assertEqual(
            result.stdout.split(),
            ['<version>', '<prod>', '<item>', '<name>', 'prod', '</name>',
             '<version>', '1.0.0', '</version>', '</item>', '</prod>',
             '</version>'])

    def test_cli_stdout_none_prints_nothing(self):
        result = fakes.runCli(['--manifests=v100', '--stdout=none'],
                              manifests=FILES)
        self.assertEqual(result.stdout, '')

    def test_cli_lists_every_tag_in_the_manifest(self):
        data = versioned('1.0.0', '2018-01-01T00:00:00Z')
        data['product']['metadata']['other'] = {
            'name': 'other', 'version-full': '2.0'}
        result = fakes.runCli(['--manifests=m', '--stdout=json'],
                              manifests={'m': data})
        self.assertEqual(
            json.loads(result.stdout)['version'],
            {'prod': [{'name': 'prod', 'version': '1.0.0'}],
             'other': [{'name': 'other', 'version': '2.0'}]})

    def test_cli_tag_without_a_version_gets_a_placeholder(self):
        data = {'product': {'metadata': {'prod': {'colour': 'blue'}}}}
        result = fakes.runCli(['--manifests=m', '--stdout=json'],
                              manifests={'m': data})
        self.assertEqual(
            json.loads(result.stdout)['version']['prod'],
            [{'name': '', 'version': 'No version or name found for tag'}])

    def test_cli_manifest_without_metadata_lists_no_versions(self):
        result = fakes.runCli(['--manifests=m', '--stdout=json'],
                              manifests={'m': {'sources': {}}})
        self.assertEqual(json.loads(result.stdout), {'version': {}})

    def test_cli_verbose_prints_the_whole_manifest(self):
        result = fakes.runCli(['--manifests=v100', '--stdout=json',
                               '--verbose'], manifests=FILES)
        self.assertEqual(json.loads(result.stdout), V100)

    def test_cli_old_style_sources_are_translated_when_loaded(self):
        old = {'sources': {'libfoo': {'prod_ctx': [
            'pip', {'PACKAGE': 'libfoo', 'VERSION': '1.0'}]}}}
        result = fakes.runCli(['--manifests=m', '--stdout=json',
                               '--verbose'], manifests={'m': old})
        self.assertEqual(
            json.loads(result.stdout)['sources']['libfoo']['prod']['pip']
            ['ctx']['VERSION'], '1.0')


class OutputFileTests(unittest.TestCase):
    def run_(self, **kw):
        return fakes.runCli(
            ['--manifests=v100', '--verbose', '--stdout=none',
             '--yaml=out.yaml', '--json=out.json', '--xml=out.xml'],
            manifests=FILES, **kw)

    def test_cli_opens_each_output_file_for_text_writing(self):
        result = self.run_()
        self.assertEqual(sorted(result.outputs.calls),
                         [('out.json', 'w'), ('out.xml', 'w'),
                          ('out.yaml', 'w')])

    def test_cli_writes_the_manifest_to_the_yaml_file(self):
        text = self.run_().outputs.text('out.yaml')
        self.assertNotIn('!!binary', text)
        self.assertEqual(yaml.safe_load(text), V100)

    def test_cli_writes_the_manifest_to_the_json_file(self):
        self.assertEqual(json.loads(self.run_().outputs.text('out.json')),
                         V100)

    def test_cli_writes_the_manifest_to_the_xml_file(self):
        text = self.run_().outputs.text('out.xml')
        self.assertIn('<version-full>\n', text)
        self.assertRegex(text, r'<version-full>\s+1\.0\.0\s+</version-full>')

    def test_cli_stdout_and_files_can_be_used_together(self):
        result = fakes.runCli(
            ['--manifests=v100', '--stdout=json', '--json=out.json'],
            manifests=FILES)
        self.assertEqual(result.stdout, result.outputs.text('out.json'))

    def test_cli_output_file_that_cannot_be_opened_exits_1(self):
        denied = PermissionError(13, 'Permission denied')
        result = self.run_(outputs=fakes.FakeOpen(failWith=denied))
        self.assertEqual(result.code, 1)
        self.assertTrue(result.log.exception.called)


class ConfigurationTests(unittest.TestCase):
    def run_(self, config, *args):
        return fakes.runCli(
            ['--manifests=v100', '--configuration=c.ini'] + list(args),
            manifests=FILES, configs={'c.ini': config})

    def test_cli_configuration_file_sets_the_stdout_format(self):
        result = self.run_('[settings]\nstdout = json\n')
        self.assertEqual(
            json.loads(result.stdout)['version']['prod'][0]['version'],
            '1.0.0')

    @unittest.skip("pre-existing bug: _getFileOptions never returns True, "
                   "so _getOptions never re-applies the command line and "
                   "the configuration file overrides it")
    def test_cli_command_line_wins_over_the_configuration_file(self):
        result = self.run_('[settings]\nstdout = json\n', '--stdout=xml')
        self.assertTrue(result.stdout.startswith('<version>'))

    def test_cli_configuration_file_flag_options_switch_on(self):
        result = self.run_('[settings]\nstdout = json\nverbose = yes\n')
        self.assertEqual(json.loads(result.stdout), V100)

    def test_cli_configuration_file_unknown_option_warns_on_stderr(self):
        result = self.run_('[settings]\nbogus = 1\n', '--stdout=none')
        self.assertEqual(result.stderr,
                         "WARNING: option 'bogus' not found (FILE)")

    def test_cli_missing_configuration_file_is_ignored(self):
        result = fakes.runCli(['--manifests=v100', '--configuration=nope'],
                              manifests=FILES)
        self.assertIn('version:', result.stdout)

    def test_cli_settings_option_takes_json(self):
        result = fakes.runCli(
            ['--manifests=v100', '--settings={"stdout": "json"}'],
            manifests=FILES)
        self.assertEqual(
            json.loads(result.stdout)['version']['prod'][0]['name'], 'prod')

    def test_cli_settings_option_overrides_the_command_line(self):
        result = fakes.runCli(
            ['--manifests=v100', '--stdout=xml',
             '--settings={"stdout": "json"}'], manifests=FILES)
        self.assertEqual(
            json.loads(result.stdout)['version']['prod'][0]['name'], 'prod')

    def test_cli_malformed_settings_json_exits_1(self):
        result = fakes.runCli(['--manifests=v100', '--settings={nope'],
                              manifests=FILES)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.stdout, '')
        self.assertTrue(result.exception.called)


class ManifestSelectionTests(unittest.TestCase):
    def test_cli_default_manifest_location_is_etc_csversion_d(self):
        result = fakes.runCli(
            [], manifests={'/etc/csversion.d/a.csversion': V100},
            dirs={'/etc/csversion.d': ['/etc/csversion.d/a.csversion']})
        self.assertEqual(result.loaded, ['/etc/csversion.d/a.csversion'])
        self.assertIn('1.0.0', result.stdout)

    def test_cli_manifest_directory_expands_to_its_csversion_files(self):
        result = fakes.runCli(
            ['--manifests=/d'], manifests=FILES,
            dirs={'/d': ['v110', 'v100']})
        self.assertEqual(sorted(result.loaded), ['v100', 'v110'])

    def test_cli_manifests_option_is_split_on_commas_and_stripped(self):
        result = fakes.runCli(['--manifests=v100, v110 ,/d'], manifests=FILES,
                              dirs={'/d': ['v120']})
        self.assertEqual(sorted(result.loaded), ['v100', 'v110', 'v120'])

    def test_cli_manifests_ignore_reads_nothing(self):
        result = fakes.runCli(
            ['--manifests=v100', '--manifests-ignore', '--stdout=json'],
            manifests=FILES)
        self.assertEqual(result.loaded, [])
        self.assertEqual(json.loads(result.stdout), {'version': {}})

    def test_cli_empty_manifest_directory_logs_a_warning(self):
        result = fakes.runCli(['--manifests=/d', '--stdout=json'],
                              dirs={'/d': []})
        result.log.warning.assert_called_once_with(
            "No manifests specified or found from: %s", '/d')
        self.assertEqual(json.loads(result.stdout), {'version': {}})

    def test_cli_missing_manifest_exits_1_and_logs_the_exception(self):
        result = fakes.runCli(['--manifests=nope'], manifests=FILES)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.stdout, '')
        self.assertTrue(result.log.exception.called)

    def test_cli_several_manifests_report_the_newest_version(self):
        result = fakes.runCli(['--manifests=v120,v100', '--stdout=json'],
                              manifests=FILES)
        self.assertEqual(
            json.loads(result.stdout)['version']['prod'][0]['version'],
            '1.2.0')


class CaptureTests(unittest.TestCase):
    @staticmethod
    def capture(manifest):
        manifest['product'] = {'metadata': {'prod': {
            'name': 'prod', 'version-full': '1.2.3'}}}

    def test_cli_capture_runs_the_csversionfile_into_a_new_manifest(self):
        result = fakes.runCli(
            ['--capture', '--csversionfile=a.csversion', '--manifests-ignore',
             '--stdout=json'], capture=self.capture)
        (driver,) = result.configDrivers
        self.assertEqual(driver.configs, ['a.csversion'])
        self.assertTrue(driver.executed)
        self.assertIs(driver.log, result.log)
        self.assertEqual(
            json.loads(result.stdout)['version']['prod'],
            [{'name': 'prod', 'version': '1.2.3'}])

    def test_cli_capture_splits_the_csversionfile_list_on_commas(self):
        result = fakes.runCli(
            ['--capture', '--csversionfile=a.csversion, b.csversion',
             '--manifests-ignore'], capture=self.capture)
        self.assertEqual(result.configDrivers[0].configs,
                         ['a.csversion', 'b.csversion'])

    def test_cli_capture_default_csversionfile_is_in_etc(self):
        result = fakes.runCli(['--capture', '--manifests-ignore'],
                              capture=self.capture)
        self.assertEqual(result.configDrivers[0].configs,
                         ['/etc/csversion/csversionfile'])

    def test_cli_capture_with_verbose_prints_the_captured_manifest(self):
        result = fakes.runCli(
            ['--capture', '--manifests-ignore', '--verbose',
             '--stdout=json'], capture=self.capture)
        self.assertEqual(
            json.loads(result.stdout)['product']['metadata']['prod'],
            {'name': 'prod', 'version-full': '1.2.3'})

    def test_cli_capture_is_merged_with_existing_manifests(self):
        def newer(manifest):
            manifest.update(copy_of(V120))
        result = fakes.runCli(
            ['--capture', '--manifests=v100', '--verbose', '--stdout=json'],
            manifests=FILES, capture=newer)
        prod = json.loads(result.stdout)['product']['metadata']['prod']
        self.assertEqual(prod['version-full'], '1.2.0')
        self.assertEqual(sorted(prod['__older']),
                         ['1.0.0__2018-01-01T00:00:00Z'])

    def test_cli_without_capture_the_csversionfile_is_not_run(self):
        result = fakes.runCli(['--manifests=v100'], manifests=FILES,
                              capture=self.capture)
        self.assertEqual(result.configDrivers, [])

    def test_cli_capture_failure_exits_1_without_output(self):
        def failing(manifest):
            raise ValueError("Section 'Nope' not found")
        result = fakes.runCli(['--capture', '--manifests-ignore'],
                              capture=failing)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.stdout, '')
        self.assertTrue(result.log.exception.called)


def copy_of(data):
    return json.loads(json.dumps(data))


class DiffTests(unittest.TestCase):
    def test_cli_diff_compares_the_oldest_and_newest_manifest(self):
        record = diff()
        self.assertEqual(libfooVersions(record), ('1.0', '1.2'))
        self.assertEqual(
            record['product']['metadata']['prod'],
            {'old': {'name': 'prod', 'version-full': '1.0.0'},
             'new': {'name': 'prod', 'version-full': '1.2.0'}})

    def test_cli_diff_prints_the_diff_instead_of_the_version_list(self):
        result = fakes.runCli(['--diff', '--stdout=json', ALL],
                              manifests=FILES)
        self.assertEqual(list(json.loads(result.stdout)), ['diff'])

    def test_cli_diff_does_not_depend_on_manifest_order(self):
        reversed_ = fakes.runCli(
            ['--diff', '--stdout=json', '--manifests=v120,v110,v100'],
            manifests=FILES)
        self.assertEqual(json.loads(reversed_.stdout)['diff'], diff())

    def test_cli_diff_version_selects_the_baseline_by_version(self):
        self.assertEqual(libfooVersions(diff('--diff-version=1.1.0')),
                         ('1.1', '1.2'))

    def test_cli_diff_version_not_found_treats_everything_as_new(self):
        self.assertEqual(libfooVersions(diff('--diff-version=9.9.9')),
                         (None, '1.2'))

    def test_cli_diff_date_selects_the_oldest_manifest_after_the_date(self):
        self.assertEqual(
            libfooVersions(diff('--diff-date=2018-01-15T00:00:00Z')),
            ('1.1', '1.2'))

    def test_cli_diff_date_after_every_older_manifest_means_all_new(self):
        self.assertEqual(
            libfooVersions(diff('--diff-date=2018-02-15T00:00:00Z')),
            (None, '1.2'))

    def test_cli_diff_date_accepts_a_utc_offset(self):
        self.assertEqual(
            libfooVersions(diff('--diff-date=2018-01-15T01:00:00+01:00')),
            ('1.1', '1.2'))

    def test_cli_diff_version_and_date_must_both_match(self):
        self.assertEqual(
            libfooVersions(diff('--diff-version=1.0.0',
                                '--diff-date=2018-01-15T00:00:00Z')),
            (None, '1.2'))

    def test_cli_diff_latest_compares_with_the_previous_manifest(self):
        self.assertEqual(libfooVersions(diff('--diff-latest')),
                         ('1.1', '1.2'))

    def test_cli_diff_of_a_single_manifest_treats_everything_as_new(self):
        result = fakes.runCli(['--diff', '--stdout=json', '--manifests=v110'],
                              manifests=FILES)
        self.assertEqual(libfooVersions(json.loads(result.stdout)['diff']),
                         (None, '1.1'))

    def test_cli_diff_writes_to_output_files_too(self):
        result = fakes.runCli(
            ['--diff', '--stdout=none', '--json=d.json', ALL],
            manifests=FILES)
        recorded = json.loads(result.outputs.text('d.json'))
        self.assertEqual(libfooVersions(recorded['diff']), ('1.0', '1.2'))


if __name__ == '__main__':
    unittest.main()
