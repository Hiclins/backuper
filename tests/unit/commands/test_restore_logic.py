"""`_build_stages` pipeline-construction tests (commands/restore.py) — hermetic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backuper.catalog import Chain
from backuper.commands import restore as restore_mod


def _fake_decrypt_stage(enc):
    return ["age", "-d", "-i", "identity"]


def _fake_decompressor_stage(compression):
    if compression in ("none", ""):
        return None
    return [compression, "-d", "-c"]


@pytest.fixture(autouse=True)
def _patch_stages(monkeypatch):
    monkeypatch.setattr(restore_mod, "decrypt_stage", _fake_decrypt_stage)
    monkeypatch.setattr(restore_mod, "decompressor_stage", _fake_decompressor_stage)


def _chain(compression="none", encrypted=False) -> Chain:
    return Chain(id="c1", snapshot="c1.snar", compression=compression, encrypted=encrypted, backups=[])


def _cfg():
    return SimpleNamespace(encryption=None)


def test_no_transforms_single_tar_stage(tmp_path):
    chain = _chain(compression="none", encrypted=False)
    local = tmp_path / "artifact.tar"
    dest = tmp_path / "dest"
    stages = restore_mod._build_stages(local, chain, _cfg(), "tar", dest)
    assert len(stages) == 1
    cmd, ok_codes = stages[0]
    assert cmd[0] == "tar"
    assert "-f" in cmd
    assert str(local) in cmd
    assert ok_codes == {0, 1}


def test_compression_only_two_stages_decompress_then_tar(tmp_path):
    chain = _chain(compression="zstd", encrypted=False)
    local = tmp_path / "artifact.tar.zst"
    dest = tmp_path / "dest"
    stages = restore_mod._build_stages(local, chain, _cfg(), "tar", dest)
    assert len(stages) == 2
    decomp_cmd, decomp_ok = stages[0]
    assert decomp_cmd[0] == "zstd"
    assert str(local) in decomp_cmd
    assert decomp_ok == {0}
    tar_cmd, tar_ok = stages[1]
    assert tar_cmd[0] == "tar"
    assert "-f" in tar_cmd and "-" in tar_cmd
    assert tar_ok == {0, 1}


def test_encryption_only_two_stages_decrypt_then_tar(tmp_path):
    chain = _chain(compression="none", encrypted=True)
    local = tmp_path / "artifact.tar.age"
    dest = tmp_path / "dest"
    stages = restore_mod._build_stages(local, chain, _cfg(), "tar", dest)
    assert len(stages) == 2
    decrypt_cmd, decrypt_ok = stages[0]
    assert decrypt_cmd[0] == "age"
    assert str(local) in decrypt_cmd
    assert decrypt_ok == {0}
    tar_cmd, _ = stages[1]
    assert tar_cmd[0] == "tar"


def test_both_three_stages_decrypt_decompress_tar_in_order(tmp_path):
    chain = _chain(compression="xz", encrypted=True)
    local = tmp_path / "artifact.tar.xz.age"
    dest = tmp_path / "dest"
    stages = restore_mod._build_stages(local, chain, _cfg(), "tar", dest)
    assert len(stages) == 3
    decrypt_cmd, _ = stages[0]
    decomp_cmd, _ = stages[1]
    tar_cmd, _ = stages[2]
    assert decrypt_cmd[0] == "age"
    assert str(local) in decrypt_cmd
    assert decomp_cmd[0] == "xz"
    assert str(local) not in decomp_cmd  # reads stdin, not the artifact file directly
    assert tar_cmd[0] == "tar"
