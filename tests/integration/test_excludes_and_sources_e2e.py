"""Real end-to-end exclude patterns and glob re-expansion through the CLI."""

from __future__ import annotations


def test_exclude_pattern_removes_matching_files_from_archive(
    make_config, source_tree, run_cli, tmp_path
):
    (source_tree / "debug.log").write_text("log content\n", encoding="utf-8")
    config_path = make_config(exclude=["*.log"])
    result = run_cli("-c", str(config_path), "backup")
    assert result.code == 0

    restore_dest = tmp_path / "restored"
    run_cli("-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest))
    assert not (restore_dest / "debug.log").exists()
    assert (restore_dest / "file1.txt").is_file()  # everything else survives


def test_glob_source_reexpands_and_picks_up_new_files_each_run(
    make_config, source_tree, run_cli, tmp_path
):
    config_path = make_config()
    run_cli("-c", str(config_path), "backup")  # full: new_file doesn't exist yet

    new_file = source_tree / "new_file.txt"
    new_file.write_text("added between runs\n", encoding="utf-8")
    result = run_cli("-c", str(config_path), "backup")  # incremental re-expands the glob
    assert result.code == 0

    restore_dest = tmp_path / "restored"
    run_cli("-c", str(config_path), "restore", "--target", "latest", "--dest", str(restore_dest))
    assert (restore_dest / "new_file.txt").read_text(encoding="utf-8") == "added between runs\n"
