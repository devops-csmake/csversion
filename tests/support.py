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
"""Shared helpers for the csversion unit tests (not itself a test module)."""
import os
import sys
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

_script = None


def loadScript():
    """Execute the extensionless `csversion` script (without running main)
       and return its namespace; it holds CSVERSION_SETTINGS."""
    global _script
    if _script is None:
        with open(CSVERSION) as f:
            source = f.read()
        namespace = {'__name__': 'csversion_script', '__file__': CSVERSION}
        exec(compile(source, CSVERSION, 'exec', dont_inherit=True), namespace)
        _script = namespace
    return _script


def mockLog():
    """A stand-in for the logger the csversion modules are handed."""
    return mock.Mock(name='log')


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
