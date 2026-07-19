"""Full-vs-incremental decision logic tests (commands/backup.py)."""

from __future__ import annotations

from datetime import datetime

from backuper.catalog import Catalog
from backuper.commands import backup
from backuper.config import load_config
from helpers import StubBackend, make_chain, make_entry


# --------------------------------------------------------------------------- #
# _decide_full
# --------------------------------------------------------------------------- #
def test_no_existing_chain_forces_full(make_config):
    cfg = load_config(str(make_config()))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    need_full, reason = backup._decide_full(cfg, cat, datetime.now(), force=False)
    assert need_full is True
    assert reason == "no existing chain"


def test_force_flag_forces_full(make_config):
    cfg = load_config(str(make_config()))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00")]))
    need_full, reason = backup._decide_full(cfg, cat, datetime.now(), force=True)
    assert need_full is True
    assert reason == "forced full"


def test_count_based_interval_triggers_at_threshold(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": "3i"})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(
        make_chain(
            "c1",
            [make_entry("2026-01-01T00:00:00", level=0), make_entry("2026-01-02T00:00:00", level=3)],
        )
    )
    need_full, reason = backup._decide_full(cfg, cat, datetime(2026, 1, 3), force=False)
    assert need_full is True
    assert "3 incremental" in reason


def test_count_based_interval_not_yet_triggered(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": "3i"})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(
        make_chain(
            "c1",
            [make_entry("2026-01-01T00:00:00", level=0), make_entry("2026-01-02T00:00:00", level=2)],
        )
    )
    need_full, reason = backup._decide_full(cfg, cat, datetime(2026, 1, 3), force=False)
    assert need_full is False


def test_duration_based_interval_triggers(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": "7d"})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00", level=0)]))
    need_full, reason = backup._decide_full(cfg, cat, datetime(2026, 1, 10), force=False)
    assert need_full is True
    assert "older than 7d" in reason


def test_duration_based_interval_not_yet_triggered(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": "7d"})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00", level=0)]))
    need_full, reason = backup._decide_full(cfg, cat, datetime(2026, 1, 3), force=False)
    assert need_full is False


def test_full_on_weekday_match_but_same_day_not_triggered(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": None, "full_on": "sunday"})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-04T08:00:00", level=0)]))  # a Sunday
    now = datetime(2026, 1, 4, 20, 0, 0)  # same Sunday, later
    need_full, reason = backup._decide_full(cfg, cat, now, force=False)
    assert need_full is False


def test_full_on_weekday_match_different_day_triggers(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": None, "full_on": "sunday"})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-04T08:00:00", level=0)]))  # a Sunday
    now = datetime(2026, 1, 11, 8, 0, 0)  # the following Sunday
    need_full, reason = backup._decide_full(cfg, cat, now, force=False)
    assert need_full is True
    assert "scheduled full on sunday" in reason


def test_full_on_wrong_weekday_never_triggers(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": None, "full_on": "sunday"})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-04T08:00:00", level=0)]))
    now = datetime(2026, 1, 5, 8, 0, 0)  # a Monday
    need_full, reason = backup._decide_full(cfg, cat, now, force=False)
    assert need_full is False


def test_full_interval_none_disables_time_and_count_check(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": None})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00", level=0)]))
    need_full, reason = backup._decide_full(cfg, cat, datetime(2030, 1, 1), force=False)
    assert need_full is False


def test_full_interval_empty_string_disables_check(make_config):
    cfg = load_config(str(make_config(mode={"full_interval": ""})))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00", level=0)]))
    need_full, reason = backup._decide_full(cfg, cat, datetime(2030, 1, 1), force=False)
    assert need_full is False


# --------------------------------------------------------------------------- #
# _ensure_snapshot
# --------------------------------------------------------------------------- #
def test_ensure_snapshot_local_present_skips_download(make_config):
    cfg = load_config(str(make_config()))
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "c1.snar").write_text("snap", encoding="utf-8")
    backend = StubBackend("b1")  # empty: would fail if a download were attempted
    assert backup._ensure_snapshot(cfg, [backend], "c1.snar") is True


def test_ensure_snapshot_recovered_from_backend(make_config):
    cfg = load_config(str(make_config()))
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    backend = StubBackend("b1", store={"c1.snar": b"snap-data"})
    assert backup._ensure_snapshot(cfg, [backend], "c1.snar") is True
    assert (cfg.state_dir / "c1.snar").read_bytes() == b"snap-data"


def test_ensure_snapshot_unavailable_returns_false(make_config):
    cfg = load_config(str(make_config()))
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    backend = StubBackend("b1")
    assert backup._ensure_snapshot(cfg, [backend], "missing.snar") is False
