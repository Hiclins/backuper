"""Full backup -> restore roundtrip against real gtar."""

from __future__ import annotations

from helpers import assert_tree_equal


def test_full_backup_restore_roundtrip(make_config, source_tree, run_cli, tmp_path):
    config_path = make_config()

    backup_result = run_cli("-c", str(config_path), "backup")
    assert backup_result.code == 0

    restore_dest = tmp_path / "restored"
    restore_result = run_cli(
        "-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest)
    )
    assert restore_result.code == 0

    assert_tree_equal(source_tree, restore_dest)


def test_list_shows_one_chain_with_full_entry(make_config, run_cli):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")

    result = run_cli("-c", str(config_path), "list")
    assert result.code == 0
    assert "chain " in result.out
    assert "full" in result.out
    assert "1 backup(s)" in result.out


def test_verify_passes_after_a_clean_backup(make_config, run_cli):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")

    result = run_cli("-c", str(config_path), "verify")
    assert result.code == 0
