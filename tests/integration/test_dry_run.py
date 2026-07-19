"""`--dry-run` / `-n` flags make zero durable changes."""

from __future__ import annotations

import time


def test_backup_dry_run_makes_no_filesystem_changes(make_config, run_cli, tmp_path):
    config_path = make_config()
    result = run_cli("-c", str(config_path), "backup", "-n")
    assert result.code == 0
    assert "[dry-run] would create:" in result.out
    assert "[dry-run] pipeline:" in result.out
    assert "[dry-run] destinations:" in result.out
    assert "[dry-run] retention:" in result.out

    dest_dir = tmp_path / "dest"
    assert not dest_dir.exists() or list(dest_dir.iterdir()) == []
    state_dir = tmp_path / "state"
    assert not (state_dir / "catalog.json").exists()
    assert not (state_dir / "staging").exists()


def test_prune_dry_run_prints_would_drop_without_deleting(make_config, run_cli):
    loose_config = make_config(_name="loose", retention={"keep_last": 5})
    run_cli("-c", str(loose_config), "backup", "--full")
    time.sleep(1.1)  # chain ids have 1-second resolution
    run_cli("-c", str(loose_config), "backup", "--full")

    strict_config = make_config(
        _name="strict", retention={"keep_last": 1}, logging={"level": "info"}
    )
    result = run_cli("-c", str(strict_config), "prune", "--dry-run")
    assert result.code == 0
    assert "would drop" in result.err

    from backuper.catalog import Catalog
    from backuper.config import load_config

    cfg = load_config(str(loose_config))
    cat = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    assert len(cat.chains) == 2  # untouched


def test_prune_dry_run_nothing_to_prune_message(make_config, run_cli):
    config_path = make_config(retention={"keep_last": 5}, logging={"level": "info"})
    run_cli("-c", str(config_path), "backup")
    result = run_cli("-c", str(config_path), "prune", "--dry-run")
    assert result.code == 0
    assert "nothing to prune" in result.err
