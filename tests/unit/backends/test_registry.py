"""Backend dispatch/registry tests (backends/registry.py)."""

from __future__ import annotations

import pytest

from backuper.backends.registry import _make_backend, build_backends
from backuper.errors import ConfigError


def test_local_dispatch(tmp_path):
    backend = _make_backend(0, {"type": "local", "name": "mylocal", "path": str(tmp_path / "d")})
    assert backend.name == "mylocal"


def test_local_missing_path_raises():
    with pytest.raises(ConfigError):
        _make_backend(0, {"type": "local", "name": "x"})


def test_s3_dispatch():
    backend = _make_backend(0, {"type": "s3", "name": "mys3", "bucket": "b"})
    assert backend.name == "mys3"


def test_unknown_type_raises():
    with pytest.raises(ConfigError):
        _make_backend(0, {"type": "ftp", "name": "x"})


def test_default_name_local(tmp_path):
    backend = _make_backend(0, {"type": "local", "path": str(tmp_path / "d")})
    assert backend.name == "local0"


def test_default_name_s3():
    backend = _make_backend(1, {"type": "s3", "bucket": "b"})
    assert backend.name == "s31"


def test_build_backends_two_unnamed_locals_sequential(tmp_path):
    destinations = [
        {"type": "local", "path": str(tmp_path / "d0")},
        {"type": "local", "path": str(tmp_path / "d1")},
    ]
    backends = build_backends(destinations)
    assert [b.name for b in backends] == ["local0", "local1"]


def test_build_backends_only_filters_to_one(tmp_path):
    destinations = [
        {"type": "local", "name": "a", "path": str(tmp_path / "a")},
        {"type": "local", "name": "b", "path": str(tmp_path / "b")},
    ]
    backends = build_backends(destinations, only="b")
    assert [b.name for b in backends] == ["b"]


def test_build_backends_only_not_found_raises(tmp_path):
    destinations = [{"type": "local", "name": "a", "path": str(tmp_path / "a")}]
    with pytest.raises(ConfigError):
        build_backends(destinations, only="nope")
