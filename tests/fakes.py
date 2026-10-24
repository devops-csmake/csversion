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
"""Type-faithful fakes for the boundaries csversion talks to.

Nothing here spawns a process or touches the network.  The subprocess fakes
honour the real API's type contract on purpose: Popen.communicate() and
check_output() hand back bytes unless text mode was asked for
(universal_newlines / text / encoding / errors), and None for a stream that
was not piped.  A fake that returned str regardless would let exactly the
Python 3 bytes-vs-str bugs these tests exist to catch slip through.
"""
import contextlib
import copy
import errno
import io
import logging
import os
import subprocess
import sys
import types
from unittest import mock

from . import support


# ----------------------------------------------------------------------
# subprocess
# ----------------------------------------------------------------------
class Completed(object):
    """What a scripted child process produces.  stdout/stderr may be str or
       bytes; they are converted the way the real API would."""
    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def missingTool(name):
    """What Popen raises when the executable cannot be found."""
    return FileNotFoundError(
        errno.ENOENT, os.strerror(errno.ENOENT), name)


def _textMode(kwargs):
    return bool(kwargs.get('universal_newlines') or kwargs.get('text') or
                kwargs.get('encoding') or kwargs.get('errors'))


def _render(data, kwargs, stream):
    if kwargs.get(stream) != subprocess.PIPE:
        return None
    if _textMode(kwargs):
        if isinstance(data, bytes):
            data = data.decode(
                kwargs.get('encoding') or 'utf-8',
                kwargs.get('errors') or 'strict')
        return data.replace('\r\n', '\n').replace('\r', '\n')
    if isinstance(data, str):
        return data.encode('utf-8')
    return data


class _FakeProcess(object):
    def __init__(self, completed, kwargs):
        self._completed = completed
        self._kwargs = kwargs
        self.returncode = None

    def communicate(self, input=None, timeout=None):
        out = _render(self._completed.stdout, self._kwargs, 'stdout')
        err = _render(self._completed.stderr, self._kwargs, 'stderr')
        self.returncode = self._completed.returncode
        return out, err


class FakeProcesses(object):
    """Scripted subprocess.Popen / subprocess.check_output.

       Each call consumes the next scripted item: a Completed, or an
       exception instance to raise from the call (e.g. missingTool()).
       Every call is recorded in .calls as (args, kwargs)."""
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def _next(self, args, kwargs):
        self.calls.append(types.SimpleNamespace(args=args, kwargs=dict(kwargs)))
        if not self.script:
            raise AssertionError("unscripted subprocess call: %r" % (args,))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def Popen(self, args, **kwargs):
        return _FakeProcess(self._next(args, kwargs), kwargs)

    def check_output(self, *popenargs, **kwargs):
        if 'stdout' in kwargs:
            raise ValueError('stdout argument not allowed, it will be '
                             'overridden.')
        args = popenargs[0] if popenargs else kwargs.get('args')
        completed = self._next(args, kwargs)
        kwargs = dict(kwargs, stdout=subprocess.PIPE)
        out = _render(completed.stdout, kwargs, 'stdout')
        if completed.returncode:
            raise subprocess.CalledProcessError(
                completed.returncode, args, output=out)
        return out


@contextlib.contextmanager
def patchSubprocess(*script):
    fake = FakeProcesses(*script)
    with mock.patch.object(subprocess, 'Popen', fake.Popen), \
         mock.patch.object(subprocess, 'check_output', fake.check_output):
        yield fake


# ----------------------------------------------------------------------
# configparser files
# ----------------------------------------------------------------------
@contextlib.contextmanager
def patchConfigFiles(configs):
    """Make RawConfigParser.read() (and os.path.isfile) see `configs`, a
       {path: ini text} mapping, instead of the filesystem."""
    import configparser

    def read(self, filenames, encoding=None):
        if isinstance(filenames, str):
            filenames = [filenames]
        found = []
        for name in filenames:
            if name in configs:
                self.read_string(configs[name], source=name)
                found.append(name)
        return found

    with mock.patch.object(configparser.RawConfigParser, 'read', read), \
         mock.patch.object(os.path, 'isfile', lambda p: p in configs):
        yield


# ----------------------------------------------------------------------
# the CLI
# ----------------------------------------------------------------------
class KeepOpen(io.StringIO):
    """Output.__del__ closes any stream that is not sys.stdout."""
    def close(self):
        pass


class FakeOpen(object):
    """Stands in for open(path, 'w'): nothing touches the disk."""
    def __init__(self, failWith=None):
        self.failWith = failWith
        self.files = {}
        self.calls = []

    def __call__(self, path, mode='r', *args, **kwargs):
        self.calls.append((path, mode))
        if self.failWith is not None:
            raise self.failWith
        self.files[path] = KeepOpen()
        return self.files[path]

    def text(self, path):
        return self.files[path].getvalue()


