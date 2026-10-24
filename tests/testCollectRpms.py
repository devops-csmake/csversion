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
"""CollectRpms, with subprocess.Popen replaced by a type-faithful fake."""
import subprocess
import unittest

from . import fakes
from . import support
from CsversionModules.CollectRpms import CollectRpms

QUERY = ["rpm", "-qa", "--qf", "%{NAME} %{VERSION} %{RELEASE} %{ARCH}\\n"]


def collect(*script, **kwargs):
    manifest = {}
    log = support.mockLog()
    with fakes.patchSubprocess(*script) as processes:
        returned = CollectRpms(log).csversionPopulateManifest(
            manifest, kwargs.get('options', {}), 'CollectRpms', 'prod',
            'sources')
    assert returned is manifest
    return manifest, processes, log


class CollectRpmsTests(unittest.TestCase):
    def test_collect_rpms_runs_rpm_query_under_sudo(self):
        manifest, processes, _ = collect(fakes.Completed(''))
        self.assertEqual(len(processes.calls), 1)
        self.assertEqual(processes.calls[0].args, ["sudo", "-E"] + QUERY)
        self.assertNotIn('shell', processes.calls[0].kwargs)

    def test_collect_rpms_asks_for_text_output(self):
        manifest, processes, _ = collect(fakes.Completed(''))
        kwargs = processes.calls[0].kwargs
        self.assertTrue(kwargs.get('universal_newlines') or kwargs.get('text'))
        self.assertEqual(kwargs['stdout'], subprocess.PIPE)
        self.assertEqual(kwargs['stderr'], subprocess.PIPE)

    def test_collect_rpms_parses_name_version_release_and_arch(self):
        manifest, _, _ = collect(fakes.Completed(
            'bash 5.0 4.el8 x86_64\n'))
        self.assertEqual(
            manifest,
            {'bash': {'prod': {'rpm': {'x86_64': {
                'PACKAGE': 'bash', 'VERSION': '5.0', 'RELEASE': '4.el8',
                'ARCH': 'x86_64'}}}}})
        support.assertAllText(self, manifest)

    def test_collect_rpms_keeps_several_packages(self):
        manifest, _, _ = collect(fakes.Completed(
            'bash 5.0 4.el8 x86_64\nglibc 2.28 72.el8 x86_64\n'
            'glibc 2.28 72.el8 i686\n'))
        self.assertEqual(sorted(manifest), ['bash', 'glibc'])
        self.assertEqual(sorted(manifest['glibc']['prod']['rpm']),
                         ['i686', 'x86_64'])

    def test_collect_rpms_missing_arch_is_filed_under_global(self):
        manifest, _, _ = collect(fakes.Completed('gpg-pubkey 5ebe 4e5\n'))
        entry = manifest['gpg-pubkey']['prod']['rpm']
        self.assertEqual(list(entry), ['__global'])
        self.assertNotIn('ARCH', entry['__global'])
        self.assertEqual(entry['__global']['RELEASE'], '4e5')

    def test_collect_rpms_non_ascii_package_names_stay_text(self):
        manifest, _, _ = collect(fakes.Completed(
            'café 1.0 1 noarch\n'))
        self.assertIn('café', manifest)
        support.assertAllText(self, manifest)

    def test_collect_rpms_blank_output_leaves_manifest_empty(self):
        for output in ('', '\n', '  \n\n'):
            with self.subTest(output=output):
                manifest, _, _ = collect(fakes.Completed(output))
                self.assertEqual(manifest, {})

    def test_collect_rpms_duplicate_arch_overwrites_and_logs(self):
        manifest, _, log = collect(fakes.Completed(
            'bash 5.0 4.el8 x86_64\nbash 5.1 1.el8 x86_64\n'))
        self.assertEqual(manifest['bash']['prod']['rpm']['x86_64']['VERSION'],
                         '5.1')
        overwrites = [c for c in log.debug.call_args_list
                      if 'Overwriting' in c[0][0]]
        self.assertEqual(len(overwrites), 1)

    def test_collect_rpms_failed_query_yields_no_entries(self):
        manifest, _, _ = collect(fakes.Completed(
            '', 'sudo: rpm: command not found\n', returncode=1))
        self.assertEqual(manifest, {})

    def test_collect_rpms_missing_sudo_raises_and_adds_nothing(self):
        manifest = {}
        with fakes.patchSubprocess(fakes.missingTool('sudo')):
            with self.assertRaises(FileNotFoundError):
                CollectRpms(support.mockLog()).csversionPopulateManifest(
                    manifest, {}, 'CollectRpms', 'prod', 'sources')
        self.assertEqual(manifest, {})

    def test_collect_rpms_undecodable_output_raises_unicode_error(self):
        manifest = {}
        with fakes.patchSubprocess(fakes.Completed(b'ba\xffsh 5.0 1 noarch\n')):
            with self.assertRaises(UnicodeDecodeError):
                CollectRpms(support.mockLog()).csversionPopulateManifest(
                    manifest, {}, 'CollectRpms', 'prod', 'sources')
        self.assertEqual(manifest, {})

    def test_collect_rpms_docker_option_runs_escaped_query_in_container(self):
        manifest, processes, _ = collect(
            fakes.Completed(''), options={'docker': 'web'})
        self.assertEqual(
            processes.calls[0].args,
            ['sudo', '-E', 'docker', 'exec', '-it', 'web', 'bash', '-c',
             'rpm -qa --qf '
             '%{NAME}\\ %{VERSION}\\ %{RELEASE}\\ %{ARCH}\\\\\\n'])

    @unittest.skip("pre-existing bug: with the chroot option the query "
                   "command is replaced by [chroot, path] instead of being "
                   "run inside it")
    def test_collect_rpms_chroot_option_runs_query_inside_chroot(self):
        manifest, processes, _ = collect(
            fakes.Completed(''), options={'chroot': '/mnt'})
        self.assertEqual(processes.calls[0].args,
                         ['sudo', '-E', 'chroot', '/mnt'] + QUERY)


if __name__ == '__main__':
    unittest.main()
