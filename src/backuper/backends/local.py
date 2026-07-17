"""Local filesystem backend."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..errors import BackendError
from .base import Backend


class LocalBackend(Backend):
    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.root = Path(path).expanduser()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BackendError(f"[{name}] cannot create {self.root}: {exc}") from exc

    def _target(self, name: str) -> Path:
        return self.root / name

    def upload(self, local: Path, name: str) -> None:
        target = self._target(name)
        if local.resolve() == target.resolve():
            return
        try:
            shutil.copy2(local, target)
        except OSError as exc:
            raise BackendError(f"[{self.name}] upload {name}: {exc}") from exc

    def download(self, name: str, local: Path) -> None:
        source = self._target(name)
        if not source.is_file():
            raise BackendError(f"[{self.name}] not found: {name}")
        try:
            shutil.copy2(source, local)
        except OSError as exc:
            raise BackendError(f"[{self.name}] download {name}: {exc}") from exc

    def list(self) -> list[str]:
        return [p.name for p in self.root.iterdir() if p.is_file()]

    def delete(self, name: str) -> None:
        target = self._target(name)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise BackendError(f"[{self.name}] delete {name}: {exc}") from exc

    def exists(self, name: str) -> bool:
        return self._target(name).is_file()
