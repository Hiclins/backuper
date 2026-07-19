"""Shared fixtures for the whole test suite (unit + integration)."""

from __future__ import annotations

import collections
import copy
import logging
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from backuper.cli import main

CliResult = collections.namedtuple("CliResult", "code out err")


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    """A small, deterministic source tree to back up."""
    src = tmp_path / "src"
    (src / "subdir").mkdir(parents=True)
    (src / "emptydir").mkdir()
    (src / "file1.txt").write_text("hello world\n", encoding="utf-8")
    (src / "subdir" / "file2.txt").write_text("nested content\n", encoding="utf-8")
    (src / "subdir" / ".dotfile").write_text("dotfile in subdir\n", encoding="utf-8")
    (src / ".hidden_file").write_text("top-level dotfile\n", encoding="utf-8")
    return src


@pytest.fixture
def make_config(tmp_path: Path, source_tree: Path):
    """Factory fixture: make_config(**overrides) -> Path to a written backuper.yaml."""

    def _make(**overrides) -> Path:
        config_path = tmp_path / f"backuper-{overrides.pop('_name', 'default')}.yaml"
        default: dict = {
            # A glob of source_tree's direct children (not the directory itself)
            # pins the archive root at source_tree, so restored output lays out
            # directly under --dest and can be compared tree-for-tree against it.
            "sources": [str(source_tree / "*")],
            "state_dir": str(tmp_path / "state"),
            "archive": {"compression": "zstd", "level": 3, "name_prefix": "test"},
            "mode": {"strategy": "incremental", "full_interval": "7d"},
            "encryption": {"enabled": False},
            "destinations": [
                {"type": "local", "name": "local", "path": str(tmp_path / "dest")}
            ],
            "retention": {"keep_last": 3},
            "logging": {"level": "warning"},
        }
        cfg = _deep_merge(default, copy.deepcopy(overrides))
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        return config_path

    return _make


@pytest.fixture
def run_cli(capsys):
    """Invoke backuper.cli.main() in-process and capture exit code + output."""

    def _run(*args: str) -> CliResult:
        code = main(list(args))
        captured = capsys.readouterr()
        return CliResult(code, captured.out, captured.err)

    return _run


@pytest.fixture(autouse=True)
def _reset_logging():
    """Isolate tests from `setup_logging`'s handler-replacement side effects.

    `setup_logging` strips and replaces every root-logger handler on each
    call (including any FileHandler it opened), which both detaches
    pytest's `caplog` handler and can leak file descriptors across tests.
    """
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)


@pytest.fixture
def age_identity(tmp_path: Path):
    """A real age identity file + its recipient public key."""
    if shutil.which("age-keygen") is None:
        pytest.skip("age-keygen not found")
    identity = tmp_path / "age-identity.txt"
    result = subprocess.run(
        ["age-keygen", "-o", str(identity)],
        capture_output=True,
        text=True,
        check=True,
    )
    text = result.stderr + result.stdout
    recipient = None
    for line in text.splitlines():
        if "Public key:" in line:
            recipient = line.split("Public key:")[-1].strip()
    if recipient is None:
        # Fall back to reading it from the identity file's comment header.
        for line in identity.read_text(encoding="utf-8").splitlines():
            if line.startswith("# public key:"):
                recipient = line.split(":", 1)[-1].strip()
    assert recipient, "could not determine age recipient from age-keygen output"
    return identity, recipient
