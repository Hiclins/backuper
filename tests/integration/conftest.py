"""Integration tests invoke real gtar/age/zstd/xz/gzip through the CLI.

The whole directory is skipped at collection time if no GNU tar is available
at all; per-binary skips (age/xz/zstd) live on individual test files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backuper.config import resolve_gnu_tar
from backuper.errors import ToolNotFoundError

try:
    resolve_gnu_tar()
except ToolNotFoundError:
    pytest.skip("GNU tar not found; skipping integration tests", allow_module_level=True)

_THIS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # A module-level `pytestmark` in conftest.py does NOT propagate to sibling
    # test modules (only within the module it's defined in) — this hook is
    # the correct way to tag every test collected under this directory.
    for item in items:
        if _THIS_DIR in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.integration)
