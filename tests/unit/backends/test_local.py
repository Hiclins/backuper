"""LocalBackend tests (backends/local.py) — real filesystem via tmp_path."""

from __future__ import annotations

import os

import pytest

from backuper.backends.local import LocalBackend
from backuper.errors import BackendError

_SKIP_AS_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="permission bits are ignored when running as root",
)


def test_root_dir_created_on_init(tmp_path):
    root = tmp_path / "backend-root"
    LocalBackend(name="local", path=str(root))
    assert root.is_dir()


def test_uncreatable_root_raises(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    with pytest.raises(BackendError):
        LocalBackend(name="local", path=str(blocker / "sub"))


def test_upload_copies_content(tmp_path):
    backend = LocalBackend(name="local", path=str(tmp_path / "root"))
    src = tmp_path / "file.txt"
    src.write_text("hello", encoding="utf-8")
    backend.upload(src, "file.txt")
    assert (tmp_path / "root" / "file.txt").read_text(encoding="utf-8") == "hello"


def test_upload_same_file_is_noop(tmp_path):
    root = tmp_path / "root"
    backend = LocalBackend(name="local", path=str(root))
    target = root / "file.txt"
    target.write_text("hello", encoding="utf-8")
    backend.upload(target, "file.txt")  # source resolves to target
    assert target.read_text(encoding="utf-8") == "hello"


def test_download_copies(tmp_path):
    root = tmp_path / "root"
    backend = LocalBackend(name="local", path=str(root))
    (root / "file.txt").write_text("payload", encoding="utf-8")
    dest = tmp_path / "downloaded.txt"
    backend.download("file.txt", dest)
    assert dest.read_text(encoding="utf-8") == "payload"


def test_download_missing_raises(tmp_path):
    backend = LocalBackend(name="local", path=str(tmp_path / "root"))
    with pytest.raises(BackendError):
        backend.download("nope.txt", tmp_path / "out.txt")


def test_list_returns_file_names_only_excludes_dirs(tmp_path):
    root = tmp_path / "root"
    backend = LocalBackend(name="local", path=str(root))
    (root / "a.txt").write_text("1", encoding="utf-8")
    (root / "b.txt").write_text("2", encoding="utf-8")
    (root / "subdir").mkdir()
    assert sorted(backend.list()) == ["a.txt", "b.txt"]


def test_delete_removes_existing_file(tmp_path):
    root = tmp_path / "root"
    backend = LocalBackend(name="local", path=str(root))
    (root / "file.txt").write_text("x", encoding="utf-8")
    backend.delete("file.txt")
    assert not (root / "file.txt").exists()


def test_delete_missing_is_silent_noop(tmp_path):
    backend = LocalBackend(name="local", path=str(tmp_path / "root"))
    backend.delete("nope.txt")  # must not raise


def test_exists_true_and_false(tmp_path):
    root = tmp_path / "root"
    backend = LocalBackend(name="local", path=str(root))
    assert backend.exists("file.txt") is False
    (root / "file.txt").write_text("x", encoding="utf-8")
    assert backend.exists("file.txt") is True


def test_str_returns_name(tmp_path):
    backend = LocalBackend(name="mybackend", path=str(tmp_path / "root"))
    assert str(backend) == "mybackend"


@_SKIP_AS_ROOT
def test_upload_oserror_wrapped_as_backend_error(tmp_path):
    root = tmp_path / "root"
    backend = LocalBackend(name="local", path=str(root))
    src = tmp_path / "file.txt"
    src.write_text("x", encoding="utf-8")
    os.chmod(root, 0o555)
    try:
        with pytest.raises(BackendError):
            backend.upload(src, "file.txt")
    finally:
        os.chmod(root, 0o755)


@_SKIP_AS_ROOT
def test_delete_oserror_wrapped_as_backend_error(tmp_path):
    root = tmp_path / "root"
    backend = LocalBackend(name="local", path=str(root))
    (root / "file.txt").write_text("x", encoding="utf-8")
    os.chmod(root, 0o555)
    try:
        with pytest.raises(BackendError):
            backend.delete("file.txt")
    finally:
        os.chmod(root, 0o755)
