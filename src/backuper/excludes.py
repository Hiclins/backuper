"""Translate gitignore-style exclude patterns into a GNU tar exclude file.

Patterns are matched against archive member names, which are relative to the
chain's tar root (the common parent of the sources; see sources.py). For the
classic server case that root is "/", so patterns look like `root/backups`; for
a "projects folder" config the root is that folder, so patterns look like
`projectA/node_modules`.

Two kinds of patterns are accepted:
    floating / root-relative   e.g. `*.log`, `node_modules/`, `projectA/cache`
        Passed through to tar; matched (non-anchored) against member names.
        `**/` is collapsed (tar wildcards already match "/") and a trailing "/"
        is stripped.
    filesystem-path form       absolute (`/var/tmp`), `~`, or `../backup`
        Resolved against the config-file directory, then re-expressed relative
        to the archive root. If it lies OUTSIDE the backup (root), it cannot
        match anything and is dropped with a warning.

Negation ("!pattern") is NOT supported in tar-exclude mode and is skipped with a
warning.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def _is_path_form(pat: str) -> bool:
    return (
        pat.startswith(("/", "~", "../"))
        or pat == ".."
    )


def normalize_patterns(
    patterns: list[str], base_dir: Path, root: str
) -> list[str]:
    result: list[str] = []
    for raw in patterns:
        pat = str(raw).strip()
        if not pat or pat.startswith("#"):
            continue
        if pat.startswith("!"):
            log.warning(
                "exclude negation is not supported (tar mode), ignoring: %s", pat
            )
            continue

        if _is_path_form(pat):
            # Resolve like a real path (anchored at the config dir), then make it
            # relative to the archive root so tar can match it.
            p = Path(pat).expanduser()
            abs_p = os.path.normpath(p if p.is_absolute() else base_dir / p)
            rel = os.path.relpath(abs_p, root)
            if rel == ".." or rel.startswith(".." + os.sep):
                log.warning(
                    "exclude is outside the archive root (%s), ignoring: %s",
                    root,
                    raw,
                )
                continue
            result.append(rel.rstrip("/"))
        else:
            if pat.startswith("**/"):
                pat = pat[3:]
            pat = pat.rstrip("/")
            if pat:
                result.append(pat)
    return result


def write_exclude_file(
    patterns: list[str], dest: Path, base_dir: Path, root: str
) -> Path | None:
    """Write normalized patterns to `dest`. Return the path, or None if empty."""
    normalized = normalize_patterns(patterns, base_dir, root)
    if not normalized:
        return None
    dest.write_text("\n".join(normalized) + "\n", encoding="utf-8")
    return dest
