"""Config loading, validation, and binary-discovery tests (config.py)."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest
import yaml

from backuper import config
from backuper.errors import ConfigError, ToolNotFoundError


# --------------------------------------------------------------------------- #
# resolve_path
# --------------------------------------------------------------------------- #
def test_resolve_path_absolute_kept(tmp_path):
    assert config.resolve_path("/etc/passwd", tmp_path) == Path("/etc/passwd")


def test_resolve_path_relative_anchored_at_base(tmp_path):
    result = config.resolve_path("sub/dir", tmp_path)
    assert result == (tmp_path / "sub/dir").resolve()


def test_resolve_path_expands_tilde(tmp_path):
    result = config.resolve_path("~/somefile", tmp_path)
    assert result == Path.home() / "somefile"


# --------------------------------------------------------------------------- #
# find_config_path
# --------------------------------------------------------------------------- #
def test_find_config_path_explicit_missing_raises(tmp_path):
    with pytest.raises(ConfigError):
        config.find_config_path(str(tmp_path / "nope.yaml"))


def test_find_config_path_explicit_found(tmp_path):
    cfg_file = tmp_path / "mine.yaml"
    cfg_file.write_text("sources: []\n", encoding="utf-8")
    assert config.find_config_path(str(cfg_file)) == cfg_file


def test_find_config_path_env_var(tmp_path, monkeypatch):
    cfg_file = tmp_path / "envcfg.yaml"
    cfg_file.write_text("sources: []\n", encoding="utf-8")
    monkeypatch.setenv("BACKUPER_CONFIG", str(cfg_file))
    assert config.find_config_path(None) == cfg_file


def test_find_config_path_cwd_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKUPER_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "backuper.yaml").write_text("sources: []\n", encoding="utf-8")
    assert config.find_config_path(None) == Path("./backuper.yaml")


def test_find_config_path_none_found_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKUPER_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        config.find_config_path(None)


# --------------------------------------------------------------------------- #
# load_config: valid + validation failures
# --------------------------------------------------------------------------- #
def _write(path: Path, data: dict | str) -> Path:
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _minimal_valid() -> dict:
    return {
        "sources": ["/tmp/does-not-matter"],
        "destinations": [{"type": "local", "path": "/tmp/dest"}],
    }


def test_load_config_minimal_valid_fills_defaults(tmp_path):
    path = _write(tmp_path / "backuper.yaml", _minimal_valid())
    cfg = config.load_config(str(path))
    assert cfg.archive.compression == "zstd"
    assert cfg.mode.strategy == "incremental"
    assert cfg.encryption.enabled is False
    assert cfg.retention.keep_last == 3
    assert cfg.logging.level == "info"
    assert cfg.base_dir == tmp_path


def test_load_config_invalid_yaml_raises(tmp_path):
    path = _write(tmp_path / "backuper.yaml", "sources: [\n  - unterminated")
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_non_mapping_root_raises(tmp_path):
    path = _write(tmp_path / "backuper.yaml", "- a\n- b\n")
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_empty_sources_raises(tmp_path):
    data = _minimal_valid()
    data["sources"] = []
    path = _write(tmp_path / "backuper.yaml", data)
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_bad_compression_raises(tmp_path):
    data = _minimal_valid()
    data["archive"] = {"compression": "rar"}
    path = _write(tmp_path / "backuper.yaml", data)
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_bad_strategy_raises(tmp_path):
    data = _minimal_valid()
    data["mode"] = {"strategy": "sideways"}
    path = _write(tmp_path / "backuper.yaml", data)
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_encryption_enabled_without_recipients_raises(tmp_path):
    data = _minimal_valid()
    data["encryption"] = {"enabled": True}
    path = _write(tmp_path / "backuper.yaml", data)
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_empty_destinations_raises(tmp_path):
    data = _minimal_valid()
    data["destinations"] = []
    path = _write(tmp_path / "backuper.yaml", data)
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_destination_missing_type_raises(tmp_path):
    data = _minimal_valid()
    data["destinations"] = [{"path": "/tmp/dest"}]
    path = _write(tmp_path / "backuper.yaml", data)
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_non_mapping_section_raises(tmp_path):
    data = _minimal_valid()
    data["archive"] = "oops"
    path = _write(tmp_path / "backuper.yaml", data)
    with pytest.raises(ConfigError):
        config.load_config(str(path))


def test_load_config_relative_paths_anchored_at_config_dir(tmp_path, monkeypatch):
    config_dir = tmp_path / "confdir"
    config_dir.mkdir()
    data = _minimal_valid()
    data["state_dir"] = "relstate"
    path = _write(config_dir / "backuper.yaml", data)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    cfg = config.load_config(str(path))
    assert cfg.state_dir == (config_dir / "relstate").resolve()


def test_load_config_local_destination_path_resolved_relative(tmp_path):
    data = _minimal_valid()
    data["destinations"] = [{"type": "local", "path": "reldest"}]
    path = _write(tmp_path / "backuper.yaml", data)
    cfg = config.load_config(str(path))
    assert cfg.destinations[0]["path"] == str((tmp_path / "reldest").resolve())


# --------------------------------------------------------------------------- #
# _warn_on_inline_secret_permissions
# --------------------------------------------------------------------------- #
def test_warn_on_inline_secret_world_readable(tmp_path, caplog):
    data = _minimal_valid()
    data["destinations"] = [
        {"type": "s3", "bucket": "b", "access_key_id": "AKIA", "secret_access_key": "x"}
    ]
    path = _write(tmp_path / "backuper.yaml", data)
    os.chmod(path, 0o644)
    with caplog.at_level(logging.WARNING):
        config.load_config(str(path))
    assert any("inline AWS credentials" in r.message for r in caplog.records)


def test_warn_on_inline_secret_chmod_600_silences(tmp_path, caplog):
    data = _minimal_valid()
    data["destinations"] = [
        {"type": "s3", "bucket": "b", "access_key_id": "AKIA", "secret_access_key": "x"}
    ]
    path = _write(tmp_path / "backuper.yaml", data)
    os.chmod(path, 0o600)
    with caplog.at_level(logging.WARNING):
        config.load_config(str(path))
    assert not any("inline AWS credentials" in r.message for r in caplog.records)


def test_no_warning_without_inline_secrets(tmp_path, caplog):
    data = _minimal_valid()
    path = _write(tmp_path / "backuper.yaml", data)
    os.chmod(path, 0o644)
    with caplog.at_level(logging.WARNING):
        config.load_config(str(path))
    assert not any("inline AWS credentials" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# incremental_count / parse_interval
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        (10, 10),
        ("10", 10),
        ("10i", 10),
        ("10x", 10),
        ("10X", 10),
        ("7d", None),
        (None, None),
    ],
)
def test_incremental_count(value, expected):
    assert config.incremental_count(value) == expected


@pytest.mark.parametrize(
    "text,days,hours,minutes",
    [
        ("7d", 7, 0, 0),
        ("12h", 0, 12, 0),
        ("30m", 0, 0, 30),
    ],
)
def test_parse_interval_valid(text, days, hours, minutes):
    from datetime import timedelta

    assert config.parse_interval(text) == timedelta(days=days, hours=hours, minutes=minutes)


def test_parse_interval_empty_raises():
    with pytest.raises(ConfigError):
        config.parse_interval("")


def test_parse_interval_non_numeric_raises():
    with pytest.raises(ConfigError):
        config.parse_interval("abcd")


def test_parse_interval_bad_unit_raises():
    with pytest.raises(ConfigError):
        config.parse_interval("10z")


# --------------------------------------------------------------------------- #
# resolve_gnu_tar / require_binary (hermetic)
# --------------------------------------------------------------------------- #
class _FakeCompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout


def test_resolve_gnu_tar_finds_gtar(monkeypatch):
    def fake_which(name):
        return f"/usr/bin/{name}" if name == "gtar" else None

    def fake_run(cmd, capture_output, text, timeout):
        return _FakeCompletedProcess("tar (GNU tar) 1.35\n")

    monkeypatch.setattr(config.shutil, "which", fake_which)
    monkeypatch.setattr(config.subprocess, "run", fake_run)
    assert config.resolve_gnu_tar() == "/usr/bin/gtar"


def test_resolve_gnu_tar_skips_bsdtar(monkeypatch):
    def fake_which(name):
        return f"/usr/bin/{name}"

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("gtar"):
            return _FakeCompletedProcess("bsdtar 3.5.1\n")
        return _FakeCompletedProcess("bsdtar 3.5.1\n")

    monkeypatch.setattr(config.shutil, "which", fake_which)
    monkeypatch.setattr(config.subprocess, "run", fake_run)
    with pytest.raises(ToolNotFoundError):
        config.resolve_gnu_tar()


def test_resolve_gnu_tar_none_installed_raises(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    with pytest.raises(ToolNotFoundError):
        config.resolve_gnu_tar()


def test_resolve_gnu_tar_explicit_path_not_found_raises(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    with pytest.raises(ToolNotFoundError):
        config.resolve_gnu_tar("/opt/nonexistent/tar")


@pytest.mark.skipif(config.shutil.which("gtar") is None and config.shutil.which("tar") is None,
                     reason="no tar binary available at all")
def test_resolve_gnu_tar_real_sanity():
    # Real, unmocked check against whatever GNU tar is installed locally/CI.
    path = config.resolve_gnu_tar()
    assert Path(path).name in ("gtar", "tar")


def test_require_binary_found(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert config.require_binary("xz") == "/usr/bin/xz"


def test_require_binary_missing_raises(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    with pytest.raises(ToolNotFoundError):
        config.require_binary("xz", hint="brew install xz")
