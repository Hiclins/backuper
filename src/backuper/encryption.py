"""Encryption stages using `age` (https://age-encryption.org).

`age` is a small, modern, cross-platform tool. We encrypt to one or more
recipient public keys and decrypt with a private identity file.
"""

from __future__ import annotations

from pathlib import Path

from .config import EncryptionConfig, require_binary
from .errors import ConfigError

ENCRYPTED_EXT = ".age"


def encrypt_stage(enc: EncryptionConfig) -> tuple[list[str] | None, str]:
    """Return (command, extension) for encrypting stdin -> stdout."""
    if not enc.enabled:
        return None, ""
    if enc.backend != "age":
        raise ConfigError(f"unsupported encryption backend: {enc.backend}")
    binary = require_binary("age", "macOS: brew install age")
    cmd = [binary, "-e"]
    for recipient in enc.recipients:
        cmd += ["-r", recipient]
    return cmd, ENCRYPTED_EXT


def decrypt_stage(enc: EncryptionConfig, source: Path | None = None) -> list[str] | None:
    """Return a decryption command.

    If `source` is given, age reads that file directly (used as the first stage
    of a restore pipeline); otherwise it reads from stdin.
    """
    if not enc.enabled:
        return None
    binary = require_binary("age", "macOS: brew install age")
    if not enc.identity_file:
        raise ConfigError(
            "encryption.identity_file is required to decrypt (restore/verify)"
        )
    identity = Path(enc.identity_file).expanduser()
    if not identity.is_file():
        raise ConfigError(f"age identity file not found: {identity}")
    cmd = [binary, "-d", "-i", str(identity)]
    if source is not None:
        cmd.append(str(source))
    return cmd
