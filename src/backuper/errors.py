"""Error types with process exit codes for cron-friendly reporting.

Exit code contract:
    0  success
    1  generic runtime error (archiving, pipeline, ...)
    2  configuration error
    3  backend/storage error or partial failure (uploaded to some destinations)
"""

from __future__ import annotations


class BackuperError(Exception):
    """Base class for all expected, reportable errors."""

    exit_code: int = 1


class ConfigError(BackuperError):
    """Invalid configuration or a missing external dependency."""

    exit_code = 2


class ToolNotFoundError(ConfigError):
    """A required external binary (tar/age/xz/...) was not found."""


class BackendError(BackuperError):
    """A storage backend failed (upload/download/list/delete)."""

    exit_code = 3


class PipelineError(BackuperError):
    """A stage of the tar|compress|encrypt pipeline exited non-zero."""

    exit_code = 1


class CatalogError(BackuperError):
    """The on-disk catalog is missing or inconsistent."""

    exit_code = 1
