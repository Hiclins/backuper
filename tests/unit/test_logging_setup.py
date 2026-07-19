"""Logging configuration tests (logging_setup.py).

Note: `setup_logging` strips and replaces ALL root-logger handlers on every
call, including any handler pytest's `caplog` attached beforehand. So these
tests assert on stderr text via `capsys`, not `caplog`.
"""

from __future__ import annotations

import json
import logging

from backuper.logging_setup import setup_logging


def test_default_level_info():
    setup_logging()
    assert logging.getLogger().level == logging.INFO


def test_explicit_debug_level():
    setup_logging(level="debug")
    assert logging.getLogger().level == logging.DEBUG


def test_unknown_level_defaults_to_info():
    setup_logging(level="bogus")
    assert logging.getLogger().level == logging.INFO


def test_verbosity_1_raises_error_level_to_info():
    setup_logging(level="error", verbosity=1)
    assert logging.getLogger().level == logging.INFO


def test_verbosity_1_never_lowers_debug():
    setup_logging(level="debug", verbosity=1)
    assert logging.getLogger().level == logging.DEBUG


def test_verbosity_2_forces_debug_even_over_error():
    setup_logging(level="error", verbosity=2)
    assert logging.getLogger().level == logging.DEBUG


def test_verbosity_0_leaves_level_untouched():
    setup_logging(level="debug", verbosity=0)
    assert logging.getLogger().level == logging.DEBUG


def test_repeated_calls_do_not_accumulate_handlers():
    setup_logging()
    setup_logging()
    setup_logging()
    assert len(logging.getLogger().handlers) == 1


def test_json_formatter_valid_json_with_expected_keys(capsys):
    setup_logging(json_output=True)
    logging.getLogger("test").info("hello world")
    err = capsys.readouterr().err
    payload = json.loads(err.strip().splitlines()[-1])
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["message"] == "hello world"
    assert "time" in payload


def test_json_formatter_includes_exc_on_exception(capsys):
    setup_logging(json_output=True)
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("test").exception("failed")
    err = capsys.readouterr().err
    payload = json.loads(err.strip().splitlines()[-1])
    assert "exc" in payload
    assert "ValueError" in payload["exc"]


def test_file_handler_writes_and_creates_parent_dirs(tmp_path):
    log_file = tmp_path / "nested" / "app.log"
    setup_logging(file=str(log_file))
    logging.getLogger("test").info("to file")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert log_file.is_file()
    assert "to file" in log_file.read_text(encoding="utf-8")


def test_bad_file_path_is_non_fatal(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a dir", encoding="utf-8")
    bad_path = blocker / "app.log"  # parent path component is a regular file
    setup_logging(file=str(bad_path))  # must not raise
    root = logging.getLogger()
    assert not any(isinstance(h, logging.FileHandler) for h in root.handlers)
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    err = capsys.readouterr().err
    assert "could not open log file" in err
