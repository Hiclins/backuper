"""Logging configuration: level, optional file, optional JSON output."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    level: str = "info",
    file: str | None = None,
    json_output: bool = False,
    verbosity: int = 0,
) -> None:
    """Configure the root logger.

    `verbosity` (from repeated -v flags) can only raise the level, never lower it:
    -v -> at least INFO, -vv -> DEBUG.
    """
    resolved = _LEVELS.get(level.lower(), logging.INFO)
    if verbosity >= 2:
        resolved = logging.DEBUG
    elif verbosity == 1:
        resolved = min(resolved, logging.INFO)

    root = logging.getLogger()
    root.setLevel(resolved)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    text_fmt = "%(asctime)s %(levelname)-7s %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(
        _JsonFormatter() if json_output else logging.Formatter(text_fmt, date_fmt)
    )
    root.addHandler(stream)

    if file:
        path = Path(file).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setFormatter(
                _JsonFormatter()
                if json_output
                else logging.Formatter(text_fmt, date_fmt)
            )
            root.addHandler(file_handler)
        except OSError as exc:  # non-fatal: keep stderr logging
            root.warning("could not open log file %s: %s", path, exc)
