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
"""Every Python file must compile under the running interpreter.

Catches Python 2 syntax (print statements, 'except X, e', backticks) and
mixed tab/space indentation creeping back in, including in the modules that
no other test happens to import.  The csversion CLI script has no .py
extension but is Python too, so it is checked explicitly.  Compile warnings
are errors here, so an invalid escape sequence in a non-raw regex string
(a DeprecationWarning, then SyntaxWarning, and eventually a SyntaxError in
newer Pythons) is caught too.
"""
import os
import unittest
import warnings

from . import support


def pythonSources():
    for dirpath, dirnames, filenames in os.walk(support.REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__')]
        for name in filenames:
            if name.endswith('.py'):
                yield os.path.join(dirpath, name)
    yield support.CSVERSION


class CompileTests(unittest.TestCase):
    def test_every_python_file_compiles(self):
        count = 0
        for path in sorted(pythonSources()):
            with self.subTest(path=os.path.relpath(path, support.REPO_ROOT)):
                with open(path, 'rb') as f:
                    source = f.read()
                with warnings.catch_warnings():
                    warnings.simplefilter('error', DeprecationWarning)
                    warnings.simplefilter('error', SyntaxWarning)
                    compile(source, path, 'exec', dont_inherit=True)
                count += 1
        self.assertGreater(count, 10)


if __name__ == '__main__':
    unittest.main()
