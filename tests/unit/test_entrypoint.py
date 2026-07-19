"""`python -m backuper` smoke test (__main__.py). No gtar/age dependency."""

from __future__ import annotations

import subprocess
import sys


def test_module_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "backuper", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_module_version_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "backuper", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "backuper" in result.stdout