class CliResult(object):
    code = None
    stdout = ''
    stderr = ''

    def __init__(self):
        self.chat = []
        self.loaded = []
        self.configDrivers = []

    @property
    def chatText(self):
        return '\n'.join(self.chat)


@contextlib.contextmanager
def cliEnvironment(argv, manifests=None, configs=None, capture=None,
                   dirs=None, outputs=None, logfiles=None):
    """Patch everything the CLI reaches for, yielding a CliResult.

       manifests: {path: manifest dict} the manifest loader will "read"
       configs:   {path: ini text} for --configuration style files
       capture:   fn(manifest) standing in for the csversionfile run
       dirs:      {directory: [*.csversion paths]} for directory manifests
       outputs:   FakeOpen used for --yaml/--json/--xml files
       logfiles:  FakeOpen used for --log

       Patched: argv, logging, stdout and stderr, the manifest and config
       file readers, ConfigDriver, directory listing and open().  Nothing
       is spawned and the disk is never touched."""
    from Csversion import CliDriver, ConfigDriver
    from Csversion import Csversion as csversion

    manifests = manifests or {}
    configs = configs or {}
    dirs = dirs or {}
    result = CliResult()
    result.outputs = outputs if outputs is not None else FakeOpen()
    result.logfiles = logfiles if logfiles is not None else FakeOpen()
    stdout, stderr = KeepOpen(), KeepOpen()
    loggers = {}

    def getLogger(name=None):
        if name not in loggers:
            loggers[name] = mock.MagicMock(
                spec=logging.Logger, name='logger:%s' % name)
        return loggers[name]
    result.getLogger = getLogger

    def chat(self, text, cr=True):
        result.chat.append(text)

    def loadManifest(self, filepath):
        result.loaded.append(filepath)
        if filepath not in manifests:
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), filepath)
        self.update(copy.deepcopy(manifests[filepath]))
        self._translateOldToNewProduct()

    def glob(pattern):
        for directory, files in dirs.items():
            if pattern == os.path.join(directory, '*.csversion'):
                return list(files)
        return []

    class FakeConfigDriver(object):
        def __init__(self, configfiles, log, manifest):
            self.record = types.SimpleNamespace(
                configs=configfiles, log=log, manifest=manifest,
                executed=False)
            result.configDrivers.append(self.record)

        def execute(self):
            self.record.executed = True
            if capture is not None:
                capture(self.record.manifest)

    with contextlib.ExitStack() as stack:
        enter = stack.enter_context
        enter(mock.patch.object(sys, 'argv', ['csversion'] + list(argv)))
        result.basicConfig = enter(mock.patch.object(logging, 'basicConfig'))
        enter(mock.patch.object(logging, 'getLogger', getLogger))
        result.critical = enter(mock.patch.object(logging, 'critical'))
        result.exception = enter(mock.patch.object(logging, 'exception'))
        result.error = enter(mock.patch.object(logging, 'error'))
        result.warning = enter(mock.patch.object(logging, 'warning'))
        enter(mock.patch.object(csversion, 'stdout', stdout))
        enter(mock.patch.object(CliDriver, 'stderr', stderr))
        enter(mock.patch.object(
            csversion, 'open', result.outputs, create=True))
        enter(mock.patch.object(
            CliDriver, 'open', result.logfiles, create=True))
        enter(mock.patch.object(CliDriver.CliDriver, 'chat', chat))
        enter(mock.patch.object(
            csversion.Manifest, 'loadManifest', loadManifest))
        enter(mock.patch.object(ConfigDriver, 'ConfigDriver',
                                FakeConfigDriver))
        enter(mock.patch.object(os.path, 'isdir', lambda p: p in dirs))
        enter(mock.patch.object(csversion.glob, 'glob', glob))
        enter(patchConfigFiles(configs))
        try:
            yield result
        finally:
            result.stdout = stdout.getvalue()
            result.stderr = stderr.getvalue()


def _exitCode(result, main):
    try:
        main()
    except SystemExit as e:
        result.code = e.code
    else:
        result.code = 'did not exit'


def runCli(argv, **environment):
    """Run `csversion <argv>` in-process; see cliEnvironment."""
    from Csversion import Csversion as csversion
    with cliEnvironment(argv, **environment) as result:
        cli = csversion.CsversionCli(
            copy.deepcopy(support.loadScript()['CSVERSION_SETTINGS']),
            'csversion', '1.2.3')
        _exitCode(result, cli.main)
        result.cli = cli
        result.log = result.getLogger('Csversion.Csversion.CsversionCli')
    return result


def runModule(name, argv, **environment):
    """Run `python -m <name> <argv>` in-process (runpy, no subprocess)."""
    import runpy
    with cliEnvironment(argv, **environment) as result:
        _exitCode(result, lambda: runpy.run_module(name, run_name='__main__'))
    return result
