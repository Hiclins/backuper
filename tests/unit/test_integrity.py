"""SHA-256 / sidecar helper tests (integrity.py)."""

from __future__ import annotations

import hashlib

from backuper.integrity import CHUNK, read_sidecar, sha256_file, sidecar_path, write_sidecar


def test_sha256_file_known_bytes(tmp_path):
    path = tmp_path / "data.bin"
    content = b"hello world"
    path.write_bytes(content)
    assert sha256_file(path) == hashlib.sha256(content).hexdigest()


def test_sha256_file_spans_multiple_chunks(tmp_path):
    path = tmp_path / "large.bin"
    content = b"x" * (CHUNK * 2 + 123)
    path.write_bytes(content)
    assert sha256_file(path) == hashlib.sha256(content).hexdigest()


def test_sidecar_path_appends_suffix():
    from pathlib import Path

    assert sidecar_path(Path("/x/archive.tar.zst")) == Path("/x/archive.tar.zst.sha256")


def test_write_sidecar_exact_format(tmp_path):
    artifact = tmp_path / "archive.tar"
    artifact.write_bytes(b"data")
    path = write_sidecar(artifact, "abc123")
    assert path == tmp_path / "archive.tar.sha256"
    assert path.read_text(encoding="utf-8") == "abc123  archive.tar\n"


def test_read_sidecar_extracts_first_token(tmp_path):
    path = tmp_path / "archive.tar.sha256"
    path.write_text("deadbeef  archive.tar\n", encoding="utf-8")
    assert read_sidecar(path) == "deadbeef"


def test_write_read_roundtrip(tmp_path):
    artifact = tmp_path / "archive.tar"
    artifact.write_bytes(b"payload")
    digest = sha256_file(artifact)
    sidecar = write_sidecar(artifact, digest)
    assert read_sidecar(sidecar) == digest
