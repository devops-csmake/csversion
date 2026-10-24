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
"""Shared helpers for the csversion tests (not itself a test module)."""
import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSVERSION = os.path.join(REPO_ROOT, 'csversion')

# The packages are plain top-level directories in the repo root
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import yaml
except ImportError:
    yaml = None

requires_yaml = unittest.skipIf(yaml is None, "PyYAML is not installed")

# What csversion's collectors expect from sudo: run the rest of the command.
FAKE_SUDO = 'if [ "$1" = "-E" ]; then shift; fi\nexec "$@"\n'


def quietLogger():
    log = logging.getLogger('csversion-tests')
    log.addHandler(logging.NullHandler())
    log.propagate = False
    return log


def writeFile(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, 'w') as f:
        f.write(text)
    return path


def runPython(args, cwd):
    """Run `python3 args...` as a real subprocess, returning (rc, out, err)
       as text."""
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    p = subprocess.Popen(
        [sys.executable] + list(args),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True)
    out, err = p.communicate()
    return p.returncode, out, err


def runCsversion(args, cwd):
    return runPython([CSVERSION] + list(args), cwd)


@contextlib.contextmanager
def fakeCommands(commands):
    """Put fake executables (name -> /bin/sh script body) first on PATH,
       so the code under test runs real subprocesses against known output
       without needing dpkg, rpm, pip or sudo on the machine."""
    directory = tempfile.mkdtemp(prefix='csversion-fakebin-')
    try:
        for name, body in commands.items():
            path = writeFile(directory, name, '#!/bin/sh\n' + body)
            os.chmod(path, 0o755)
        newpath = directory + os.pathsep + os.environ.get('PATH', '')
        with mock.patch.dict(os.environ, {'PATH': newpath}):
            yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def assertAllText(testcase, item, path='manifest'):
    """Every key and leaf in a manifest must be str (not bytes): bytes
       serialise to yaml as !!binary and break json/xml output."""
    if isinstance(item, dict):
        for key, value in item.items():
            testcase.assertIsInstance(key, str, "%s key %r" % (path, key))
            assertAllText(testcase, value, "%s.%s" % (path, key))
    elif isinstance(item, (list, tuple)):
        for index, value in enumerate(item):
            assertAllText(testcase, value, "%s[%d]" % (path, index))
    else:
        testcase.assertNotIsInstance(item, bytes, path)
        if isinstance(item, str):
            return
        testcase.assertIsInstance(item, (int, float, bool, type(None)), path)
