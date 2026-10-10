"""Test isolation: run everything against a scratch HOME.

Flow stores all its state under ``~/.flow``, with paths resolved at module
import time. Pointing ``HOME`` at a fresh temp dir in *this* conftest (which
pytest imports before any test module) keeps the suite fully isolated: every
``backend.*`` module and the `flow daemon` subprocess (which inherits the env)
reads/writes the scratch tree, never the real ``~/.flow``.
"""

import atexit
import os
import shutil
import tempfile

_TEST_HOME = tempfile.mkdtemp(prefix="flow-tests-")
os.environ["HOME"] = _TEST_HOME
# pathlib.Path.home() reads USERPROFILE (not HOME) on Windows, and HOMEDRIVE/
# HOMEPATH are its fallbacks -- set all three so the scratch tree wins there too.
os.environ["USERPROFILE"] = _TEST_HOME
os.environ["HOMEDRIVE"], os.environ["HOMEPATH"] = os.path.splitdrive(_TEST_HOME)
atexit.register(shutil.rmtree, _TEST_HOME, ignore_errors=True)