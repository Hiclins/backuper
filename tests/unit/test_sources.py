"""Source resolution / tar rooting tests (sources.py)."""

from __future__ import annotations

import logging
from pathlib import Path

from backuper import sources


# --------------------------------------------------------------------------- #
# resolve_source_paths
# --------------------------------------------------------------------------- #
def test_absolute_literal_kept(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    assert sources.resolve_source_paths([str(f)], tmp_path) == [str(f)]


def test_relative_anchored_at_base_dir(tmp_path):
    (tmp_path / "sub").mkdir()
    f = tmp_path / "sub" / "file.txt"
    f.write_text("x", encoding="utf-8")
    assert sources.resolve_source_paths(["sub/file.txt"], tmp_path) == [str(f)]


def test_tilde_expansion(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / "file.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    result = sources.resolve_source_paths(["~/file.txt"], tmp_path)
    assert result == [str(fake_home / "file.txt")]


def test_glob_dedup_sorted_includes_dotfiles(tmp_path):
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    (tmp_path / "b.txt").write_text("2", encoding="utf-8")
    (tmp_path / ".hidden").write_text("3", encoding="utf-8")
    result = sources.resolve_source_paths(["*"], tmp_path)
    names = sorted(Path(p).name for p in result)
    assert names == [".hidden", "a.txt", "b.txt"]
    assert result == sorted(result)  # sorted output


def test_glob_no_match_warns_and_is_skipped(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        result = sources.resolve_source_paths(["nomatch*.xyz"], tmp_path)
    assert result == []
    assert any("matched nothing" in r.message for r in caplog.records)


def test_literal_missing_path_warns_but_kept(tmp_path, caplog):
    missing = tmp_path / "doesnotexist.txt"
    with caplog.at_level(logging.WARNING):
        result = sources.resolve_source_paths([str(missing)], tmp_path)
    assert result == [str(missing)]
    assert any("does not exist" in r.message for r in caplog.records)


def test_dedup_across_patterns(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    result = sources.resolve_source_paths([str(f), str(f)], tmp_path)
    assert result == [str(f)]


# --------------------------------------------------------------------------- #
# common_root
# --------------------------------------------------------------------------- #
def test_common_root_single_path():
    assert sources.common_root(["/a/b/c.txt"]) == "/a/b"


def test_common_root_single_path_at_filesystem_root():
    assert sources.common_root(["/c.txt"]) == "/"


def test_common_root_multi_paths():
    assert sources.common_root(["/a/b/x.txt", "/a/b/y.txt"]) == "/a/b"


def test_common_root_disjoint_trees():
    assert sources.common_root(["/etc/passwd", "/srv/data"]) == "/"


# --------------------------------------------------------------------------- #
# members_relative_to
# --------------------------------------------------------------------------- #
def test_members_relative_to_inside_root():
    result = sources.members_relative_to(["/a/b/c.txt", "/a/b/d.txt"], "/a/b")
    assert result == ["c.txt", "d.txt"]


def test_members_relative_to_path_equal_root_is_not_escaping():
    result = sources.members_relative_to(["/a/b"], "/a/b")
    assert result == ["."]


def test_members_relative_to_any_escaping_path_returns_none():
    result = sources.members_relative_to(["/a/b/c.txt", "/other/x.txt"], "/a/b")
    assert result is None
