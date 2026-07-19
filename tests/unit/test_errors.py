"""Exit-code contract and exception hierarchy (errors.py)."""

from __future__ import annotations

from backuper.errors import (
    BackendError,
    BackuperError,
    CatalogError,
    ConfigError,
    PipelineError,
    ToolNotFoundError,
)


def test_exit_codes():
    assert BackuperError().exit_code == 1
    assert ConfigError().exit_code == 2
    assert ToolNotFoundError().exit_code == 2
    assert BackendError().exit_code == 3
    assert PipelineError().exit_code == 1
    assert CatalogError().exit_code == 1


def test_subclass_relationships():
    assert issubclass(ConfigError, BackuperError)
    assert issubclass(ToolNotFoundError, ConfigError)
    assert issubclass(ToolNotFoundError, BackuperError)
    assert issubclass(BackendError, BackuperError)
    assert issubclass(PipelineError, BackuperError)
    assert issubclass(CatalogError, BackuperError)
