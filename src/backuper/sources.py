"""Resolve and glob-expand backup sources into a tar root + member list.

Sources may be:
  - absolute paths            (/etc, /root)
  - relative paths            (project, ../shared) -> anchored at the config dir
  - globs                     (*, ../*, data/*.db) -> expanded against the config dir

Expansion happens at BACKUP time (not config load) so each run picks up newly
created files/directories. The tar root is the common parent of all resolved
paths; member names are stored relative to it. This makes the historical server
behaviour (`/etc`, `/root`, `/home` -> root `/`) a special case of the general
rule, and keeps restore layouts clean for the "one config per projects folder"
use case.
"""

from __future__ import annotations

import glob
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_GLOB_CHARS = ("*", "?", "[")


def _has_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in _GLOB_CHARS)


def _glob_include_hidden(pattern: str) -> list[str]:
    """Like glob.glob(pattern, recursive=True) but also matching dotfiles.

    `include_hidden` was only added to glob.glob() in Python 3.11. On older
    versions we get the same effect by temporarily disabling glob's private
    hidden-file filter, which has had the same shape since Python 3.4.
    """
    if sys.version_info >= (3, 11):
        return glob.glob(pattern, recursive=True, include_hidden=True)
    original = glob._ishidden
    glob._ishidden = lambda path: False
    try:
        return glob.glob(pattern, recursive=True)
    finally:
        glob._ishidden = original


def resolve_source_paths(patterns: list[str], base_dir: Path) -> list[str]:
    """Return a sorted, de-duplicated list of absolute source paths.

    Relative patterns are anchored at `base_dir`. Glob patterns are expanded
    (recursively, including dotfiles). A glob with no matches is warned about and
    skipped; a literal path that does not exist is warned about but kept so tar
    reports it.
    """
    resolved: set[str] = set()
    for raw in patterns:
        pattern = os.path.expanduser(str(raw))
        if not os.path.isabs(pattern):
            pattern = os.path.join(str(base_dir), pattern)

        if _has_glob(pattern):
            matches = _glob_include_hidden(pattern)
            if not matches:
                log.warning("source pattern matched nothing: %s", raw)
                continue
            for match in matches:
                resolved.add(os.path.abspath(match))
        else:
            abs_path = os.path.abspath(pattern)
            if not os.path.exists(abs_path):
                log.warning("source does not exist: %s", abs_path)
            resolved.add(abs_path)

    return sorted(resolved)


def common_root(paths: list[str]) -> str:
    """The directory tar chdir's into: the common parent of all `paths`."""
    if len(paths) == 1:
        return os.path.dirname(paths[0]) or "/"
    return os.path.commonpath(paths)


def members_relative_to(paths: list[str], root: str) -> list[str] | None:
    """Member names for `paths` relative to `root`.

    Returns None if any path escapes `root` (its relative form starts with
    ".."), which signals that the pinned chain root can no longer contain the
    current sources.
    """
    members: list[str] = []
    for path in paths:
        rel = os.path.relpath(path, root)
        if rel == ".." or rel.startswith(".." + os.sep):
            return None
        members.append(rel)
    return members
