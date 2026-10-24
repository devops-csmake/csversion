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
"""CollectPips, with subprocess.Popen replaced by a type-faithful fake.

CollectPips makes up to three kinds of Popen call: the shell pipeline that
finds virtualenvs, the global `pip freeze`, and one freeze per virtualenv.
Each must ask for text output or the fake (like the real thing) hands back
bytes.
"""
import subprocess
import unittest

from . import fakes
from . import support
from CsversionModules.CollectPips import CollectPips

DELIM = "=-=-=-=-=-=-=-=-="
FIND = "sudo -E find / | grep 'bin/activate_this'"


def venvFreeze(venv):
    return ("sudo -E /bin/bash -c 'source %s/bin/activate; echo %s; "
            "pip freeze; deactivate;'" % (venv, DELIM))


def collect(*script, **kwargs):
    manifest = {}
    log = support.mockLog()
    with fakes.patchSubprocess(*script) as processes:
        returned = CollectPips(log).csversionPopulateManifest(
            manifest, kwargs.get('options', {}), 'CollectPips', 'prod',
            'sources')
    assert returned is manifest
    return manifest, processes, log


def isText(call):
    return bool(call.kwargs.get('universal_newlines') or
                call.kwargs.get('text'))


class CollectPipsGlobalTests(unittest.TestCase):
    def test_collect_pips_runs_pip_freeze_under_sudo(self):
        manifest, processes, _ = collect(fakes.Completed(''))
        self.assertEqual(len(processes.calls), 1)
        self.assertEqual(processes.calls[0].args,
                         ["sudo", "-E", "pip", "freeze"])
        self.assertNotIn('shell', processes.calls[0].kwargs)

    def test_collect_pips_asks_for_text_output(self):
        manifest, processes, _ = collect(fakes.Completed(''))
        kwargs = processes.calls[0].kwargs
        self.assertTrue(isText(processes.calls[0]))
        self.assertEqual(kwargs['stdout'], subprocess.PIPE)
        self.assertEqual(kwargs['stderr'], subprocess.PIPE)

    def test_collect_pips_parses_frozen_requirements_as_global(self):
        manifest, _, _ = collect(fakes.Completed(
            'requests==2.31.0\nPyYAML==6.0.1\n'))
        self.assertEqual(
            manifest['requests'],
            {'prod': {'pip': {'__global': {
                'VENV': '__global', 'PACKAGE': 'requests',
                'VERSION': '2.31.0'}}}})
        self.assertEqual(sorted(manifest), ['PyYAML', 'requests'])
        support.assertAllText(self, manifest)

    def test_collect_pips_skips_and_logs_lines_that_are_not_pinned(self):
        manifest, _, log = collect(fakes.Completed(
            '-e git+https://example.invalid/x.git#egg=x\n'
            'requests==2.31.0\n'))
        self.assertEqual(sorted(manifest), ['requests'])
        log.info.assert_any_call(
            '%s was not recognized from pip freeze',
            '-e git+https://example.invalid/x.git#egg=x')

    def test_collect_pips_blank_output_leaves_manifest_empty(self):
        for output in ('', '\n', '  \n\n'):
            with self.subTest(output=output):
                manifest, _, _ = collect(fakes.Completed(output))
                self.assertEqual(manifest, {})

    def test_collect_pips_duplicate_package_overwrites_and_logs(self):
        manifest, _, log = collect(fakes.Completed(
            'requests==2.30.0\nrequests==2.31.0\n'))
        self.assertEqual(
            manifest['requests']['prod']['pip']['__global']['VERSION'],
            '2.31.0')
        overwrites = [c for c in log.debug.call_args_list
                      if 'Overwriting' in c[0][0]]
        self.assertEqual(len(overwrites), 1)

    def test_collect_pips_non_ascii_package_names_stay_text(self):
        manifest, _, _ = collect(fakes.Completed('café==1.0\n'))
        self.assertIn('café', manifest)
        support.assertAllText(self, manifest)

    def test_collect_pips_failed_freeze_yields_no_entries(self):
        manifest, _, _ = collect(fakes.Completed(
            '', 'sudo: pip: command not found\n', returncode=1))
        self.assertEqual(manifest, {})

    def test_collect_pips_missing_sudo_raises_and_adds_nothing(self):
        manifest = {}
        with fakes.patchSubprocess(fakes.missingTool('sudo')):
            with self.assertRaises(FileNotFoundError):
                CollectPips(support.mockLog()).csversionPopulateManifest(
                    manifest, {}, 'CollectPips', 'prod', 'sources')
        self.assertEqual(manifest, {})

    def test_collect_pips_undecodable_output_raises_unicode_error(self):
        manifest = {}
        with fakes.patchSubprocess(fakes.Completed(b'ba\xffd==1.0\n')):
            with self.assertRaises(UnicodeDecodeError):
                CollectPips(support.mockLog()).csversionPopulateManifest(
                    manifest, {}, 'CollectPips', 'prod', 'sources')
        self.assertEqual(manifest, {})

    def test_collect_pips_does_not_search_for_venvs_by_default(self):
        manifest, processes, _ = collect(fakes.Completed(''))
        self.assertEqual(len(processes.calls), 1)

    def test_collect_pips_find_venvs_must_be_the_word_true(self):
        manifest, processes, _ = collect(
            fakes.Completed(''), options={'find-venvs': 'no'})
        self.assertEqual(len(processes.calls), 1)


