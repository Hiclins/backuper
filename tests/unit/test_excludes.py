"""Exclude-pattern normalization tests (excludes.py)."""

from __future__ import annotations

import logging

from backuper import excludes


def test_blank_and_comment_lines_skipped(tmp_path):
    result = excludes.normalize_patterns(["", "  ", "# a comment", "*.log"], tmp_path, "/root")
    assert result == ["*.log"]


def test_negation_warns_and_is_dropped(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        result = excludes.normalize_patterns(["!important.txt"], tmp_path, "/root")
    assert result == []
    assert any("negation" in r.message for r in caplog.records)


def test_floating_pattern_passthrough(tmp_path):
    assert excludes.normalize_patterns(["*.log"], tmp_path, "/root") == ["*.log"]


def test_leading_double_star_slash_stripped(tmp_path):
    assert excludes.normalize_patterns(["**/cache/"], tmp_path, "/root") == ["cache"]


def test_trailing_slash_stripped(tmp_path):
    assert excludes.normalize_patterns(["node_modules/"], tmp_path, "/root") == ["node_modules"]


def test_path_form_absolute_inside_root_rebased(tmp_path):
    root = str(tmp_path / "archive-root")
    pattern = str(tmp_path / "archive-root" / "sub" / "secret")
    result = excludes.normalize_patterns([pattern], tmp_path, root)
    assert result == ["sub/secret"]


def test_path_form_relative_dotdot_inside_root(tmp_path):
    # base_dir/../shared resolves to tmp_path's parent/shared; make root that path
    base_dir = tmp_path / "config_dir"
    base_dir.mkdir()
    root = str(tmp_path / "shared")
    result = excludes.normalize_patterns(["../shared/secret.txt"], base_dir, root)
    assert result == ["secret.txt"]


def test_path_form_outside_root_dropped_with_warning(tmp_path, caplog):
    root = str(tmp_path / "archive-root")
    outside = str(tmp_path / "elsewhere" / "file.txt")
    with caplog.at_level(logging.WARNING):
        result = excludes.normalize_patterns([outside], tmp_path, root)
    assert result == []
    assert any("outside the archive root" in r.message for r in caplog.records)


def test_write_exclude_file_returns_none_when_empty(tmp_path):
    dest = tmp_path / "exclude.list"
    result = excludes.write_exclude_file(["!neg", "# comment"], dest, tmp_path, "/root")
    assert result is None
    assert not dest.exists()


def test_write_exclude_file_writes_normalized_patterns(tmp_path):
    dest = tmp_path / "exclude.list"
    result = excludes.write_exclude_file(["*.log", "**/cache/"], dest, tmp_path, "/root")
    assert result == dest
    assert dest.read_text(encoding="utf-8") == "*.log\ncache\n"
