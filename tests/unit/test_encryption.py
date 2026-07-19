"""age encryption command-construction tests (encryption.py) — hermetic."""

from __future__ import annotations

import pytest

from backuper import encryption
from backuper.config import EncryptionConfig
from backuper.errors import ConfigError


def _enc(**overrides) -> EncryptionConfig:
    defaults = dict(enabled=True, backend="age", recipients=["age1abc"], identity_file=None)
    defaults.update(overrides)
    return EncryptionConfig(**defaults)


@pytest.fixture(autouse=True)
def _fake_require_binary(monkeypatch):
    monkeypatch.setattr(encryption, "require_binary", lambda name, hint="": f"/usr/bin/{name}")


def test_encrypt_stage_disabled_returns_none():
    cmd, ext = encryption.encrypt_stage(_enc(enabled=False))
    assert cmd is None
    assert ext == ""


def test_encrypt_stage_single_recipient():
    cmd, ext = encryption.encrypt_stage(_enc(recipients=["age1abc"]))
    assert cmd == ["/usr/bin/age", "-e", "-r", "age1abc"]
    assert ext == ".age"


def test_encrypt_stage_multiple_recipients_each_get_flag():
    cmd, _ = encryption.encrypt_stage(_enc(recipients=["age1abc", "age1def"]))
    assert cmd == ["/usr/bin/age", "-e", "-r", "age1abc", "-r", "age1def"]


def test_encrypt_stage_unsupported_backend_raises():
    with pytest.raises(ConfigError):
        encryption.encrypt_stage(_enc(backend="gpg"))


def test_decrypt_stage_disabled_returns_none():
    assert encryption.decrypt_stage(_enc(enabled=False)) is None


def test_decrypt_stage_missing_identity_file_config_raises():
    with pytest.raises(ConfigError):
        encryption.decrypt_stage(_enc(identity_file=None))


def test_decrypt_stage_identity_file_not_on_disk_raises(tmp_path):
    with pytest.raises(ConfigError):
        encryption.decrypt_stage(_enc(identity_file=str(tmp_path / "nope.key")))


def test_decrypt_stage_builds_command(tmp_path):
    identity = tmp_path / "id.key"
    identity.write_text("AGE-SECRET-KEY-1EXAMPLE\n", encoding="utf-8")
    cmd = encryption.decrypt_stage(_enc(identity_file=str(identity)))
    assert cmd == ["/usr/bin/age", "-d", "-i", str(identity)]


def test_decrypt_stage_with_source_appends_it(tmp_path):
    identity = tmp_path / "id.key"
    identity.write_text("AGE-SECRET-KEY-1EXAMPLE\n", encoding="utf-8")
    source = tmp_path / "archive.tar.age"
    cmd = encryption.decrypt_stage(_enc(identity_file=str(identity)), source=source)
    assert cmd[-1] == str(source)
