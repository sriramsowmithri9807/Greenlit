"""PERCEIVE: capture a failing test's output and the source it touches.

Runs the test command inside the Sandbox (never on the host, per the
project's compliance requirement) and parses the resulting output for a
Python traceback to identify which source files to hand the PLAN step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from greenlit.clients.sandbox import Sandbox

_TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)", line (\d+)')
_MAX_SOURCE_FILES = 5


@dataclass
class PerceivedFailure:
    stack_trace: str
    source_files: dict[str, str]
    exit_code: int


def _touched_files(output: str, repo_dir: Path) -> list[str]:
    """Files referenced in a traceback that actually exist in the repo
    (skips stdlib/site-packages frames, which won't resolve under repo_dir)."""
    seen: list[str] = []
    for match in _TRACEBACK_FILE_RE.finditer(output):
        rel = match.group(1).removeprefix("/work/")
        if rel in seen:
            continue
        if (repo_dir / rel).is_file():
            seen.append(rel)
        if len(seen) >= _MAX_SOURCE_FILES:
            break
    return seen


def perceive(sandbox: Sandbox, repo_dir: Path, test_command: str) -> PerceivedFailure:
    result = sandbox.run_tests(repo_dir, test_command)
    combined_output = f"{result.stdout}\n{result.stderr}".strip()

    touched = _touched_files(combined_output, repo_dir)
    source_files = {rel: (repo_dir / rel).read_text() for rel in touched}

    return PerceivedFailure(
        stack_trace=combined_output,
        source_files=source_files,
        exit_code=result.exit_code,
    )
