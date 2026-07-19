"""Compressor command-construction tests (compression.py) — hermetic, no real binaries."""

from __future__ import annotations

import pytest

from backuper import compression
from backuper.config import ArchiveConfig
from backuper.errors import ConfigError


def _archive(**overrides) -> ArchiveConfig:
    defaults = dict(
        name_prefix="backup",
        compression="xz",
        level=9,
        extreme=False,
        ultra=False,
        long=False,
        threads=0,
        tar_binary="auto",
    )
    defaults.update(overrides)
    return ArchiveConfig(**defaults)


@pytest.fixture(autouse=True)
def _fake_require_binary(monkeypatch):
    monkeypatch.setattr(compression, "require_binary", lambda name, hint="": f"/usr/bin/{name}")


def test_compressor_stage_none():
    cmd, ext = compression.compressor_stage(_archive(compression="none"))
    assert cmd is None
    assert ext == ""


def test_compressor_stage_xz_defaults():
    cmd, ext = compression.compressor_stage(_archive(compression="xz", level=9, threads=4))
    assert cmd == ["/usr/bin/xz", "-z", "-c", "-9", "-T4"]
    assert ext == ".xz"


def test_compressor_stage_xz_extreme_appends_flag():
    cmd, _ = compression.compressor_stage(_archive(compression="xz", extreme=True))
    assert cmd[-1] == "-e"


def test_compressor_stage_zstd_defaults():
    cmd, ext = compression.compressor_stage(_archive(compression="zstd", level=19, threads=0))
    assert cmd == ["/usr/bin/zstd", "-z", "-c", "-19", "-T0"]
    assert ext == ".zst"


def test_compressor_stage_zstd_ultra_and_long_flags():
    cmd, _ = compression.compressor_stage(_archive(compression="zstd", ultra=True, long=True))
    assert "--ultra" in cmd
    assert "--long=31" in cmd


def test_compressor_stage_gzip_defaults():
    cmd, ext = compression.compressor_stage(_archive(compression="gzip", level=6))
    assert cmd == ["/usr/bin/gzip", "-c", "-6"]
    assert ext == ".gz"


def test_compressor_stage_unknown_algorithm_raises():
    with pytest.raises(ConfigError):
        compression.compressor_stage(_archive(compression="rar"))


def test_decompressor_stage_none_and_empty_string():
    assert compression.decompressor_stage("none") is None
    assert compression.decompressor_stage("") is None


def test_decompressor_stage_xz():
    assert compression.decompressor_stage("xz") == ["/usr/bin/xz", "-d", "-c"]


def test_decompressor_stage_zstd_always_includes_long():
    """zstd decode always passes --long=31 regardless of the encode-time
    `long` flag, since it's harmless on decode and required if it was used."""
    assert compression.decompressor_stage("zstd") == ["/usr/bin/zstd", "-d", "-c", "--long=31"]


def test_decompressor_stage_gzip():
    assert compression.decompressor_stage("gzip") == ["/usr/bin/gzip", "-d", "-c"]


def test_decompressor_stage_unknown_raises():
    with pytest.raises(ConfigError):
        compression.decompressor_stage("rar")
