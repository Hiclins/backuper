"""Catalog / Chain / BackupEntry tests (catalog.py)."""

from __future__ import annotations

import json

import pytest

from backuper.catalog import CATALOG_NAME, Catalog
from backuper.errors import CatalogError
from helpers import make_chain as _chain
from helpers import make_entry as _entry


# --------------------------------------------------------------------------- #
# BackupEntry / Chain properties
# --------------------------------------------------------------------------- #
def test_backup_entry_time_parses_iso():
    entry = _entry("2026-01-15T10:00:00")
    assert entry.time.year == 2026
    assert entry.time.month == 1
    assert entry.time.day == 15


def test_chain_created_and_end_time_raise_on_empty_backups():
    chain = _chain("empty", [])
    with pytest.raises(IndexError):
        _ = chain.created
    with pytest.raises(IndexError):
        _ = chain.end_time


def test_chain_next_level_empty_is_zero():
    assert _chain("c1", []).next_level == 0


def test_chain_next_level_increments():
    chain = _chain("c1", [_entry("2026-01-01T00:00:00", level=0), _entry("2026-01-02T00:00:00", level=1)])
    assert chain.next_level == 2


def test_chain_total_size_sums():
    chain = _chain("c1", [_entry("2026-01-01T00:00:00", size=100), _entry("2026-01-02T00:00:00", size=250)])
    assert chain.total_size == 350


def test_chain_created_end_time_first_last():
    chain = _chain(
        "c1",
        [
            _entry("2026-01-01T00:00:00", level=0),
            _entry("2026-01-05T00:00:00", level=1),
        ],
    )
    assert chain.created.day == 1
    assert chain.end_time.day == 5


# --------------------------------------------------------------------------- #
# Catalog chain access
# --------------------------------------------------------------------------- #
def test_latest_chain_empty_is_none():
    assert Catalog(prefix="test").latest_chain() is None


def test_latest_chain_returns_last_added():
    cat = Catalog(prefix="test")
    cat.add_chain(_chain("c1", [_entry("2026-01-01T00:00:00")]))
    cat.add_chain(_chain("c2", [_entry("2026-01-02T00:00:00")]))
    assert cat.latest_chain().id == "c2"


def test_remove_chains_returns_removed_and_filters():
    cat = Catalog(prefix="test")
    cat.add_chain(_chain("c1", [_entry("2026-01-01T00:00:00")]))
    cat.add_chain(_chain("c2", [_entry("2026-01-02T00:00:00")]))
    removed = cat.remove_chains({"c1"})
    assert [c.id for c in removed] == ["c1"]
    assert [c.id for c in cat.chains] == ["c2"]


# --------------------------------------------------------------------------- #
# find_chain_for_target
# --------------------------------------------------------------------------- #
def test_find_chain_for_target_empty_catalog():
    assert Catalog(prefix="test").find_chain_for_target("latest") is None


def test_find_chain_for_target_latest():
    cat = Catalog(prefix="test")
    cat.add_chain(_chain("c1", [_entry("2026-01-01T00:00:00", level=0)]))
    cat.add_chain(
        _chain(
            "c2",
            [_entry("2026-01-02T00:00:00", level=0), _entry("2026-01-03T00:00:00", level=1)],
        )
    )
    chain, level = cat.find_chain_for_target("latest")
    assert chain.id == "c2"
    assert level == 1


def test_find_chain_for_target_invalid_iso_raises():
    cat = Catalog(prefix="test")
    cat.add_chain(_chain("c1", [_entry("2026-01-01T00:00:00")]))
    with pytest.raises(CatalogError):
        cat.find_chain_for_target("not-a-date")


def test_find_chain_for_target_before_any_chain_returns_none():
    cat = Catalog(prefix="test")
    cat.add_chain(_chain("c1", [_entry("2026-06-01T00:00:00")]))
    assert cat.find_chain_for_target("2020-01-01T00:00:00") is None


def test_find_chain_for_target_picks_latest_qualifying_chain():
    """When multiple chains both start before the target, the loop keeps
    overwriting `candidate` — the LAST matching chain in catalog order wins,
    not the first."""
    cat = Catalog(prefix="test")
    cat.add_chain(_chain("c1", [_entry("2026-01-01T00:00:00", level=0), _entry("2026-01-02T00:00:00", level=1)]))
    cat.add_chain(_chain("c2", [_entry("2026-01-03T00:00:00", level=0), _entry("2026-01-04T00:00:00", level=1)]))
    chain, level = cat.find_chain_for_target("2026-01-10T00:00:00")
    assert chain.id == "c2"
    assert level == 1


def test_find_chain_for_target_stops_within_chain_at_target_time():
    cat = Catalog(prefix="test")
    cat.add_chain(
        _chain(
            "c1",
            [
                _entry("2026-01-01T00:00:00", level=0),
                _entry("2026-01-02T00:00:00", level=1),
                _entry("2026-01-03T00:00:00", level=2),
            ],
        )
    )
    chain, level = cat.find_chain_for_target("2026-01-02T12:00:00")
    assert chain.id == "c1"
    assert level == 1


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #
def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    cat = Catalog(prefix="test")
    cat.add_chain(_chain("c1", [_entry("2026-01-01T00:00:00")]))
    cat.save(tmp_path)
    assert (tmp_path / CATALOG_NAME).is_file()
    assert not (tmp_path / "catalog.json.tmp").exists()


def test_save_creates_state_dir(tmp_path):
    state_dir = tmp_path / "nested" / "state"
    cat = Catalog(prefix="test")
    cat.save(state_dir)
    assert (state_dir / CATALOG_NAME).is_file()


def test_save_load_roundtrip(tmp_path):
    cat = Catalog(prefix="myprefix")
    cat.add_chain(
        _chain("c1", [_entry("2026-01-01T00:00:00", level=0)], root="/srv", format_version=1)
    )
    cat.save(tmp_path)
    loaded = Catalog.load(tmp_path, "myprefix")
    assert loaded.prefix == "myprefix"
    assert len(loaded.chains) == 1
    assert loaded.chains[0].id == "c1"
    assert loaded.chains[0].root == "/srv"


def test_load_missing_file_returns_fresh_catalog(tmp_path):
    cat = Catalog.load(tmp_path, "prefix")
    assert cat.prefix == "prefix"
    assert cat.chains == []


def test_load_corrupt_json_raises(tmp_path):
    (tmp_path / CATALOG_NAME).write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CatalogError):
        Catalog.load(tmp_path, "prefix")


def test_load_backward_compat_defaults(tmp_path):
    raw = {
        "version": 1,
        "prefix": "old",
        "chains": [
            {
                "id": "c1",
                "snapshot": "c1.snar",
                "backups": [
                    {
                        "timestamp": "2026-01-01T00:00:00",
                        "level": 0,
                        "artifact": "a.tar",
                        "sha256": "a" * 64,
                        "size": 10,
                    }
                ],
                # compression/encrypted/root/format_version deliberately omitted
            }
        ],
    }
    (tmp_path / CATALOG_NAME).write_text(json.dumps(raw), encoding="utf-8")
    cat = Catalog.load(tmp_path, "old")
    chain = cat.chains[0]
    assert chain.compression == "zstd"
    assert chain.encrypted is False
    assert chain.root == "/"
    assert chain.format_version == 1
