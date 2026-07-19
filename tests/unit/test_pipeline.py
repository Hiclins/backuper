"""Subprocess pipeline tests (pipeline.py).

Stages use `sys.executable -c ...` so this stays hermetic and cross-platform
(real subprocesses, but only Python itself — never an external tar/age/
compressor binary).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from backuper import pipeline
from backuper.errors import PipelineError


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_run_capture_single_stage_hashes_and_sizes(tmp_path):
    content = b"hello world"
    stages = [pipeline.strict_stage(_py(f"import sys; sys.stdout.buffer.write({content!r})"))]
    out = tmp_path / "out.bin"
    digest, size = pipeline.run_capture(stages, out)
    assert size == len(content)
    assert digest == hashlib.sha256(content).hexdigest()
    assert out.read_bytes() == content


def test_run_capture_multi_stage_chain(tmp_path):
    content = b"chained data"
    producer = _py(f"import sys; sys.stdout.buffer.write({content!r})")
    passthrough = _py("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())")
    stages = [pipeline.strict_stage(producer), pipeline.strict_stage(passthrough)]
    out = tmp_path / "out.bin"
    digest, size = pipeline.run_capture(stages, out)
    assert out.read_bytes() == content
    assert digest == hashlib.sha256(content).hexdigest()


def test_strict_stage_failure_raises_pipeline_error(tmp_path):
    stages = [pipeline.strict_stage(_py("import sys; sys.exit(3)"))]
    with pytest.raises(PipelineError):
        pipeline.run_capture(stages, tmp_path / "out.bin")


def test_tar_stage_tolerates_exit_code_1(tmp_path):
    stages = [pipeline.tar_stage(_py("import sys; sys.stdout.buffer.write(b'ok'); sys.exit(1)"))]
    out = tmp_path / "out.bin"
    digest, size = pipeline.run_capture(stages, out)  # must not raise
    assert out.read_bytes() == b"ok"
    assert size == 2


def test_error_message_includes_stderr_snippet_and_binary_name(tmp_path):
    stages = [
        pipeline.strict_stage(_py("import sys; sys.stderr.write('boom-message'); sys.exit(2)"))
    ]
    with pytest.raises(PipelineError) as excinfo:
        pipeline.run_capture(stages, tmp_path / "out.bin")
    message = str(excinfo.value)
    assert "boom-message" in message
    assert Path(sys.executable).name in message


def test_multiple_stage_failures_aggregated_in_message(tmp_path):
    stage_a = pipeline.strict_stage(_py("import sys; sys.exit(2)"))
    stage_b = pipeline.strict_stage(
        _py("import sys; sys.stdin.buffer.read(); sys.exit(5)")
    )
    with pytest.raises(PipelineError) as excinfo:
        pipeline.run_capture([stage_a, stage_b], tmp_path / "out.bin")
    message = str(excinfo.value)
    assert "exited 2" in message
    assert "exited 5" in message
    assert "; " in message


def test_run_extract_side_effect_only_no_output(tmp_path):
    marker = tmp_path / "marker.txt"
    code = f"open({str(marker)!r}, 'w').write('done')"
    stages = [pipeline.strict_stage(_py(code))]
    result = pipeline.run_extract(stages)
    assert result is None
    assert marker.read_text(encoding="utf-8") == "done"


def test_run_extract_raises_on_failure():
    stages = [pipeline.strict_stage(_py("import sys; sys.exit(1)"))]
    with pytest.raises(PipelineError):
        pipeline.run_extract(stages)


def test_run_capture_kills_procs_and_propagates_on_bad_output_path(tmp_path):
    out_dir = tmp_path / "out_is_a_dir"
    out_dir.mkdir()
    stages = [pipeline.strict_stage(_py("import sys; sys.stdout.buffer.write(b'x' * 10_000_000)"))]
    with pytest.raises(IsADirectoryError):
        pipeline.run_capture(stages, out_dir)
