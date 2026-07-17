"""`verify` command: re-download artifacts and check their SHA-256."""

from __future__ import annotations

import logging
from argparse import Namespace

from ..backends import build_backends
from ..config import Config
from ..errors import BackendError
from ..integrity import sha256_file
from .common import download_any, load_catalog

log = logging.getLogger(__name__)


def run(cfg: Config, args: Namespace) -> int:
    backends = build_backends(cfg.destinations, only=args.destination)
    catalog = load_catalog(cfg, backends)

    if args.all:
        chains = catalog.chains
    else:
        latest = catalog.latest_chain()
        chains = [latest] if latest else []

    if not chains:
        log.info("nothing to verify")
        return 0

    workdir = cfg.state_dir / "verify-tmp"
    workdir.mkdir(parents=True, exist_ok=True)

    checked = 0
    failures = 0
    for chain in chains:
        for entry in chain.backups:
            checked += 1
            local = workdir / entry.artifact
            try:
                download_any(backends, entry.artifact, local)
                actual = sha256_file(local)
            except BackendError as exc:
                failures += 1
                log.error("MISSING %s: %s", entry.artifact, exc)
                continue
            finally:
                local.unlink(missing_ok=True)

            if actual == entry.sha256:
                log.info("OK      %s", entry.artifact)
            else:
                failures += 1
                log.error(
                    "CORRUPT %s: expected %s, got %s",
                    entry.artifact,
                    entry.sha256[:16],
                    actual[:16],
                )

    if failures:
        raise BackendError(f"{failures}/{checked} artifact(s) failed verification")
    log.info("verified %d artifact(s), all OK", checked)
    return 0
