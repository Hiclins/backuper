"""`backup` command: create a full or incremental archive and store it."""

from __future__ import annotations

import logging
import shutil
from argparse import Namespace
from datetime import datetime
from pathlib import Path

from .. import pipeline
from ..backends import build_backends
from ..catalog import CATALOG_NAME, CHAIN_FORMAT_VERSION, BackupEntry, Catalog, Chain
from ..compression import compressor_stage
from ..config import (
    COMPRESSION_EXT,
    Config,
    incremental_count,
    parse_interval,
    resolve_gnu_tar,
)
from ..encryption import ENCRYPTED_EXT, encrypt_stage
from ..errors import BackendError, BackuperError
from ..excludes import write_exclude_file
from ..integrity import sidecar_path, write_sidecar
from ..retention import select_chains_to_drop
from ..sources import common_root, members_relative_to, resolve_source_paths

log = logging.getLogger(__name__)


def _decide_full(cfg: Config, catalog: Catalog, now: datetime, force: bool) -> tuple[bool, str]:
    latest = catalog.latest_chain()
    if latest is None:
        return True, "no existing chain"
    if force:
        return True, "forced full"
    fi = cfg.mode.full_interval
    if fi is not None and fi != "":
        count = incremental_count(fi)
        if count is not None:
            # count-based: after `count` incrementals, the next backup is a full
            if latest.backups[-1].level >= count:
                return True, f"reached {count} incremental(s) since last full"
        elif now - latest.created >= parse_interval(str(fi)):
            return True, f"last full older than {fi}"
    if cfg.mode.full_on:
        same_day = latest.created.date() == now.date()
        if now.strftime("%A").lower() == cfg.mode.full_on.lower() and not same_day:
            return True, f"scheduled full on {cfg.mode.full_on}"
    return False, "continuing current chain"


