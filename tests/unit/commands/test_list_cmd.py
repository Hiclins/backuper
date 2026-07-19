"""`list` command tests (commands/list_cmd.py)."""

from __future__ import annotations

import argparse

import pytest

from backuper.catalog import Catalog
from backuper.commands import list_cmd
from backuper.config import load_config
from helpers import make_chain, make_entry


# --------------------------------------------------------------------------- #
# _human_size
# --------------------------------------------------------------------------- #
def test_human_size_below_1024_stays_bytes():
    assert list_cmd._human_size(0) == "0.0B"
    assert list_cmd._human_size(1023) == "1023.0B"


def test_human_size_1024_crosses_to_kib():
    assert list_cmd._human_size(1024) == "1.0KiB"


def test_human_size_mib_boundary():
    assert list_cmd._human_size(1024**2) == "1.0MiB"


def test_human_size_gib_boundary():
    assert list_cmd._human_size(1024**3) == "1.0GiB"


def test_human_size_tib_boundary():
    assert list_cmd._human_size(1024**4) == "1.0TiB"


def test_human_size_beyond_tib_caps_at_tib_unit():
    # No PiB unit exists in the loop; huge values stay labelled TiB.
    assert list_cmd._human_size(1024**5) == "1024.0TiB"


# --------------------------------------------------------------------------- #
# run()
# --------------------------------------------------------------------------- #
def test_run_empty_catalog_prints_no_backups(make_config, capsys, monkeypatch):
    cfg = load_config(str(make_config()))
    monkeypatch.setattr(
        list_cmd, "load_catalog", lambda cfg, backends: Catalog(prefix=cfg.archive.name_prefix)
    )
    code = list_cmd.run(cfg, argparse.Namespace())
    assert code == 0
    assert "no backups yet" in capsys.readouterr().out


def test_run_prints_chain_and_entry_lines(make_config, capsys, monkeypatch):
    cfg = load_config(str(make_config()))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    chain = make_chain(
        "c1",
        [
            make_entry("2026-01-01T10:00:00", level=0, artifact="full.tar", size=2048),
            make_entry("2026-01-02T10:00:00", level=1, artifact="incr.tar", size=512),
        ],
        encrypted=True,
    )
    cat.add_chain(chain)
    monkeypatch.setattr(list_cmd, "load_catalog", lambda cfg, backends: cat)

    code = list_cmd.run(cfg, argparse.Namespace())
    assert code == 0
    out = capsys.readouterr().out
    assert "chain c1" in out
    assert "encrypted" in out
    assert "2 backup(s)" in out
    assert "full.tar" in out
    assert "incr.tar" in out
    assert "incr L1" in out
    assert "full" in out


def test_run_plain_compression_shown_when_not_encrypted(make_config, capsys, monkeypatch):
    cfg = load_config(str(make_config()))
    cat = Catalog(prefix=cfg.archive.name_prefix)
    cat.add_chain(make_chain("c1", [make_entry("2026-01-01T10:00:00", level=0)], encrypted=False))
    monkeypatch.setattr(list_cmd, "load_catalog", lambda cfg, backends: cat)

    code = list_cmd.run(cfg, argparse.Namespace())
    assert code == 0
    out = capsys.readouterr().out
    assert "plain" in out