class CollectPipsVenvTests(unittest.TestCase):
    def collectVenvs(self, find, *freezes, **kwargs):
        script = [find, fakes.Completed('requests==2.31.0\n')] + list(freezes)
        options = dict(kwargs.get('options', {}), **{'find-venvs': 'True'})
        return collect(*script, options=options)

    def test_collect_pips_find_venvs_pipes_find_through_grep_in_a_shell(self):
        manifest, processes, _ = self.collectVenvs(fakes.Completed(''))
        call = processes.calls[0]
        self.assertEqual(call.args, FIND)
        self.assertIs(call.kwargs['shell'], True)
        self.assertTrue(isText(call))

    def test_collect_pips_find_venvs_freezes_each_venv_found(self):
        manifest, processes, _ = self.collectVenvs(
            fakes.Completed('/opt/a/bin/activate_this.py\n'
                            '/srv/b/bin/activate_this.py\n'),
            fakes.Completed('%s\nflask==2.0.1\n' % DELIM),
            fakes.Completed('%s\ndjango==4.2\n' % DELIM))
        self.assertEqual([c.args for c in processes.calls[2:]],
                         [venvFreeze('/opt/a'), venvFreeze('/srv/b')])
        self.assertTrue(all(c.kwargs['shell'] is True
                            for c in processes.calls[2:]))

    def test_collect_pips_find_venvs_asks_for_text_from_every_call(self):
        manifest, processes, _ = self.collectVenvs(
            fakes.Completed('/opt/a/bin/activate_this.py\n'),
            fakes.Completed('%s\nflask==2.0.1\n' % DELIM))
        self.assertEqual(len(processes.calls), 3)
        for call in processes.calls:
            with self.subTest(args=call.args):
                self.assertTrue(isText(call))

    def test_collect_pips_venv_packages_are_filed_under_the_venv_path(self):
        manifest, _, _ = self.collectVenvs(
            fakes.Completed('/opt/a/bin/activate_this.py\n'),
            fakes.Completed('%s\nflask==2.0.1\n' % DELIM))
        self.assertEqual(
            manifest['flask']['prod']['pip'],
            {'/opt/a': {'VENV': '/opt/a', 'PACKAGE': 'flask',
                        'VERSION': '2.0.1'}})
        self.assertEqual(list(manifest['requests']['prod']['pip']),
                         ['__global'])
        support.assertAllText(self, manifest)

    def test_collect_pips_same_package_in_global_and_venv_keeps_both(self):
        manifest, _, _ = self.collectVenvs(
            fakes.Completed('/opt/a/bin/activate_this.py\n'),
            fakes.Completed('%s\nrequests==1.0\n' % DELIM))
        pip = manifest['requests']['prod']['pip']
        self.assertEqual(sorted(pip), ['/opt/a', '__global'])
        self.assertEqual(pip['/opt/a']['VERSION'], '1.0')
        self.assertEqual(pip['__global']['VERSION'], '2.31.0')

    def test_collect_pips_venv_output_before_the_delimiter_is_ignored(self):
        manifest, _, _ = self.collectVenvs(
            fakes.Completed('/opt/a/bin/activate_this.py\n'),
            fakes.Completed('noise==9.9\n%s\nflask==2.0.1\n' % DELIM))
        self.assertNotIn('noise', manifest)
        self.assertIn('flask', manifest)

    def test_collect_pips_venv_output_without_delimiter_yields_nothing(self):
        manifest, _, _ = self.collectVenvs(
            fakes.Completed('/opt/a/bin/activate_this.py\n'),
            fakes.Completed('flask==2.0.1\n'))
        self.assertEqual(sorted(manifest), ['requests'])

    def test_collect_pips_venv_that_fails_is_skipped_and_logged(self):
        manifest, _, log = self.collectVenvs(
            fakes.Completed('/opt/a/bin/activate_this.py\n'
                            '/srv/b/bin/activate_this.py\n'),
            fakes.Completed('', 'activate: no such file\n', returncode=1),
            fakes.Completed('%s\ndjango==4.2\n' % DELIM))
        self.assertNotIn('/opt/a', str(manifest))
        self.assertEqual(
            manifest['django']['prod']['pip']['/srv/b']['VERSION'], '4.2')
        log.info.assert_any_call("Could not get information on %s", '/opt/a')

    def test_collect_pips_failed_venv_search_is_not_fatal(self):
        manifest, processes, log = self.collectVenvs(
            fakes.Completed('', 'find: permission denied\n', returncode=1))
        self.assertEqual(len(processes.calls), 2)
        self.assertEqual(sorted(manifest), ['requests'])
        log.info.assert_any_call("Search for virtual environments failed")

    def test_collect_pips_blank_find_lines_are_ignored(self):
        manifest, processes, _ = self.collectVenvs(
            fakes.Completed('\n  \n/opt/a/bin/activate_this.py\n\n'),
            fakes.Completed('%s\nflask==2.0.1\n' % DELIM))
        self.assertEqual(len(processes.calls), 3)

    def test_collect_pips_missing_sudo_during_venv_search_raises(self):
        with fakes.patchSubprocess(fakes.missingTool('sudo')):
            with self.assertRaises(FileNotFoundError):
                CollectPips(support.mockLog()).csversionPopulateManifest(
                    {}, {'find-venvs': 'true'}, 'CollectPips', 'prod',
                    'sources')


