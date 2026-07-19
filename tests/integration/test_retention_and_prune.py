"""Retention wiring: auto-prune during backup, and the standalone prune command."""

from __future__ import annotations

import time
from pathlib import Path

from backuper.catalog import Catalog
from backuper.config import load_config


def test_backup_auto_prunes_older_chain_with_keep_last_1(make_config, run_cli):
    config_path = make_config(retention={"keep_last": 1})
    run_cli("-c", str(config_path), "backup", "--full")
    time.sleep(1.1)  # chain ids have 1-second resolution; avoid a collision
    run_cli("-c", str(config_path), "backup", "--full")  # a second, unrelated full chain

    cfg = load_config(str(config_path))
    cat = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    # backup.run() applies retention after every successful upload -> the
    # older chain is dropped automatically, without a separate `prune` call.
    assert len(cat.chains) == 1


def test_prune_dry_run_leaves_state_untouched_then_real_run_drops(make_config, run_cli):
    loose_config = make_config(_name="loose", retention={"keep_last": 5})
    run_cli("-c", str(loose_config), "backup", "--full")
    time.sleep(1.1)  # chain ids have 1-second resolution; avoid a collision
    run_cli("-c", str(loose_config), "backup", "--full")

    cfg = load_config(str(loose_config))
    cat = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    assert len(cat.chains) == 2
    old_chain_id = cat.chains[0].id
    old_artifact = cat.chains[0].backups[0].artifact
    old_snapshot = cat.chains[0].snapshot
    dest_dir = Path(cfg.destinations[0]["path"])

    # Same state_dir/destinations, stricter retention.
    strict_config = make_config(_name="strict", retention={"keep_last": 1})

    dry_result = run_cli("-c", str(strict_config), "prune", "--dry-run")
    assert dry_result.code == 0
    cat_after_dry = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    assert len(cat_after_dry.chains) == 2
    assert (dest_dir / old_artifact).is_file()
    assert (cfg.state_dir / old_snapshot).is_file()

    real_result = run_cli("-c", str(strict_config), "prune")
    assert real_result.code == 0
    cat_after_real = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    assert len(cat_after_real.chains) == 1
    assert cat_after_real.chains[0].id != old_chain_id
    assert not (dest_dir / old_artifact).is_file()
    assert not (cfg.state_dir / old_snapshot).exists()
