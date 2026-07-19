"""Small assertion/builder helpers shared across test modules."""

from __future__ import annotations

from pathlib import Path

from backuper.backends.base import Backend
from backuper.catalog import BackupEntry, Chain
from backuper.errors import BackendError


class StubBackend(Backend):
    """An in-memory Backend for testing commands/common.py orchestration
    without real filesystem or network I/O."""

    def __init__(
        self,
        name: str,
        store: dict[str, bytes] | None = None,
        fail_upload: set[str] | None = None,
        fail_delete: set[str] | None = None,
        fail_exists_error: str | None = None,
    ) -> None:
        self.name = name
        self.store: dict[str, bytes] = store if store is not None else {}
        self.fail_upload = fail_upload or set()
        self.fail_delete = fail_delete or set()
        self.fail_exists_error = fail_exists_error
        self.deleted: list[str] = []

    def upload(self, local: Path, name: str) -> None:
        if name in self.fail_upload:
            raise BackendError(f"[{self.name}] upload failed: {name}")
        self.store[name] = local.read_bytes()

    def download(self, name: str, local: Path) -> None:
        if name not in self.store:
            raise BackendError(f"[{self.name}] download failed: {name}")
        local.write_bytes(self.store[name])

    def list(self) -> list[str]:
        return list(self.store)

    def delete(self, name: str) -> None:
        if name in self.fail_delete:
            raise BackendError(f"[{self.name}] delete failed: {name}")
        self.deleted.append(name)
        self.store.pop(name, None)

    def exists(self, name: str) -> bool:
        if self.fail_exists_error:
            raise BackendError(f"[{self.name}] {self.fail_exists_error}")
        return name in self.store


def make_entry(ts: str, level: int = 0, artifact: str | None = None, size: int = 100) -> BackupEntry:
    return BackupEntry(
        timestamp=ts,
        level=level,
        artifact=artifact or f"backup-{ts}-L{level}.tar",
        sha256="a" * 64,
        size=size,
    )


def make_chain(chain_id: str, entries: list[BackupEntry], **kwargs) -> Chain:
    return Chain(
        id=chain_id,
        snapshot=f"{chain_id}.snar",
        compression=kwargs.pop("compression", "zstd"),
        encrypted=kwargs.pop("encrypted", False),
        backups=entries,
        **kwargs,
    )


def _relative_files(root: Path) -> dict[str, Path]:
    files = {}
    for path in root.rglob("*"):
        if path.is_file():
            files[str(path.relative_to(root))] = path
    return files


def assert_tree_equal(dir_a: Path, dir_b: Path) -> None:
    """Assert two directory trees have identical relative paths and byte content."""
    files_a = _relative_files(dir_a)
    files_b = _relative_files(dir_b)
    assert set(files_a) == set(files_b), (
        f"tree mismatch: only in {dir_a}: {set(files_a) - set(files_b)}; "
        f"only in {dir_b}: {set(files_b) - set(files_a)}"
    )
    for rel, path_a in files_a.items():
        path_b = files_b[rel]
        assert path_a.read_bytes() == path_b.read_bytes(), f"content differs: {rel}"
