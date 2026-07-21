"""Configuration loading, validation and external-binary discovery."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import yaml

from .errors import ConfigError, ToolNotFoundError

VALID_COMPRESSION = {"xz", "zstd", "gzip", "none"}
COMPRESSION_EXT = {"xz": ".xz", "zstd": ".zst", "gzip": ".gz", "none": ""}

# Candidate config locations, tried in order when --config is not given.
DEFAULT_CONFIG_PATHS = (
    "./backuper.yaml",
    "~/.config/backuper/config.yaml",
    "/etc/backuper/config.yaml",
)


@dataclass
class ArchiveConfig:
    name_prefix: str = "backup"
    compression: str = "zstd"
    level: int = 19
    extreme: bool = False  # xz: -e
    ultra: bool = False  # zstd: unlock levels 20..22
    long: bool = False  # zstd: --long=31
    threads: int = 0  # 0 -> all cores
    tar_binary: str = "auto"


@dataclass
class ModeConfig:
    strategy: str = "incremental"  # full | incremental
    # Duration ("7d"/"12h"/"30m") OR a count of incrementals before the next
    # full (int like 10, or "10i"/"10x").
    full_interval: str | int | None = "7d"
    full_on: str | None = None  # weekday name


@dataclass
class EncryptionConfig:
    enabled: bool = False
    backend: str = "age"
    recipients: list[str] = field(default_factory=list)
    identity_file: str | None = None


@dataclass
class RetentionConfig:
    keep_last: int = 3
    daily: int = 0
    weekly: int = 0
    monthly: int = 0
    yearly: int = 0


@dataclass
class LoggingConfig:
    level: str = "info"
    file: str | None = None
    json: bool = False


@dataclass
class Config:
    sources: list[str]
    exclude: list[str]
    archive: ArchiveConfig
    mode: ModeConfig
    encryption: EncryptionConfig
    destinations: list[dict]
    retention: RetentionConfig
    logging: LoggingConfig
    state_dir: Path
    config_path: Path
    base_dir: Path  # directory of the config file; anchor for relative paths


# --------------------------------------------------------------------------- #
# Loading & validation
# --------------------------------------------------------------------------- #
def resolve_path(value: str, base: Path) -> Path:
    """Resolve a config path: expand '~', keep absolute paths, and anchor
    relative paths at `base` (the config file's directory)."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()
def find_config_path(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise ConfigError(f"config file not found: {p}")
        return p
    env = os.environ.get("BACKUPER_CONFIG")
    candidates = [env] if env else []
    candidates += list(DEFAULT_CONFIG_PATHS)
    for cand in candidates:
        if not cand:
            continue
        p = Path(cand).expanduser()
        if p.is_file():
            return p
    raise ConfigError(
        "no config file found; pass --config or create one at "
        + " or ".join(DEFAULT_CONFIG_PATHS)
    )


def load_config(explicit: str | None) -> Config:
    path = find_config_path(explicit)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping: {path}")

    base_dir = path.parent

    archive = ArchiveConfig(**_section(raw, "archive"))
    mode = ModeConfig(**_section(raw, "mode"))
    encryption = EncryptionConfig(**_section(raw, "encryption"))
    retention = RetentionConfig(**_section(raw, "retention"))
    logging_cfg = LoggingConfig(**_section(raw, "logging"))

    # Relative paths are anchored at the config file's directory (not the shell
    # cwd), so a config behaves identically regardless of where it is run from.
    state_dir = resolve_path(
        raw.get("state_dir") or "~/.local/state/backuper", base_dir
    )
    if encryption.identity_file:
        encryption.identity_file = str(resolve_path(encryption.identity_file, base_dir))
    if logging_cfg.file:
        logging_cfg.file = str(resolve_path(logging_cfg.file, base_dir))

    destinations = list(raw.get("destinations") or [])
    for dest in destinations:
        if isinstance(dest, dict) and dest.get("type") == "local" and dest.get("path"):
            dest["path"] = str(resolve_path(dest["path"], base_dir))

    cfg = Config(
        sources=list(raw.get("sources") or []),
        exclude=list(raw.get("exclude") or []),
        archive=archive,
        mode=mode,
        encryption=encryption,
        destinations=destinations,
        retention=retention,
        logging=logging_cfg,
        state_dir=state_dir,
        config_path=path,
        base_dir=base_dir,
    )
    _validate(cfg)
    return cfg


def _section(raw: dict, name: str) -> dict:
    value = raw.get(name) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"'{name}' section must be a mapping")
    return value


def _validate(cfg: Config) -> None:
    if not cfg.sources:
        raise ConfigError("'sources' is empty; nothing to back up")
    # Sources may be absolute, relative (anchored at the config dir), or globs
    # (`*`, `../*`, ...). They are resolved and expanded at backup time in
    # sources.py, so no path-shape validation happens here.

    if cfg.archive.compression not in VALID_COMPRESSION:
        raise ConfigError(
            f"archive.compression must be one of {sorted(VALID_COMPRESSION)}"
        )
    if cfg.mode.strategy not in {"full", "incremental"}:
        raise ConfigError("mode.strategy must be 'full' or 'incremental'")

    if cfg.encryption.enabled and not cfg.encryption.recipients:
        raise ConfigError("encryption.enabled is true but no recipients are set")

    if not cfg.destinations:
        raise ConfigError("'destinations' is empty; nowhere to store backups")
    for dest in cfg.destinations:
        if not isinstance(dest, dict) or "type" not in dest:
            raise ConfigError(f"each destination needs a 'type': {dest!r}")

    # Warn (not fail) if credentials are inlined in a world-readable config.
    _warn_on_inline_secret_permissions(cfg)


def _warn_on_inline_secret_permissions(cfg: Config) -> None:
    has_inline = any(
        d.get("access_key_id") or d.get("secret_access_key")
        for d in cfg.destinations
    )
    if not has_inline:
        return
    import logging

    try:
        mode = cfg.config_path.stat().st_mode
    except OSError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        logging.getLogger(__name__).warning(
            "config %s contains inline AWS credentials but is group/other "
            "accessible; run: chmod 600 %s",
            cfg.config_path,
            cfg.config_path,
        )


# --------------------------------------------------------------------------- #
# Helpers used at run time
# --------------------------------------------------------------------------- #
def incremental_count(value: str | int | None) -> int | None:
    """If `full_interval` expresses a COUNT of incrementals rather than a
    duration, return that count; otherwise return None.

    Count forms: an int (10), a digit string ("10"), or a digit string with an
    'i'/'x' suffix ("10i", "10x"). Duration forms (with a d/h/m unit) return
    None so the caller falls back to `parse_interval`.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    if len(text) > 1 and text[-1] in ("i", "x") and text[:-1].isdigit():
        return int(text[:-1])
    return None


def parse_interval(text: str) -> timedelta:
    """Parse '7d', '12h', '30m' into a timedelta."""
    text = str(text).strip().lower()
    if not text:
        raise ConfigError("empty interval")
    unit = text[-1]
    try:
        amount = float(text[:-1])
    except ValueError as exc:
        raise ConfigError(f"invalid interval: {text!r}") from exc
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    raise ConfigError(f"invalid interval unit in {text!r} (use d/h/m)")


def resolve_gnu_tar(preferred: str = "auto") -> str:
    """Locate a GNU tar binary and return its path.

    macOS ships bsdtar as `tar`, which does not support --listed-incremental,
    so we probe `--version` for the string 'GNU tar'.
    """
    candidates = [preferred] if preferred and preferred != "auto" else ["gtar", "tar"]
    for cand in candidates:
        path = shutil.which(cand)
        if not path:
            continue
        try:
            out = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if "GNU tar" in out.stdout:
            return path
    raise ToolNotFoundError(
        "GNU tar not found. Install it (macOS: `brew install gnu-tar`, provides "
        "`gtar`) or set archive.tar_binary to its path."
    )


def require_binary(name: str, hint: str = "") -> str:
    path = shutil.which(name)
    if not path:
        suffix = f" ({hint})" if hint else ""
        raise ToolNotFoundError(f"required binary not found: {name}{suffix}")
    return path
