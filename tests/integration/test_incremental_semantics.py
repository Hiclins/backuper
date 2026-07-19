"""Incremental backup semantics: add/modify/delete replay through GNU tar
`--listed-incremental`. The delete-replay case is the single most important
scenario in this suite — it proves the tool's pipeline correctly propagates
GNU tar's incremental deletion tracking through to restore."""

from __future__ import annotations

from helpers import assert_tree_equal


def test_added_file_appears_after_incremental_restore(make_config, source_tree, run_cli, tmp_path):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")  # full

    new_file = source_tree / "added_later.txt"
    new_file.write_text("brand new\n", encoding="utf-8")
    result = run_cli("-c", str(config_path), "backup")  # incremental
    assert result.code == 0

    restore_dest = tmp_path / "restored"
    run_cli("-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest))
    assert_tree_equal(source_tree, restore_dest)
    assert (restore_dest / "added_later.txt").read_text(encoding="utf-8") == "brand new\n"


def test_modified_file_content_wins_after_incremental_restore(
    make_config, source_tree, run_cli, tmp_path
):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")  # full

    target = source_tree / "file1.txt"
    target.write_text("updated content\n", encoding="utf-8")
    run_cli("-c", str(config_path), "backup")  # incremental

    restore_dest = tmp_path / "restored"
    run_cli("-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest))
    assert (restore_dest / "file1.txt").read_text(encoding="utf-8") == "updated content\n"


def test_deleted_file_is_absent_after_incremental_restore(
    make_config, source_tree, run_cli, tmp_path
):
    """GNU tar's --listed-incremental records deletions at the DIRECTORY
    level: it emits a per-directory dumpdir of Y/N/D markers only for
    directories tar actually recurses into. A file deleted from a *recursed
    subdirectory* is correctly tracked as deleted; a top-level source that is
    itself a bare file argument (not nested under a recursed directory
    member) is not subject to this tracking, since no directory listing
    covers it. This test exercises the supported (subdirectory) case."""
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")  # full: includes subdir/file2.txt

    (source_tree / "subdir" / "file2.txt").unlink()
    result = run_cli("-c", str(config_path), "backup")  # incremental: records the deletion
    assert result.code == 0

    restore_dest = tmp_path / "restored"
    restore_result = run_cli(
        "-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest)
    )
    assert restore_result.code == 0
    assert not (restore_dest / "subdir" / "file2.txt").exists()
    # everything else survives, including the sibling dotfile in the same dir
    assert (restore_dest / "subdir" / ".dotfile").is_file()
    assert (restore_dest / "file1.txt").is_file()


def test_restore_to_earlier_target_excludes_later_incremental(
    make_config, source_tree, run_cli, tmp_path
):
    import time
    from datetime import datetime

    config_path = make_config()
    run_cli("-c", str(config_path), "backup")  # full (T0)

    time.sleep(1.1)  # ensure a distinguishable second-resolution timestamp
    (source_tree / "t1_file.txt").write_text("t1\n", encoding="utf-8")
    run_cli("-c", str(config_path), "backup")  # incremental at T1, completes

    time.sleep(1.1)
    t1_marker = datetime.now().isoformat()  # strictly after T1, before T2
    time.sleep(1.1)
    (source_tree / "t2_file.txt").write_text("t2\n", encoding="utf-8")
    run_cli("-c", str(config_path), "backup")  # incremental at T2

    restore_dest = tmp_path / "restored"
    result = run_cli(
        "-c", str(config_path), "restore", "--target", t1_marker, "--dest", str(restore_dest)
    )
    assert result.code == 0
    assert (restore_dest / "t1_file.txt").is_file()
    assert not (restore_dest / "t2_file.txt").exists()
