"""Shared command helpers tests (commands/common.py)."""

from __future__ import annotations

import logging

import pytest

from backuper.backends.local import LocalBackend
from backuper.catalog import CATALOG_NAME, Catalog
from backuper.commands import common
from backuper.config import load_config
from backuper.errors import BackendError, CatalogError
from helpers import StubBackend, make_chain, make_entry


# --------------------------------------------------------------------------- #
# upload_many
# --------------------------------------------------------------------------- #
def test_upload_many_succeeds_to_all(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("1", encoding="utf-8")
    backend1 = LocalBackend(name="b1", path=str(tmp_path / "dest1"))
    backend2 = LocalBackend(name="b2", path=str(tmp_path / "dest2"))
    failures = common.upload_many([backend1, backend2], [(f1, "a.txt")])
    assert failures == {}
    assert (tmp_path / "dest1" / "a.txt").is_file()
    assert (tmp_path / "dest2" / "a.txt").is_file()


def test_upload_many_partial_failure_skips_rest_for_that_backend(tmp_path):
    f1 = tmp_path / "item1"
    f1.write_bytes(b"1")
    f2 = tmp_path / "item2"
    f2.write_bytes(b"2")
    f3 = tmp_path / "item3"
    f3.write_bytes(b"3")

    good = LocalBackend(name="good", path=str(tmp_path / "dest"))
    bad = StubBackend("bad", fail_upload={"item2"})

    failures = common.upload_many(
        [good, bad], [(f1, "item1"), (f2, "item2"), (f3, "item3")]
    )

    assert failures == {"bad": "[bad] upload failed: item2"}
    # good backend received the full set
    assert (tmp_path / "dest" / "item1").is_file()
    assert (tmp_path / "dest" / "item2").is_file()
    assert (tmp_path / "dest" / "item3").is_file()
    # bad backend got item1 (before the failure) but not item2/item3
    assert "item1" in bad.store
    assert "item2" not in bad.store
    assert "item3" not in bad.store


# --------------------------------------------------------------------------- #
# download_any
# --------------------------------------------------------------------------- #
def test_download_any_returns_first_backend_that_has_it(tmp_path):
    b1 = StubBackend("b1")
    b2 = StubBackend("b2", store={"artifact.tar": b"data"})
    dest = tmp_path / "out.tar"
    found = common.download_any([b1, b2], "artifact.tar", dest)
    assert found.name == "b2"
    assert dest.read_bytes() == b"data"


def test_download_any_none_have_it_raises(tmp_path):
    b1 = StubBackend("b1")
    b2 = StubBackend("b2")
    with pytest.raises(BackendError) as excinfo:
        common.download_any([b1, b2], "missing.tar", tmp_path / "out.tar")
    assert "not found in any destination" in str(excinfo.value)


def test_download_any_aggregates_per_backend_errors(tmp_path):
    b1 = StubBackend("b1", fail_exists_error="connection refused")
    with pytest.raises(BackendError) as excinfo:
        common.download_any([b1], "x.tar", tmp_path / "out.tar")
    assert "connection refused" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# delete_from_all
# --------------------------------------------------------------------------- #
def test_delete_from_all_never_raises_only_warns(caplog):
    good = StubBackend("good", store={"a": b"1"})
    bad = StubBackend("bad", store={"a": b"1"}, fail_delete={"a"})
    with caplog.at_level(logging.WARNING):
        common.delete_from_all([good, bad], ["a"])  # must not raise
    assert "a" not in good.store
    assert any("could not delete" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# load_catalog
# --------------------------------------------------------------------------- #
def test_load_catalog_prefers_local_file(tmp_path, make_config):
    config_path = make_config()
    cfg = load_config(str(config_path))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00")]))
    cat.save(cfg.state_dir)

    loaded = common.load_catalog(cfg, backends=[])
    assert [c.id for c in loaded.chains] == ["c1"]


def test_load_catalog_falls_back_to_backend(tmp_path, make_config):
    config_path = make_config()
    cfg = load_config(str(config_path))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00")]))
    import json

    backend = StubBackend(
        "remote", store={CATALOG_NAME: json.dumps(cat.to_dict()).encode("utf-8")}
    )

    loaded = common.load_catalog(cfg, backends=[backend])
    assert [c.id for c in loaded.chains] == ["c1"]


def test_load_catalog_missing_everywhere_raises(tmp_path, make_config):
    config_path = make_config()
    cfg = load_config(str(config_path))
    with pytest.raises(CatalogError):
        common.load_catalog(cfg, backends=[StubBackend("empty")])


# --------------------------------------------------------------------------- #
# chain_object_names
# --------------------------------------------------------------------------- #
def test_chain_object_names_includes_artifact_sidecar_snapshot():
    cat = Catalog(prefix="p")
    chain = make_chain("c1", [make_entry("2026-01-01T00:00:00", artifact="a.tar")])
    cat.add_chain(chain)
    names = common.chain_object_names(cat, {"c1"})
    assert "a.tar" in names
    assert "a.tar.sha256" in names
    assert chain.snapshot in names


def test_chain_object_names_filters_by_chain_ids():
    cat = Catalog(prefix="p")
    cat.add_chain(make_chain("keep", [make_entry("2026-01-01T00:00:00", artifact="keep.tar")]))
    cat.add_chain(make_chain("drop", [make_entry("2026-01-02T00:00:00", artifact="drop.tar")]))
    names = common.chain_object_names(cat, {"drop"})
    assert "drop.tar" in names
    assert "keep.tar" not in names


# --------------------------------------------------------------------------- #
# apply_retention
# --------------------------------------------------------------------------- #
def test_apply_retention_nothing_to_prune_returns_empty_untouched(make_config):
    config_path = make_config(retention={"keep_last": 5})
    cfg = load_config(str(config_path))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T00:00:00")]))
    backend = StubBackend("local")
    result = common.apply_retention(cfg, cat, [backend], dry_run=False)
    assert result == []
    assert backend.deleted == []


def test_apply_retention_dry_run_does_not_touch_backend(make_config):
    config_path = make_config(retention={"keep_last": 1})
    cfg = load_config(str(config_path))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("old", [make_entry("2026-01-01T00:00:00", artifact="old.tar")]))
    cat.add_chain(make_chain("new", [make_entry("2026-01-02T00:00:00", artifact="new.tar")]))
    backend = StubBackend(
        "local", store={"old.tar": b"x", "old.tar.sha256": b"y", "old.snar": b"z"}
    )
    dropped = common.apply_retention(cfg, cat, [backend], dry_run=True)
    assert [c.id for c in dropped] == ["old"]
    assert backend.deleted == []
    assert "old.tar" in backend.store


def test_apply_retention_real_run_deletes_and_rewrites_catalog(make_config):
    config_path = make_config(retention={"keep_last": 1})
    cfg = load_config(str(config_path))
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "old.snar").write_text("snapshot", encoding="utf-8")

    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("old", [make_entry("2026-01-01T00:00:00", artifact="old.tar")]))
    cat.add_chain(make_chain("new", [make_entry("2026-01-02T00:00:00", artifact="new.tar")]))
    backend = StubBackend(
        "local",
        store={
            "old.tar": b"x",
            "old.tar.sha256": b"y",
            "old.snar": b"z",
            CATALOG_NAME: b"{}",
        },
    )

    dropped = common.apply_retention(cfg, cat, [backend], dry_run=False)

    assert [c.id for c in dropped] == ["old"]
    assert "old.tar" not in backend.store
    assert "old.tar.sha256" not in backend.store
    assert "old.snar" not in backend.store
    assert not (cfg.state_dir / "old.snar").exists()
    assert [c.id for c in cat.chains] == ["new"]
    assert (cfg.state_dir / CATALOG_NAME).is_file()
