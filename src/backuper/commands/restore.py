"""`restore` command: rebuild a point in time from full + incrementals."""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path

from .. import pipeline
from ..backends import build_backends
from ..catalog import Catalog, Chain
from ..compression import decompressor_stage
from ..config import Config, resolve_gnu_tar
from ..encryption import decrypt_stage
from ..errors import BackuperError
from ..integrity import sha256_file
from .common import download_any, load_catalog

log = logging.getLogger(__name__)


def _build_stages(local: Path, chain: Chain, cfg: Config, tar_bin: str, dest: Path):
    """Build a decrypt? | decompress? | tar-extract pipeline for one artifact.

    The first stage reads the artifact file directly; later stages read stdin.
    tar extracts incrementally so deletions recorded in the archive are applied.
    """
    tar_cmd = [
        tar_bin,
        "--extract",
        "--listed-incremental=/dev/null",
        "-C",
        str(dest),
    ]

    transforms: list[list[str]] = []
    if chain.encrypted:
        transforms.append(decrypt_stage(cfg.encryption))  # type: ignore[arg-type]
    decomp = decompressor_stage(chain.compression)
    if decomp:
        transforms.append(decomp)

    if not transforms:
        return [pipeline.tar_stage(tar_cmd + ["-f", str(local)])]

    stages = [pipeline.strict_stage(list(transforms[0]) + [str(local)])]
    for extra in transforms[1:]:
        stages.append(pipeline.strict_stage(list(extra)))
    stages.append(pipeline.tar_stage(tar_cmd + ["-f", "-"]))
    return stages


def run(cfg: Config, args: Namespace) -> int:
    tar_bin = resolve_gnu_tar(cfg.archive.tar_binary)
    backends = build_backends(cfg.destinations, only=args.destination)
    catalog: Catalog = load_catalog(cfg, backends)

    found = catalog.find_chain_for_target(args.target)
    if not found:
        raise BackuperError(f"no backup found for target {args.target!r}")
    chain, last_level = found

    dest = Path(args.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    workdir = cfg.state_dir / "restore-tmp"
    workdir.mkdir(parents=True, exist_ok=True)

    applied = [b for b in chain.backups if b.level <= last_level]
    log.info(
        "restoring chain %s up to level %d (%d archive(s)) into %s",
        chain.id,
        last_level,
        len(applied),
        dest,
    )

    for entry in applied:
        local = workdir / entry.artifact
        source = download_any(backends, entry.artifact, local)
        log.info("level %d: %s (from %s)", entry.level, entry.artifact, source.name)

        actual = sha256_file(local)
        if actual != entry.sha256:
            raise BackuperError(
                f"integrity check failed for {entry.artifact}: "
                f"expected {entry.sha256[:16]}, got {actual[:16]}"
            )

        stages = _build_stages(local, chain, cfg, tar_bin, dest)
        pipeline.run_extract(stages)
        local.unlink(missing_ok=True)

    log.info("restore complete: %s", dest)
    return 0
