"""age encryption integration tests: real encrypt/decrypt through the CLI."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from helpers import assert_tree_equal

pytestmark = pytest.mark.skipif(shutil.which("age") is None, reason="age not installed")


def _sole_artifact(dest_dir):
    tar_files = [p for p in dest_dir.iterdir() if ".tar" in p.name and not p.name.endswith(".sha256")]
    assert len(tar_files) == 1, f"expected exactly one artifact, found {tar_files}"
    return tar_files[0]


def test_encrypted_backup_restore_roundtrip(make_config, source_tree, run_cli, tmp_path, age_identity):
    identity, recipient = age_identity
    config_path = make_config(
        encryption={"enabled": True, "recipients": [recipient], "identity_file": str(identity)}
    )
    result = run_cli("-c", str(config_path), "backup")
    assert result.code == 0

    artifact = _sole_artifact(tmp_path / "dest")
    assert artifact.name.endswith(".age")

    restore_dest = tmp_path / "restored"
    restore_result = run_cli(
        "-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest)
    )
    assert restore_result.code == 0
    assert_tree_equal(source_tree, restore_dest)


def test_verify_passes_on_encrypted_archive(make_config, run_cli, age_identity):
    identity, recipient = age_identity
    config_path = make_config(
        encryption={"enabled": True, "recipients": [recipient], "identity_file": str(identity)}
    )
    run_cli("-c", str(config_path), "backup")
    result = run_cli("-c", str(config_path), "verify")
    assert result.code == 0


def test_restore_with_wrong_identity_fails(make_config, run_cli, tmp_path, age_identity):
    identity, recipient = age_identity
    config_path = make_config(
        encryption={"enabled": True, "recipients": [recipient], "identity_file": str(identity)}
    )
    run_cli("-c", str(config_path), "backup")

    wrong_identity = tmp_path / "wrong.key"
    subprocess.run(["age-keygen", "-o", str(wrong_identity)], capture_output=True, check=True)

    # Same destinations/state_dir (shared tmp_path defaults), different identity.
    wrong_config_path = make_config(
        _name="wrong",
        encryption={"enabled": True, "recipients": [recipient], "identity_file": str(wrong_identity)},
    )
    restore_dest = tmp_path / "restored"
    result = run_cli(
        "-c", str(wrong_config_path), "restore", "--target", "latest", "--dest", str(restore_dest)
    )
    assert result.code == 1  # PipelineError from age failing to decrypt


def test_encryption_disabled_by_default_control_case(make_config, run_cli, tmp_path):
    config_path = make_config()  # encryption disabled by default
    result = run_cli("-c", str(config_path), "backup")
    assert result.code == 0
    artifact = _sole_artifact(tmp_path / "dest")
    assert not artifact.name.endswith(".age")
