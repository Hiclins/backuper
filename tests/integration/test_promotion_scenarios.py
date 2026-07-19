"""Chain-promotion scenarios: what forces a fresh full backup."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backuper.catalog import Catalog
from backuper.config import load_config


def _chain_count(config_path) -> int:
    cfg = load_config(str(config_path))
    cat = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    return len(cat.chains)


def test_compression_change_promotes_to_new_chain(make_config, run_cli):
    config_path = make_config(archive={"compression": "zstd"})
    run_cli("-c", str(config_path), "backup")
    assert _chain_count(config_path) == 1

    config_path2 = make_config(_name="xz", archive={"compression": "xz"})
    result = run_cli("-c", str(config_path2), "backup")
    assert result.code == 0
    assert _chain_count(config_path2) == 2


@pytest.mark.skipif(shutil.which("age") is None, reason="age not installed")
def test_encryption_toggle_promotes_to_new_chain(make_config, run_cli, age_identity):
    identity, recipient = age_identity
    config_plain = make_config(_name="plain")
    run_cli("-c", str(config_plain), "backup")
    assert _chain_count(config_plain) == 1

    config_enc = make_config(
        _name="enc",
        encryption={"enabled": True, "recipients": [recipient], "identity_file": str(identity)},
    )
    result = run_cli("-c", str(config_enc), "backup")
    assert result.code == 0
    assert _chain_count(config_enc) == 2


def test_missing_local_only_snar_recovers_from_backend_no_promotion(make_config, run_cli):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")  # full
    assert _chain_count(config_path) == 1

    cfg = load_config(str(config_path))
    cat = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    snapshot_name = cat.chains[0].snapshot
    local_snar = cfg.state_dir / snapshot_name
    assert local_snar.is_file()
    local_snar.unlink()  # backend still has a copy from the upload

    result = run_cli("-c", str(config_path), "backup")  # incremental should recover it
    assert result.code == 0
    assert _chain_count(config_path) == 1  # still one chain, not promoted

    cat2 = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    assert len(cat2.chains[0].backups) == 2  # full + one incremental


def test_missing_snar_everywhere_promotes(make_config, run_cli):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")
    assert _chain_count(config_path) == 1

    cfg = load_config(str(config_path))
    cat = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    snapshot_name = cat.chains[0].snapshot
    (cfg.state_dir / snapshot_name).unlink()
    dest_dir = Path(cfg.destinations[0]["path"])
    (dest_dir / snapshot_name).unlink()

    result = run_cli("-c", str(config_path), "backup")
    assert result.code == 0
    assert _chain_count(config_path) == 2


def test_source_outside_pinned_root_promotes(make_config, source_tree, run_cli, tmp_path):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")
    assert _chain_count(config_path) == 1

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "outside.txt").write_text("outside content\n", encoding="utf-8")

    config_path2 = make_config(
        _name="expanded", sources=[str(source_tree / "*"), str(other_dir / "*")]
    )
    result = run_cli("-c", str(config_path2), "backup")
    assert result.code == 0
    assert _chain_count(config_path2) == 2


def test_full_flag_always_forces_new_chain(make_config, run_cli):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")
    assert _chain_count(config_path) == 1

    result = run_cli("-c", str(config_path), "backup", "--full")
    assert result.code == 0
    assert _chain_count(config_path) == 2