def run(cfg: Config, args: Namespace) -> int:
    tar_bin = resolve_gnu_tar(cfg.archive.tar_binary)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    catalog = Catalog.load(cfg.state_dir, cfg.archive.name_prefix)
    backends = build_backends(cfg.destinations)

    now = datetime.now().replace(microsecond=0)

    # Resolve/expand sources now (picks up new files each run). The tar root is
    # the common parent of all resolved paths; members are relative to it.
    abs_sources = resolve_source_paths(cfg.sources, cfg.base_dir)
    if not abs_sources:
        raise BackuperError("no sources matched the configured patterns")
    computed_root = common_root(abs_sources)

    need_full, reason = _decide_full(cfg, catalog, now, args.full)

    # For an incremental, the chain must be consistent with the current config
    # (same compression/encryption), its snapshot must be available, and the
    # current sources must still fit under the chain's pinned root.
    chain = catalog.latest_chain()
    if not need_full:
        if (
            chain.compression != cfg.archive.compression
            or chain.encrypted != cfg.encryption.enabled
        ):
            need_full, reason = True, "compression/encryption changed since last full"
        elif not _ensure_snapshot(cfg, backends, chain.snapshot):
            need_full, reason = True, "snapshot file unavailable; starting new chain"
        elif chain.format_version != CHAIN_FORMAT_VERSION:
            need_full, reason = (
                True,
                f"chain uses format v{chain.format_version}, tool uses "
                f"v{CHAIN_FORMAT_VERSION}; starting new full",
            )
        elif members_relative_to(abs_sources, chain.root) is None:
            need_full, reason = True, "sources moved outside the chain's root"

    compression = cfg.archive.compression
    encrypted = cfg.encryption.enabled
    if need_full:
        chain_id = now.strftime("%Y%m%d-%H%M%S")
        snapshot_name = f"{cfg.archive.name_prefix}-{chain_id}.snar"
        level = 0
        root = computed_root
    else:
        chain_id = chain.id
        snapshot_name = chain.snapshot
        compression = chain.compression
        encrypted = chain.encrypted
        level = chain.next_level
        root = chain.root  # pinned: keep member names stable across the chain

    members = members_relative_to(abs_sources, root)

    comp_ext = COMPRESSION_EXT[compression]
    enc_ext = ENCRYPTED_EXT if encrypted else ""
    artifact = f"{cfg.archive.name_prefix}-{now:%Y-%m-%d-%H-%M-%S}-L{level}.tar{comp_ext}{enc_ext}"

    log.info(
        "%s backup (level %d, chain %s) - %s",
        "FULL" if need_full else "incremental",
        level,
        chain_id,
        reason,
    )

    # Build the tar|compress|encrypt pipeline. tar chdir's into `root` (the
    # common parent of the sources), so member names (and exclude patterns) are
    # relative to it, e.g. "root/backups" when root is "/".
    work_snar = cfg.state_dir / (snapshot_name + ".work")
    final_snar = cfg.state_dir / snapshot_name
    exclude_file = write_exclude_file(
        cfg.exclude, cfg.state_dir / "exclude.list", cfg.base_dir, root
    )

    tar_cmd = [
        tar_bin,
        "-c",
        f"--listed-incremental={work_snar}",
        "-C",
        root,
        "--warning=no-file-changed",
        "--warning=no-file-removed",
    ]
    if exclude_file:
        tar_cmd += ["--exclude-from", str(exclude_file)]
    tar_cmd += ["--", *members]

    stages = [pipeline.tar_stage(tar_cmd)]
    comp_cmd, _ext = compressor_stage(cfg.archive)
    if comp_cmd:
        stages.append(pipeline.strict_stage(comp_cmd))
    enc_cmd, _enc_ext = encrypt_stage(cfg.encryption)
    if enc_cmd:
        stages.append(pipeline.strict_stage(enc_cmd))

    if args.dry_run:
        return _dry_run(cfg, catalog, artifact, stages, backends)

    # -- execute ------------------------------------------------------------ #
    staging = cfg.state_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    out_path = staging / artifact

    if need_full:
        work_snar.unlink(missing_ok=True)  # fresh snapshot for a new chain
    else:
        shutil.copy2(final_snar, work_snar)  # work on a copy for atomicity

    log.info("creating %s", artifact)
    digest, size = pipeline.run_capture(stages, out_path)
    sidecar = write_sidecar(out_path, digest)
    work_snar.replace(final_snar)  # commit the updated snapshot
    log.info("archive %s: %d bytes, sha256=%s", artifact, size, digest[:16])

    entry = BackupEntry(
        timestamp=now.isoformat(),
        level=level,
        artifact=artifact,
        sha256=digest,
        size=size,
    )
    if need_full:
        chain = Chain(
            id=chain_id,
            snapshot=snapshot_name,
            compression=compression,
            encrypted=encrypted,
            root=root,
            format_version=CHAIN_FORMAT_VERSION,
            backups=[entry],
        )
        catalog.add_chain(chain)
    else:
        chain.backups.append(entry)
    catalog.save(cfg.state_dir)

    # -- upload to every destination ---------------------------------------- #
    items = [
        (out_path, artifact),
        (sidecar, sidecar.name),
        (final_snar, snapshot_name),
        (cfg.state_dir / CATALOG_NAME, CATALOG_NAME),
    ]
    failures = upload_many_local(backends, items)

    if failures:
        log.error(
            "backup stored to %d/%d destinations; keeping staging copy in %s",
            len(backends) - len(failures),
            len(backends),
            staging,
        )
        raise BackendError(
            "upload failed for: " + ", ".join(sorted(failures))
        )

    # Uploaded everywhere - clean staging and apply retention.
    out_path.unlink(missing_ok=True)
    sidecar.unlink(missing_ok=True)
    _apply_retention(cfg, catalog, backends)
    log.info("backup complete")
    return 0


def _ensure_snapshot(cfg: Config, backends, snapshot_name: str) -> bool:
    """Make sure the chain snapshot exists locally (fetch it if needed)."""
    local = cfg.state_dir / snapshot_name
    if local.is_file():
        return True
    from .common import download_any

    try:
        download_any(backends, snapshot_name, local)
        log.info("recovered snapshot %s from a destination", snapshot_name)
        return True
    except BackendError:
        return False


def _dry_run(cfg: Config, catalog: Catalog, artifact: str, stages, backends) -> int:
    print(f"[dry-run] would create: {artifact}")
    print("[dry-run] pipeline:")
    for cmd, _ok in stages:
        print("    " + " ".join(cmd) + " |")
    print(f"[dry-run] destinations: {', '.join(b.name for b in backends)}")
    drop, _keep = select_chains_to_drop(catalog.chains, cfg.retention)
    if drop:
        print("[dry-run] retention would drop chains:")
        for chain in drop:
            print(f"    {chain.id} ({len(chain.backups)} backups)")
    else:
        print("[dry-run] retention: nothing to prune")
    return 0


# Thin wrappers so this module stays importable even if common.py grows.
def upload_many_local(backends, items):
    from .common import upload_many

    return upload_many(backends, items)


def _apply_retention(cfg, catalog, backends):
    from .common import apply_retention

    apply_retention(cfg, catalog, backends, dry_run=False)
