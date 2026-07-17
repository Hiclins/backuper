"""Helpers shared by the backup/restore/verify/prune commands."""

from __future__ import annotations

import logging
from pathlib import Path

from ..backends.base import Backend
from ..catalog import CATALOG_NAME, Catalog
from ..config import Config
from ..errors import BackendError, CatalogError
from ..integrity import sidecar_path
from ..retention import select_chains_to_drop

log = logging.getLogger(__name__)


def upload_many(
    backends: list[Backend], items: list[tuple[Path, str]]
) -> dict[str, str]:
    """Upload (local, name) pairs to every backend.

    Returns a mapping of failed-backend-name -> error message. A backend that
    fails on one item is skipped for the rest and recorded once.
    """
    failures: dict[str, str] = {}
    for backend in backends:
        try:
            for local, name in items:
                backend.upload(local, name)
            log.info("uploaded %d file(s) to %s", len(items), backend.name)
        except BackendError as exc:
            failures[backend.name] = str(exc)
            log.error("upload to %s failed: %s", backend.name, exc)
    return failures


def download_any(backends: list[Backend], name: str, dest: Path) -> Backend:
    """Download `name` from the first backend that has it. Raise if none do."""
    errors: list[str] = []
    for backend in backends:
        try:
            if backend.exists(name):
                backend.download(name, dest)
                return backend
        except BackendError as exc:
            errors.append(str(exc))
    raise BackendError(
        f"{name} not found in any destination"
        + (f" ({'; '.join(errors)})" if errors else "")
    )


def delete_from_all(backends: list[Backend], names: list[str]) -> None:
    for backend in backends:
        for name in names:
            try:
                backend.delete(name)
            except BackendError as exc:
                log.warning("could not delete %s from %s: %s", name, backend.name, exc)


def load_catalog(cfg: Config, backends: list[Backend]) -> Catalog:
    """Load the catalog from local state, falling back to a backend copy."""
    local = cfg.state_dir / CATALOG_NAME
    if local.is_file():
        return Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    try:
        download_any(backends, CATALOG_NAME, local)
    except BackendError as exc:
        raise CatalogError(
            "no catalog found locally or in any destination; run a backup first"
        ) from exc
    return Catalog.load(cfg.state_dir, cfg.archive.name_prefix)


def chain_object_names(catalog: Catalog, chain_ids: set[str]) -> list[str]:
    """All backend object names owned by the given chains (artifacts + sidecars
    + snapshot files)."""
    names: list[str] = []
    for chain in catalog.chains:
        if chain.id not in chain_ids:
            continue
        for entry in chain.backups:
            names.append(entry.artifact)
            names.append(sidecar_path(Path(entry.artifact)).name)
        names.append(chain.snapshot)
    return names


def apply_retention(
    cfg: Config, catalog: Catalog, backends: list[Backend], dry_run: bool
) -> list:
    """Drop whole chains per the GFS policy. Returns the dropped chains."""
    drop, _keep = select_chains_to_drop(catalog.chains, cfg.retention)
    if not drop:
        log.info("retention: nothing to prune")
        return []

    for chain in drop:
        span = f"{chain.created:%Y-%m-%d %H:%M} .. {chain.end_time:%Y-%m-%d %H:%M}"
        log.info(
            "retention: %s chain %s (%d backups, %s)",
            "would drop" if dry_run else "dropping",
            chain.id,
            len(chain.backups),
            span,
        )
    if dry_run:
        return drop

    names = chain_object_names(catalog, {c.id for c in drop})
    delete_from_all(backends, names)
    catalog.remove_chains({c.id for c in drop})
    catalog.save(cfg.state_dir)
    # remove local snapshot files for dropped chains
    for chain in drop:
        (cfg.state_dir / chain.snapshot).unlink(missing_ok=True)
    # mirror the trimmed catalog to the backends
    upload_many(backends, [(cfg.state_dir / CATALOG_NAME, CATALOG_NAME)])
    return drop
