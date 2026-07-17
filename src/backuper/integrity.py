"""SHA-256 integrity helpers and `.sha256` sidecar files."""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1 << 16
SIDECAR_SUFFIX = ".sha256"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_path(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + SIDECAR_SUFFIX)


def write_sidecar(artifact: Path, digest: str) -> Path:
    """Write a `<name> <sha256>` sidecar next to the artifact."""
    path = sidecar_path(artifact)
    path.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
    return path


def read_sidecar(path: Path) -> str:
    """Return the digest recorded in a sidecar file."""
    return path.read_text(encoding="utf-8").split()[0]
