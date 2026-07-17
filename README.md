# backuper

A modular backup tool written in Python, configured with a YAML file, with
**incremental** archives in a portable format, client-side encryption, and
multiple storage destinations.

## Features

- Full **or incremental** backups (GNU tar snapshots)
- Credentials from env / IAM by default (inline in config also supported)
- GFS retention applied over whole backup chains
- Client-side encryption (age, recipient public keys)
- `restore` + `verify` (SHA-256 integrity checks)
- Everything driven by one documented YAML config

## Incremental format

Incremental backups use **GNU tar `--listed-incremental`** (a `.snar` snapshot
file per chain). The archives themselves are plain `.tar` (optionally
compressed/encrypted), so they can be opened by any `tar` on any OS. A *chain*
is one full backup (level 0) plus the incrementals that follow it; restoring
applies the full and then each incremental in order.

There is no universal incremental format a generic GUI archiver understands
natively — GNU tar's is the closest de-facto standard, which is why it was
chosen.

## Requirements

- Python 3.11+
- **GNU tar** (`gtar` / `tar` that reports "GNU tar")
- **age** (only if `encryption.enabled`)
- **xz** / **zstd** / **gzip** (only the one selected by `archive.compression`)
- `boto3` (only if an S3 destination is configured): `pip install 'backuper[s3]'`

On macOS (development):

```sh
brew install gnu-tar age zstd xz
```

## Install

```sh
pip install -e .          # or: pip install -e '.[s3]' for S3 support
```

## Configure

Copy [`backuper.example.yaml`](backuper.example.yaml) — it documents every
option — to `./backuper.yaml`, `~/.config/backuper/config.yaml`, or
`/etc/backuper/config.yaml`.

### Sources and paths

`sources` entries may be absolute (`/etc`), relative, or globs (`*`, `../*`,
`data/*.db`). Globs are expanded on every run and `*` includes dotfiles. The
archive root is the common parent of the resolved sources, and members are
stored relative to it — so `restore --dest R` lays files out under `R` without
long absolute prefixes.

**Relative paths** (in `sources`, `state_dir`, a local destination `path`,
`identity_file`, `logging.file`) are resolved from the **directory of the config
file**, not the shell's cwd — so the same config behaves identically under cron
or from any directory. Absolute paths and `~` are unchanged. This makes a
"one config per projects folder" setup convenient:

```yaml
# ~/projects/backup.yaml
sources: ["*"]          # everything in ~/projects (incl. dotfiles)
state_dir: .backuper    # -> ~/projects/.backuper
```

Within a chain the root is pinned: incrementals reuse the full's root, and if
sources later move outside it, the next backup starts a new full automatically.

**Excludes** are gitignore-style and matched relative to the archive root. A
pattern may also be a real path — absolute, `~`, or `../backup` — which is
resolved from the config directory and matched by location (dropped with a
warning if it lies outside the backup).

### Full vs incremental cadence

`mode.full_interval` decides when a new full (a fresh chain) is started:

- **duration** — `7d` / `12h` / `30m`: full when the current full is older than this.
- **count** — a plain integer or `10i`: full after that many incrementals (e.g.
  `10` → a full, then 10 incrementals, then a full again).

`mode.full_on: sunday` can force a full on a given weekday. `backup --full`
always forces one.

### Maximum compression

- `compression: xz` with `level: 9` and `extreme: true` → best ratio (closest to
  the old `7z -mx=9`).
- `compression: zstd` with `level: 22`, `ultra: true`, `long: true` → almost the
  same ratio, much faster.

> Note: `long: true` uses a large zstd window. `backuper restore` handles it
> automatically, but decompressing such an archive with an external tool needs
> `zstd -d --long=31`. Leave `long: false` for the widest external compatibility.

### Encryption keys

```sh
age-keygen -o age.key          # prints the "Public key: age1..." recipient
```

Put the `age1...` public key under `encryption.recipients`; keep `age.key` as
`encryption.identity_file` (needed only for restore/verify).

## Usage

```sh
backuper backup                 # full or incremental, per config
backuper backup --full          # force a new full chain
backuper backup --dry-run       # show the plan, change nothing

backuper list                   # show chains and restore points
backuper verify --all           # re-download and check SHA-256 of everything

backuper restore --target latest --dest /tmp/restore
backuper restore --target 2026-07-17T12:00:00 --dest /tmp/restore

backuper prune                  # apply retention now
backuper prune --dry-run
```

Global flags: `-c/--config <path>`, `-v` / `-vv` (verbosity).

### Exit codes (for cron/monitoring)

| code | meaning                                             |
| ---- | --------------------------------------------------- |
| 0    | success                                             |
| 1    | generic runtime error (archiving, integrity, ...)   |
| 2    | configuration error / missing dependency            |
| 3    | backend error or partial upload / failed verify     |

## Architecture

The tool is deliberately modular; each concern is one small module under
`src/backuper/`:

- `config.py` — YAML → typed dataclasses, validation, binary discovery
- `pipeline.py` — runs the `tar | compress | encrypt` subprocess pipeline
- `compression.py`, `encryption.py`, `excludes.py`, `integrity.py` — stages
- `catalog.py` — JSON catalog of chains / restore points
- `retention.py` — GFS policy over whole chains
- `backends/` — `Backend` ABC + `local` / `s3` (+ `registry`); add a backend by
  dropping in one file and registering it
- `commands/` — `backup`, `restore`, `verify`, `list`, `prune`
- `cli.py` — argument parsing and dispatch

## Cron example

```cron
# nightly backup; capture non-zero exit for alerting
30 2 * * *  /usr/local/bin/backuper -c /etc/backuper/config.yaml backup || echo "backup failed ($?)" | mail -s backuper root
```
