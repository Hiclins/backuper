"""Command-line interface and dispatch."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .config import load_config
from .errors import BackuperError
from .logging_setup import setup_logging

log = logging.getLogger("backuper")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backuper",
        description="Modular incremental backup tool (GNU tar + age + S3/local).",
    )
    parser.add_argument("--version", action="version", version=f"backuper {__version__}")
    parser.add_argument("-c", "--config", help="path to the config file")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase log verbosity (-v info, -vv debug)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="create a full or incremental backup")
    p_backup.add_argument(
        "--full", action="store_true", help="force a full backup (start a new chain)"
    )
    p_backup.add_argument(
        "-n", "--dry-run", action="store_true", help="show what would happen only"
    )

    p_restore = sub.add_parser("restore", help="restore a point in time")
    p_restore.add_argument(
        "--target",
        default="latest",
        help="'latest' or an ISO timestamp (e.g. 2026-07-17T12:00:00)",
    )
    p_restore.add_argument("--dest", required=True, help="directory to restore into")
    p_restore.add_argument(
        "--destination", help="restore from this destination only (by name)"
    )

    p_verify = sub.add_parser("verify", help="check artifact integrity (SHA-256)")
    p_verify.add_argument(
        "--all", action="store_true", help="verify every chain (default: latest only)"
    )
    p_verify.add_argument(
        "--destination", help="verify against this destination only (by name)"
    )

    sub.add_parser("list", help="list backup chains and restore points")

    p_prune = sub.add_parser("prune", help="apply the retention policy")
    p_prune.add_argument(
        "-n", "--dry-run", action="store_true", help="show what would be pruned only"
    )

    return parser


def _dispatch(command: str):
    if command == "backup":
        from .commands import backup

        return backup.run
    if command == "restore":
        from .commands import restore

        return restore.run
    if command == "verify":
        from .commands import verify

        return verify.run
    if command == "list":
        from .commands import list_cmd

        return list_cmd.run
    if command == "prune":
        from .commands import prune

        return prune.run
    raise BackuperError(f"unknown command: {command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        setup_logging(
            level=cfg.logging.level,
            file=cfg.logging.file,
            json_output=cfg.logging.json,
            verbosity=args.verbose,
        )
        handler = _dispatch(args.command)
        return handler(cfg, args)
    except BackuperError as exc:
        # Logging may not be configured yet if load_config failed.
        if logging.getLogger().handlers:
            log.error("%s", exc)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
