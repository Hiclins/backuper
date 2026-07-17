# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`backuper` is a Python CLI backup tool. It produces **incremental** archives
using GNU tar snapshots, optionally compressed and age-encrypted, and stores
them to one or more destinations (local dir, S3). Configuration is a single
YAML file; `backuper.example.yaml` is the documented template.

All code and config comments are written in **English**.

## Commands

```sh
pip install -e .            # dev install; use '.[s3]' to include boto3 for S3

# Run the CLI (console script or module form):
backuper -c config.yaml <command>
python -m backuper -c config.yaml <command>

# Subcommands:
backuper -c CFG backup [--full] [-n/--dry-run]
backuper -c CFG restore --target <latest|ISO8601> --dest DIR [--destination NAME]
backuper -c CFG verify [--all] [--destination NAME]
backuper -c CFG list
backuper -c CFG prune [-n/--dry-run]
```

There is no test suite yet. Verification is done end-to-end against a temporary
local destination (see "Verifying changes"). External binaries are required at
runtime: **GNU tar** (`gtar`), **age** (if encryption on), and the selected
compressor (`xz`/`zstd`/`gzip`). On macOS: `brew install gnu-tar age zstd xz`
(GNU tar installs as `gtar`; the system `tar` is bsdtar and will NOT work for
incremental backups — `config.resolve_gnu_tar` probes `--version` for "GNU tar").

## Architecture

The design is deliberately modular; each concern is one small module under
`src/backuper/`. Data flows: **config → command → pipeline of subprocess stages
→ backends**, with a JSON **catalog** as the source of truth for what exists.

### Core domain concepts (understand these first)

- **Chain** (`catalog.py`): one full backup (level 0) plus the incrementals that
  follow it, all sharing a single GNU tar snapshot (`.snar`) file. Restore
  applies the full then each incremental in order; deletions are handled by GNU
  tar's incremental extract.
- **Catalog** (`catalog.py`): `catalog.json` listing all chains and their
  backups (timestamp, level, artifact name, sha256, size). Lives in `state_dir`
  and is **also mirrored to every backend** so restore works on a fresh machine.
  `Catalog.find_chain_for_target` resolves a `--target` to (chain, last level).
- **Retention** (`retention.py`): GFS policy that operates on **whole chains**,
  never individual artifacts — this is the key invariant that prevents orphaning
  an incremental from the full it depends on.

### The pipeline (`pipeline.py`)

Backups and restores run a chain of subprocesses connected stdout→stdin:
`tar | compress | encrypt` (backup) or `decrypt | decompress | tar-extract`
(restore). Stages are `(argv, ok_codes)` tuples. Two things to respect when
editing:
- The **tar stage uses `ok_codes={0,1}`** because GNU tar exits 1 (non-fatal)
  when files change on a live filesystem. Other stages are strict (`{0}`).
- Each stage's **stderr is redirected to a temp file**, not a pipe, to avoid
  deadlock from a chatty stage. Don't switch stderr back to `PIPE`.

`run_capture` streams the final stdout to a file while computing SHA-256 on the
fly; `run_extract` runs for side effects (tar writes to disk, no captured
output).

### Source resolution & tar rooting (`sources.py`)

Sources may be absolute, relative (anchored at the **config file's directory**,
`cfg.base_dir`), or globs (`*`, `../*`; `*` includes dotfiles via
`include_hidden=True`). `resolve_source_paths` expands them **at backup time**;
`common_root` picks the tar `-C` directory (the common parent) and members are
stored relative to it. The old server behavior (`/etc`,`/root` → root `/`) is
just the special case where the common parent is `/`.

**Root is pinned per chain**: `Chain.root` (catalog) is set from the full; an
incremental reuses it so member names stay stable and the `.snar` stays in sync.
If current sources escape the chain's root (`members_relative_to` returns None),
`backup.py` promotes to a new full — same pattern as the compression/encryption
mismatch and missing-snapshot promotions. Other config paths (`state_dir`,
`identity_file`, `logging.file`, local `path`) are resolved against `base_dir`
in `config.py` at load time.

### Backup mechanics (`commands/backup.py`)

- Archives are created relative to the chain root (`tar -C <root> <member>`), so
  member names and exclude patterns are relative to it (e.g. `root/backups` when
  the root is `/`).
- Full-vs-incremental is decided by `_decide_full` (no chain / `--full` /
  `full_interval` / `full_on`). An incremental is **promoted to full** if the
  chain's compression/encryption no longer matches config, or its `.snar` can't
  be found (it's fetched from a backend if missing locally).
- The `.snar` is updated on a **`.work` copy** and only `replace()`d into place
  after a successful archive — keep this atomicity.
- On any upload failure the staging copy is **kept** and the command raises
  `BackendError` (exit 3); retention only runs after a fully successful upload.

### Backends (`backends/`)

`Backend` ABC (`base.py`) is a flat namespace of named blobs (artifacts,
`.sha256` sidecars, `.snar`, `catalog.json`). Add a destination type by writing
one module and registering it in `registry.py` — nothing else changes. `boto3`
is imported lazily inside `s3.py` so the tool runs without it when only local is
used. S3 credentials come from the standard AWS chain unless inlined in config.

### Config & errors

- `config.py` loads YAML into dataclasses and validates. `parse_interval`
  handles `7d`/`12h`/`30m`. Binary discovery (`resolve_gnu_tar`,
  `require_binary`) raises `ToolNotFoundError` (a `ConfigError`).
- `errors.py` maps exception classes to **process exit codes**, the contract for
  cron/monitoring: `0` ok · `1` runtime · `2` config/missing-dependency · `3`
  backend error or failed verify. `cli.main` catches `BackuperError` and returns
  `exc.exit_code`.

## Constraints / gotchas

- Sources may be absolute, config-dir-relative, or globs (see "Source resolution"
  above); they are no longer required to be absolute.
- Exclude patterns are gitignore-style but translated to GNU tar `--exclude-from`
  (`excludes.py`); **negation (`!`) is not supported** and is dropped with a
  warning.
- `archive.long: true` (zstd) yields archives that external `zstd -d` needs
  `--long=31` to open; `backuper restore` always passes it, but it reduces
  external portability.
