"""Build backend instances from destination config entries."""

from __future__ import annotations

from ..errors import ConfigError
from .base import Backend
from .local import LocalBackend
from .s3 import S3Backend


def _make_backend(index: int, dest: dict) -> Backend:
    dtype = dest.get("type")
    name = dest.get("name") or f"{dtype}{index}"

    if dtype == "local":
        if "path" not in dest:
            raise ConfigError(f"[{name}] local destination requires 'path'")
        return LocalBackend(name=name, path=dest["path"])

    if dtype == "s3":
        return S3Backend(
            name=name,
            bucket=dest.get("bucket", ""),
            prefix=dest.get("prefix", ""),
            storage_class=dest.get("storage_class"),
            region=dest.get("region"),
            access_key_id=dest.get("access_key_id"),
            secret_access_key=dest.get("secret_access_key"),
            endpoint_url=dest.get("endpoint_url"),
        )

    raise ConfigError(f"[{name}] unknown destination type: {dtype!r}")


def build_backends(
    destinations: list[dict], only: str | None = None
) -> list[Backend]:
    """Instantiate every configured backend (or just the one named `only`)."""
    backends = [_make_backend(i, d) for i, d in enumerate(destinations)]
    if only is not None:
        backends = [b for b in backends if b.name == only]
        if not backends:
            raise ConfigError(f"no destination named {only!r}")
    return backends
