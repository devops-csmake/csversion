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
"""CollectDpkgs, with subprocess.Popen replaced by a type-faithful fake.

The fake returns bytes unless text mode was requested, so a collector that
forgets universal_newlines=True blows up here exactly as it would for real.
"""
import subprocess
import unittest

from . import fakes
from . import support
from CsversionModules.CollectDpkgs import CollectDpkgs

QUERY = ["dpkg-query", "--show", "-f",
         "${binary:Package} (${Version}) (${Architecture})\\n"]


def collect(*script, **kwargs):
    """Run the collector against scripted processes.
       Returns (manifest, processes, log)."""
    manifest = {}
    log = support.mockLog()
    with fakes.patchSubprocess(*script) as processes:
        returned = CollectDpkgs(log).csversionPopulateManifest(
            manifest, kwargs.get('options', {}), 'CollectDpkgs', 'prod',
            'sources')
    assert returned is manifest
    return manifest, processes, log


class CollectDpkgsTests(unittest.TestCase):
    def test_collect_dpkgs_runs_dpkg_query_under_sudo(self):
        manifest, processes, log = collect(fakes.Completed(''))
        self.assertEqual(len(processes.calls), 1)
        call = processes.calls[0]
        self.assertEqual(call.args, ["sudo", "-E"] + QUERY)
        self.assertNotIn('shell', call.kwargs)

    def test_collect_dpkgs_asks_for_text_output(self):
        # Without this Popen.communicate() returns bytes under Python 3
        manifest, processes, log = collect(fakes.Completed(''))
        kwargs = processes.calls[0].kwargs
        self.assertTrue(kwargs.get('universal_newlines') or kwargs.get('text'))
        self.assertEqual(kwargs['stdout'], subprocess.PIPE)
        self.assertEqual(kwargs['stderr'], subprocess.PIPE)

    def test_collect_dpkgs_parses_package_version_release_and_arch(self):
        manifest, _, _ = collect(fakes.Completed(
            'bash (5.0-4) (amd64)\n'))
        self.assertEqual(
            manifest,
            {'bash': {'prod': {'dpkg': {'amd64': {
                'PACKAGE': 'bash', 'VERSION': '5.0', 'RELEASE': '4',
                'ARCH': 'amd64'}}}}})
        support.assertAllText(self, manifest)

    def test_collect_dpkgs_drops_arch_qualifier_from_package_name(self):
        manifest, _, _ = collect(fakes.Completed(
            'libc6:amd64 (2.31-0ubuntu9) (amd64)\n'))
        entry = manifest['libc6']['prod']['dpkg']['amd64']
        self.assertEqual(entry['PACKAGE'], 'libc6')
        self.assertEqual(entry['VERSION'], '2.31')
        self.assertEqual(entry['RELEASE'], '0ubuntu9')

    def test_collect_dpkgs_plus_separates_version_from_release(self):
        manifest, _, _ = collect(fakes.Completed(
            'tzdata (2021a+deb10u1) (all)\n'))
        entry = manifest['tzdata']['prod']['dpkg']['all']
        self.assertEqual((entry['VERSION'], entry['RELEASE']),
                         ('2021a', 'deb10u1'))

    def test_collect_dpkgs_empty_arch_is_filed_under_global(self):
        manifest, _, _ = collect(fakes.Completed('foo (1.0-1) ()\n'))
        self.assertEqual(
            manifest['foo']['prod']['dpkg'],
            {'__global': {'PACKAGE': 'foo', 'VERSION': '1.0',
                          'RELEASE': '1'}})

    def test_collect_dpkgs_empty_release_is_omitted(self):
        manifest, _, _ = collect(fakes.Completed('foo (1.0-) (amd64)\n'))
        self.assertNotIn('RELEASE', manifest['foo']['prod']['dpkg']['amd64'])

    def test_collect_dpkgs_keeps_several_packages_and_arches(self):
        manifest, _, _ = collect(fakes.Completed(
            'bash (5.0-4) (amd64)\n'
            'bash (5.0-4) (i386)\n'
            'zlib1g (1.2.11-1) (amd64)\n'))
        self.assertEqual(sorted(manifest), ['bash', 'zlib1g'])
        self.assertEqual(sorted(manifest['bash']['prod']['dpkg']),
                         ['amd64', 'i386'])

    def test_collect_dpkgs_non_ascii_package_names_stay_text(self):
        manifest, _, _ = collect(fakes.Completed(
            'café-data (1.0-1) (all)\n'))
        self.assertIn('café-data', manifest)
        support.assertAllText(self, manifest)

    def test_collect_dpkgs_skips_and_logs_lines_that_do_not_match(self):
        manifest, _, log = collect(fakes.Completed(
            'this is not a package line\n'
            'bash (5.0-4) (amd64)\n'))
        self.assertEqual(sorted(manifest), ['bash'])
        log.debug.assert_any_call("Didn't match: %s",
                                  'this is not a package line')

    def test_collect_dpkgs_blank_output_leaves_manifest_empty(self):
        for output in ('', '\n', '  \n\n'):
            with self.subTest(output=output):
                manifest, _, _ = collect(fakes.Completed(output))
                self.assertEqual(manifest, {})

    def test_collect_dpkgs_duplicate_arch_overwrites_and_logs(self):
        manifest, _, log = collect(fakes.Completed(
            'bash (5.0-4) (amd64)\n'
            'bash (5.1-1) (amd64)\n'))
        self.assertEqual(manifest['bash']['prod']['dpkg']['amd64']['VERSION'],
                         '5.1')
        overwrites = [c for c in log.debug.call_args_list
                      if 'Overwriting' in c[0][0]]
        self.assertEqual(len(overwrites), 1)

    def test_collect_dpkgs_failed_query_yields_no_entries(self):
        manifest, _, _ = collect(fakes.Completed(
            '', 'dpkg-query: command not found\n', returncode=127))
        self.assertEqual(manifest, {})

    def test_collect_dpkgs_missing_sudo_raises_and_adds_nothing(self):
        manifest = {}
        with fakes.patchSubprocess(fakes.missingTool('sudo')):
            with self.assertRaises(FileNotFoundError):
                CollectDpkgs(support.mockLog()).csversionPopulateManifest(
                    manifest, {}, 'CollectDpkgs', 'prod', 'sources')
        self.assertEqual(manifest, {})

    def test_collect_dpkgs_undecodable_output_raises_unicode_error(self):
        # Text mode decodes strictly; a stray non-UTF-8 byte is an error
        # rather than silently producing bytes or mojibake in the manifest
        manifest = {}
        with fakes.patchSubprocess(fakes.Completed(b'bad\xff (1.0-1) (all)\n')):
            with self.assertRaises(UnicodeDecodeError):
                CollectDpkgs(support.mockLog()).csversionPopulateManifest(
                    manifest, {}, 'CollectDpkgs', 'prod', 'sources')
        self.assertEqual(manifest, {})

    def test_collect_dpkgs_docker_option_runs_escaped_query_in_container(self):
        manifest, processes, _ = collect(
            fakes.Completed(''), options={'docker': 'web'})
        self.assertEqual(
            processes.calls[0].args,
            ['sudo', '-E', 'docker', 'exec', '-it', 'web', 'bash', '-c',
             'dpkg-query --show -f '
             '${binary:Package}\\ (${Version})\\ (${Architecture})\\\\\\n'])

    @unittest.skip("pre-existing bug: with the chroot option the query "
                   "command is replaced by [chroot, path] instead of being "
                   "run inside it")
    def test_collect_dpkgs_chroot_option_runs_query_inside_chroot(self):
        manifest, processes, _ = collect(
            fakes.Completed(''), options={'chroot': '/mnt'})
        self.assertEqual(processes.calls[0].args,
                         ['sudo', '-E', 'chroot', '/mnt'] + QUERY)


if __name__ == '__main__':
    unittest.main()
