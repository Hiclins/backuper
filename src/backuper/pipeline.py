"""Run a `tar | compress | encrypt` style pipeline of subprocesses.

A stage is a (command, ok_codes) pair. Stages are connected stdout->stdin.
GNU tar legitimately exits 1 ("some files changed/removed while reading") on a
live filesystem, so its stage passes ok_codes={0, 1}.

stderr of every stage is redirected to a temporary regular file (not a pipe) so
a chatty stage cannot deadlock the pipeline by filling a stderr pipe buffer.
"""

from __future__ import annotations

import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

from .errors import PipelineError

CHUNK = 1 << 16

# A stage: (argv, set of acceptable exit codes).
Stage = tuple[list[str], set[int]]


def tar_stage(cmd: list[str]) -> Stage:
    return (cmd, {0, 1})


def strict_stage(cmd: list[str]) -> Stage:
    return (cmd, {0})


def _start(stages: list[Stage], last_stdout: int) -> tuple[list, list]:
    procs: list[subprocess.Popen] = []
    stderr_files: list = []
    prev_stdout = None
    for index, (cmd, _ok) in enumerate(stages):
        is_last = index == len(stages) - 1
        stderr_file = tempfile.TemporaryFile()
        proc = subprocess.Popen(
            cmd,
            stdin=prev_stdout,
            stdout=(last_stdout if is_last else subprocess.PIPE),
            stderr=stderr_file,
        )
        # Close our copy of the upstream's read end so only the child holds it.
        if prev_stdout is not None:
            prev_stdout.close()
        prev_stdout = proc.stdout if not is_last else None
        procs.append(proc)
        stderr_files.append(stderr_file)
    return procs, stderr_files


def _finish(stages: list[Stage], procs: list, stderr_files: list) -> None:
    problems: list[str] = []
    for (cmd, ok_codes), proc, stderr_file in zip(stages, procs, stderr_files):
        ret = proc.wait()
        stderr_file.seek(0)
        message = stderr_file.read().decode(errors="replace").strip()
        stderr_file.close()
        if ret not in ok_codes:
            snippet = f": {message[:500]}" if message else ""
            problems.append(f"{Path(cmd[0]).name} exited {ret}{snippet}")
    if problems:
        raise PipelineError("; ".join(problems))


def run_capture(stages: list[Stage], output_path: Path) -> tuple[str, int]:
    """Run the pipeline, streaming the final stdout into `output_path`.

    Returns (sha256_hex, size_bytes) of the produced file.
    """
    procs, stderr_files = _start(stages, subprocess.PIPE)
    try:
        digest = sha256()
        size = 0
        final = procs[-1]
        with open(output_path, "wb") as out:
            while True:
                chunk = final.stdout.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        final.stdout.close()
        _finish(stages, procs, stderr_files)
        return digest.hexdigest(), size
    except BaseException:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
        raise


def run_extract(stages: list[Stage]) -> None:
    """Run the pipeline for its side effects (e.g. tar extraction), no output."""
    procs, stderr_files = _start(stages, subprocess.DEVNULL)
    try:
        _finish(stages, procs, stderr_files)
    except BaseException:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
        raise
