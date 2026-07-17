"""Compressor selection and command construction.

Algorithms are ordered by ratio (higher = smaller output):
    xz    -> LZMA2, best ratio, slowest (closest to the old .7z result)
    zstd  -> great ratio at high levels, much faster; supports a large window
    gzip  -> widely compatible, modest ratio
    none  -> passthrough (data already compressed)
"""

from __future__ import annotations

from .config import ArchiveConfig, require_binary
from .errors import ConfigError


def compressor_stage(archive: ArchiveConfig) -> tuple[list[str] | None, str]:
    """Return (command, file-extension) for compressing tar on stdin.

    The command reads from stdin and writes to stdout. Returns (None, "") when
    compression is disabled.
    """
    algo = archive.compression
    level = archive.level
    threads = archive.threads

    if algo == "none":
        return None, ""
    if algo == "xz":
        binary = require_binary("xz", "macOS: brew install xz")
        cmd = [binary, "-z", "-c", f"-{level}", f"-T{threads}"]
        if archive.extreme:
            cmd.append("-e")  # -9e squeezes out a bit more at higher CPU cost
        return cmd, ".xz"
    if algo == "zstd":
        binary = require_binary("zstd", "macOS: brew install zstd")
        cmd = [binary, "-z", "-c", f"-{level}", f"-T{threads}"]
        if archive.ultra:
            cmd.append("--ultra")  # required for levels 20..22
        if archive.long:
            cmd.append("--long=31")  # large-window matching for better ratio
        return cmd, ".zst"
    if algo == "gzip":
        binary = require_binary("gzip")
        return [binary, "-c", f"-{level}"], ".gz"
    raise ConfigError(f"unknown compression: {algo}")


def decompressor_stage(compression: str) -> list[str] | None:
    """Return a stdin->stdout decompression command for a stored algorithm."""
    if compression in ("none", ""):
        return None
    if compression == "xz":
        return [require_binary("xz"), "-d", "-c"]
    if compression == "zstd":
        # --long is harmless on decode and required if it was used on encode.
        return [require_binary("zstd"), "-d", "-c", "--long=31"]
    if compression == "gzip":
        return [require_binary("gzip"), "-d", "-c"]
    raise ConfigError(f"unknown compression: {compression}")
