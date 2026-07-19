"""`verify` command integration tests: real SHA-256 checks against a local backend."""

from __future__ import annotations

import time
from pathlib import Path

from backuper.catalog import Catalog
from backuper.config import load_config


def _sole_artifact(dest_dir):
    tar_files = [p for p in dest_dir.iterdir() if ".tar" in p.name and not p.name.endswith(".sha256")]
    assert len(tar_files) == 1
    return tar_files[0]


def test_verify_on_empty_catalog_reports_nothing_to_verify(make_config, run_cli):
    # A catalog that exists but has zero chains (distinct from no catalog at
    # all, which raises CatalogError instead) — pre-seed one directly.
    config_path = make_config(logging={"level": "info"})
    cfg = load_config(str(config_path))
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    Catalog(prefix=cfg.archive.name_prefix).save(cfg.state_dir)

    result = run_cli("-c", str(config_path), "verify")
    assert result.code == 0
    assert "nothing to verify" in result.err


def test_verify_all_ok_after_clean_backup(make_config, run_cli):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")
    result = run_cli("-c", str(config_path), "verify")
    assert result.code == 0


def test_verify_corrupted_artifact_reports_corrupt_exit_3(make_config, run_cli, tmp_path):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")

    artifact = _sole_artifact(tmp_path / "dest")
    artifact.write_bytes(b"corrupted-garbage-bytes")

    result = run_cli("-c", str(config_path), "verify")
    assert result.code == 3
    assert "CORRUPT" in result.err


def test_verify_missing_artifact_reports_missing_exit_3(make_config, run_cli, tmp_path):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")

    artifact = _sole_artifact(tmp_path / "dest")
    artifact.unlink()

    result = run_cli("-c", str(config_path), "verify")
    assert result.code == 3
    assert "MISSING" in result.err


def test_verify_all_flag_checks_older_chains_default_only_latest(make_config, run_cli):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup", "--full")  # older chain
    time.sleep(1.1)  # chain ids have 1-second resolution
    run_cli("-c", str(config_path), "backup", "--full")  # latest chain

    cfg = load_config(str(config_path))
    cat = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    assert len(cat.chains) == 2
    older_artifact = cat.chains[0].backups[0].artifact
    dest_dir = Path(cfg.destinations[0]["path"])
    (dest_dir / older_artifact).write_bytes(b"corrupted")

    latest_only = run_cli("-c", str(config_path), "verify")
    assert latest_only.code == 0  # default scope doesn't touch the older chain

    all_result = run_cli("-c", str(config_path), "verify", "--all")
    assert all_result.code == 3