class CollectPipsCommandTests(unittest.TestCase):
    def test_collect_pips_chroot_option_prefixes_the_freeze_command(self):
        manifest, processes, _ = collect(
            fakes.Completed(''), options={'chroot': '/mnt'})
        self.assertEqual(processes.calls[0].args,
                         ['sudo', '-E', 'chroot', '/mnt', 'pip', 'freeze'])

    def test_collect_pips_docker_option_runs_freeze_in_container(self):
        manifest, processes, _ = collect(
            fakes.Completed(''), options={'docker': 'web'})
        self.assertEqual(
            processes.calls[0].args,
            ['sudo', '-E', 'docker', 'exec', '-it', 'web', 'bash', '-c',
             'pip freeze'])

    def test_collect_pips_chroot_inside_docker_nests_the_commands(self):
        manifest, processes, _ = collect(
            fakes.Completed(''),
            options={'chroot': '/mnt', 'docker': 'web'})
        self.assertEqual(
            processes.calls[0].args,
            ['sudo', '-E', 'docker', 'exec', '-it', 'web', 'bash', '-c',
             'chroot /mnt pip freeze'])

    def test_collect_pips_find_venvs_in_chroot_searches_inside_the_chroot(self):
        manifest, processes, _ = collect(
            fakes.Completed('', returncode=1), fakes.Completed(''),
            options={'chroot': '/mnt', 'find-venvs': 'true'})
        self.assertEqual(
            processes.calls[0].args,
            "sudo -E chroot /mnt find / | grep 'bin/activate_this'")


if __name__ == '__main__':
    unittest.main()
