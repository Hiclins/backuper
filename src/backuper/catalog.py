"""On-disk catalog of backup chains.

A *chain* is one full backup (level 0) plus any number of incrementals that
share a single GNU tar snapshot (.snar) file. Restore and retention operate on
whole chains. The catalog is JSON so it stays inspectable by hand.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .errors import CatalogError

CATALOG_NAME = "catalog.json"
CATALOG_VERSION = 1

# On-disk *chain* format version (snapshot/tar/member-naming semantics). This is
# independent of the package version (backuper.__version__). Bump ONLY when a
# change makes it unsafe to append an incremental to a chain created by an older
# version. `commands/backup.py` promotes to a fresh full when a chain's
# format_version differs from this, so cross-version chains stay correct.
# History:
#   1 - initial format; config-dir-relative sources / common-root rooting is
#       backward compatible because existing chains pin root="/".
CHAIN_FORMAT_VERSION = 1


@dataclass
class BackupEntry:
    timestamp: str  # ISO-8601
    level: int  # 0 = full, 1..N = incrementals
    artifact: str  # file name in the backends
    sha256: str
    size: int

    @property
    def time(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)


@dataclass
class Chain:
    id: str  # e.g. "20260717-120000" (from the full backup time)
    snapshot: str  # .snar file name
    compression: str  # algorithm used for every artifact in the chain
    encrypted: bool
    root: str = "/"  # tar -C directory; member names are relative to this
    format_version: int = CHAIN_FORMAT_VERSION  # chain format it was created with
    backups: list[BackupEntry] = field(default_factory=list)

    @property
    def created(self) -> datetime:
        return self.backups[0].time

    @property
    def end_time(self) -> datetime:
        return self.backups[-1].time

    @property
    def next_level(self) -> int:
        return self.backups[-1].level + 1 if self.backups else 0

    @property
    def total_size(self) -> int:
        return sum(b.size for b in self.backups)

    def artifact_names(self) -> list[str]:
        return [b.artifact for b in self.backups]


@dataclass
class Catalog:
    prefix: str
    chains: list[Chain] = field(default_factory=list)
    version: int = CATALOG_VERSION

    # -- chain access ------------------------------------------------------- #
    def latest_chain(self) -> Chain | None:
        return self.chains[-1] if self.chains else None

    def add_chain(self, chain: Chain) -> None:
        self.chains.append(chain)

    def remove_chains(self, ids: set[str]) -> list[Chain]:
        removed = [c for c in self.chains if c.id in ids]
        self.chains = [c for c in self.chains if c.id not in ids]
        return removed

    def find_chain_for_target(self, target: str) -> tuple[Chain, int] | None:
        """Return (chain, last_included_level) covering `target`.

        `target` is "latest" or an ISO timestamp. We pick the newest chain whose
        full backup started at or before the target, and include every backup in
        that chain up to (and including) the target time.
        """
        if not self.chains:
            return None
        if target == "latest":
            chain = self.chains[-1]
            return chain, chain.backups[-1].level
        try:
            want = datetime.fromisoformat(target)
        except ValueError as exc:
            raise CatalogError(
                f"invalid --target {target!r}; use 'latest' or ISO like "
                "2026-07-17T12:00:00"
            ) from exc
        candidate: tuple[Chain, int] | None = None
        for chain in self.chains:
            if chain.created > want:
                continue
            included = [b for b in chain.backups if b.time <= want]
            if included:
                candidate = (chain, included[-1].level)
        return candidate

    # -- persistence -------------------------------------------------------- #
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "prefix": self.prefix,
            "chains": [
                {
                    "id": c.id,
                    "snapshot": c.snapshot,
                    "compression": c.compression,
                    "encrypted": c.encrypted,
                    "root": c.root,
                    "format_version": c.format_version,
                    "backups": [asdict(b) for b in c.backups],
                }
                for c in self.chains
            ],
        }

    def save(self, state_dir: Path) -> Path:
        path = state_dir / CATALOG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)  # atomic on the same filesystem
        return path

    @classmethod
    def load(cls, state_dir: Path, prefix: str) -> "Catalog":
        path = state_dir / CATALOG_NAME
        if not path.is_file():
            return cls(prefix=prefix)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"cannot read catalog {path}: {exc}") from exc
        chains = [
            Chain(
                id=c["id"],
                snapshot=c["snapshot"],
                compression=c.get("compression", "zstd"),
                encrypted=c.get("encrypted", False),
                root=c.get("root", "/"),  # default keeps old catalogs consistent
                # old catalogs predate the gate: treat them as format 1
                format_version=c.get("format_version", 1),
                backups=[BackupEntry(**b) for b in c.get("backups", [])],
            )
            for c in data.get("chains", [])
        ]
        return cls(
            prefix=data.get("prefix", prefix),
            chains=chains,
            version=data.get("version", CATALOG_VERSION),
        )
