"""Storage backends: pluggable destinations for backup artifacts."""

from .base import Backend
from .registry import build_backends

__all__ = ["Backend", "build_backends"]
