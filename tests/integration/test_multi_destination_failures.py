"""Multi-destination behavior: partial upload failure, --destination scoping."""

from __future__ import annotations

import os

import pytest

from backuper.config import load_config


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="permission bits are ignored when running as root",
)
def test_partial_upload_failure_exit_code_3_keeps_staging(make_config, run_cli, tmp_path):
    good_dest = tmp_path / "good_dest"
    bad_dest = tmp_path / "bad_dest"
    good_dest.mkdir()
    bad_dest.mkdir()

    config_path = make_config(
        destinations=[
            {"type": "local", "name": "good", "path": str(good_dest)},
            {"type": "local", "name": "bad", "path": str(bad_dest)},
        ]
    )
    # Make bad_dest unwritable AFTER backend construction succeeds, so the
    # failure happens inside upload()'s shutil.copy2, not backend __init__.
    os.chmod(bad_dest, 0o555)
    try:
        result = run_cli("-c", str(config_path), "backup")
    finally:
        os.chmod(bad_dest, 0o755)  # restore so tmp_path cleanup can remove it

    assert result.code == 3

    cfg = load_config(str(config_path))
    staging_dir = cfg.state_dir / "staging"
    staged_files = list(staging_dir.iterdir()) if staging_dir.is_dir() else []
    assert staged_files, "staging copy should be kept on partial upload failure"

    good_files = [p for p in good_dest.iterdir() if ".tar" in p.name]
    assert good_files, "the working destination should still have received the artifact"


def test_destination_scoped_restore_and_verify(make_config, run_cli, tmp_path):
    dest_a = tmp_path / "dest_a"
    dest_b = tmp_path / "dest_b"
    config_path = make_config(
        destinations=[
            {"type": "local", "name": "a", "path": str(dest_a)},
            {"type": "local", "name": "b", "path": str(dest_b)},
        ]
    )
    run_cli("-c", str(config_path), "backup")

    restore_dest = tmp_path / "restored"
    restore_result = run_cli(
        "-c",
        str(config_path),
        "restore",
        "--target",
        "latest",
        "--dest",
        str(restore_dest),
        "--destination",
        "a",
    )
    assert restore_result.code == 0

    verify_result = run_cli("-c", str(config_path), "verify", "--destination", "b")
    assert verify_result.code == 0
