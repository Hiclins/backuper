"""Abstract storage backend.

A backend is a flat namespace of named blobs. Names are plain file names
(artifacts, their `.sha256` sidecars, `.snar` snapshots, and `catalog.json`).
Add a new backend by subclassing this and registering it in `registry.py` -
nothing else in the codebase needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Backend(ABC):
    #: Human-readable name used in logs and by `--destination`.
    name: str

    @abstractmethod
    def upload(self, local: Path, name: str) -> None:
        """Store `local` under `name`."""

    @abstractmethod
    def download(self, name: str, local: Path) -> None:
        """Fetch `name` into `local`."""

    @abstractmethod
    def list(self) -> list[str]:
        """Return all stored names."""

    @abstractmethod
    def delete(self, name: str) -> None:
        """Delete `name` if present (no error if missing)."""

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Return True if `name` is stored."""

    def __str__(self) -> str:
        return self.name
