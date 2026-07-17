"""`list` command: show backup chains and restore points."""

from __future__ import annotations

from argparse import Namespace

from ..backends import build_backends
from ..config import Config
from .common import load_catalog


def _human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TiB"


def run(cfg: Config, args: Namespace) -> int:
    backends = build_backends(cfg.destinations)
    catalog = load_catalog(cfg, backends)

    if not catalog.chains:
        print("no backups yet")
        return 0

    for chain in catalog.chains:
        enc = "encrypted" if chain.encrypted else "plain"
        print(
            f"chain {chain.id}  [{chain.compression}, {enc}]  "
            f"{len(chain.backups)} backup(s)  {_human_size(chain.total_size)}"
        )
        for entry in chain.backups:
            kind = "full" if entry.level == 0 else f"incr L{entry.level}"
            print(
                f"    {entry.time:%Y-%m-%d %H:%M:%S}  {kind:<8}  "
                f"{_human_size(entry.size):>9}  {entry.artifact}"
            )
    return 0
