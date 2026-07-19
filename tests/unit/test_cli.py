"""CLI argument parsing and dispatch tests (cli.py)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from backuper import cli
from backuper.errors import (
    BackendError,
    BackuperError,
    CatalogError,
    ConfigError,
    PipelineError,
    ToolNotFoundError,
)


# --------------------------------------------------------------------------- #
# build_parser
# --------------------------------------------------------------------------- #
def test_backup_defaults():
    args = cli.build_parser().parse_args(["backup"])
    assert args.command == "backup"
    assert args.full is False
    assert args.dry_run is False


def test_backup_flags_set():
    args = cli.build_parser().parse_args(["backup", "--full", "-n"])
    assert args.full is True
    assert args.dry_run is True


def test_restore_requires_dest():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["restore"])


def test_restore_target_defaults_to_latest():
    args = cli.build_parser().parse_args(["restore", "--dest", "/tmp/x"])
    assert args.target == "latest"
    assert args.destination is None


def test_verify_flags():
    args = cli.build_parser().parse_args(["verify", "--all", "--destination", "s3"])
    assert args.all is True
    assert args.destination == "s3"


def test_verify_defaults():
    args = cli.build_parser().parse_args(["verify"])
    assert args.all is False
    assert args.destination is None


def test_prune_dry_run_flag():
    args = cli.build_parser().parse_args(["prune", "-n"])
    assert args.dry_run is True


def test_no_subcommand_exits():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.build_parser().parse_args(["--version"])
    assert excinfo.value.code == 0
    assert "backuper" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# _dispatch
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("command", ["backup", "restore", "verify", "list", "prune"])
def test_dispatch_returns_callable_run(command):
    handler = cli._dispatch(command)
    assert callable(handler)
    assert handler.__name__ == "run"


def test_dispatch_unknown_command_raises_backuper_error():
    with pytest.raises(BackuperError):
        cli._dispatch("not-a-real-command")


# --------------------------------------------------------------------------- #
# main(): exit-code mapping
# --------------------------------------------------------------------------- #
def _stub_dispatch(monkeypatch, exc):
    def fake_dispatch(command):
        def _raise(cfg, args):
            raise exc

        return _raise

    monkeypatch.setattr(cli, "_dispatch", fake_dispatch)


@pytest.mark.parametrize(
    "exc,expected_code",
    [
        (ConfigError("bad config"), 2),
        (ToolNotFoundError("missing binary"), 2),
        (BackendError("backend down"), 3),
        (PipelineError("stage failed"), 1),
        (CatalogError("bad catalog"), 1),
        (BackuperError("generic"), 1),
    ],
)
def test_main_maps_exception_to_exit_code(make_config, monkeypatch, exc, expected_code):
    config_path = make_config()
    _stub_dispatch(monkeypatch, exc)
    code = cli.main(["-c", str(config_path), "list"])
    assert code == expected_code


def test_main_config_error_before_logging_prints_raw_stderr():
    # Run as a real subprocess: pytest's own live-log capture always attaches
    # a handler to the root logger within the test's call phase, which would
    # make `logging.getLogger().handlers` truthy in-process and mask the
    # pre-logging branch this test targets.
    result = subprocess.run(
        [sys.executable, "-m", "backuper", "-c", "/definitely/does/not/exist.yaml", "list"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert result.stderr.startswith("error: ")


def test_main_post_logging_error_uses_log_formatter_not_raw_print(
    make_config, monkeypatch, capsys
):
    config_path = make_config()
    _stub_dispatch(monkeypatch, ConfigError("boom"))
    code = cli.main(["-c", str(config_path), "list"])
    assert code == 2
    err = capsys.readouterr().err
    assert "boom" in err
    assert not err.startswith("error: ")


def test_main_keyboard_interrupt_returns_130(make_config, monkeypatch, capsys):
    config_path = make_config()
    _stub_dispatch(monkeypatch, KeyboardInterrupt())
    code = cli.main(["-c", str(config_path), "list"])
    assert code == 130
    assert "interrupted" in capsys.readouterr().err
