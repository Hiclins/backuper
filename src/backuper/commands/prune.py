"""`prune` command: apply the GFS retention policy on its own."""

from __future__ import annotations

from argparse import Namespace

from ..backends import build_backends
from ..config import Config
from .common import apply_retention, load_catalog


def run(cfg: Config, args: Namespace) -> int:
    backends = build_backends(cfg.destinations)
    catalog = load_catalog(cfg, backends)
    apply_retention(cfg, catalog, backends, dry_run=args.dry_run)
    return 0
