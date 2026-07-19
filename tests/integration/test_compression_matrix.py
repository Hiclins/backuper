"""Compression algorithm matrix: real xz/zstd/gzip/none roundtrips."""

from __future__ import annotations

import shutil

import pytest

from backuper.config import COMPRESSION_EXT
from helpers import assert_tree_equal

_MAGIC = {
    "xz": b"\xfd7zXZ\x00",
    "zstd": b"\x28\xb5\x2f\xfd",
    "gzip": b"\x1f\x8b",
}


def _artifact_path(dest_dir):
    tar_files = [p for p in dest_dir.iterdir() if ".tar" in p.name and not p.name.endswith(".sha256")]
    assert len(tar_files) == 1, f"expected exactly one artifact, found {tar_files}"
    return tar_files[0]


@pytest.mark.parametrize("algo", ["xz", "zstd", "gzip", "none"])
def test_compression_algo_roundtrip(algo, make_config, source_tree, run_cli, tmp_path):
    binary_map = {"xz": "xz", "zstd": "zstd", "gzip": "gzip", "none": None}
    needed = binary_map[algo]
    if needed and shutil.which(needed) is None:
        pytest.skip(f"{needed} not installed")

    config_path = make_config(archive={"compression": algo, "level": 3})
    result = run_cli("-c", str(config_path), "backup")
    assert result.code == 0

    dest_dir = tmp_path / "dest"
    artifact = _artifact_path(dest_dir)
    assert artifact.name.endswith(".tar" + COMPRESSION_EXT[algo])

    if algo in _MAGIC:
        with open(artifact, "rb") as fh:
            header = fh.read(8)
        assert header.startswith(_MAGIC[algo])

    restore_dest = tmp_path / "restored"
    restore_result = run_cli(
        "-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest)
    )
    assert restore_result.code == 0
    assert_tree_equal(source_tree, restore_dest)


def test_zstd_ultra_and_long_high_level_roundtrip(make_config, source_tree, run_cli, tmp_path):
    if shutil.which("zstd") is None:
        pytest.skip("zstd not installed")
    config_path = make_config(
        archive={"compression": "zstd", "level": 20, "ultra": True, "long": True}
    )
    result = run_cli("-c", str(config_path), "backup")
    assert result.code == 0

    restore_dest = tmp_path / "restored"
    restore_result = run_cli(
        "-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest)
    )
    assert restore_result.code == 0
    assert_tree_equal(source_tree, restore_dest)


def test_xz_extreme_roundtrip(make_config, source_tree, run_cli, tmp_path):
    if shutil.which("xz") is None:
        pytest.skip("xz not installed")
    config_path = make_config(archive={"compression": "xz", "level": 6, "extreme": True})
    result = run_cli("-c", str(config_path), "backup")
    assert result.code == 0

    restore_dest = tmp_path / "restored"
    restore_result = run_cli(
        "-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest)
    )
    assert restore_result.code == 0
    assert_tree_equal(source_tree, restore_dest)
