"""PERCEIVE: find every failing test in a repo, then capture one test's
output and the source it touches.

Two levels, both running inside the Sandbox (never on the host, per the
project's compliance requirement):

- `discover_failures` runs the whole suite once and parses pytest's
  "short test summary info" block to get every distinct failing test as
  its own issue — this is what lets the orchestrator treat "all the bugs
  in a repo" as a worklist instead of one lumped-together failure.
- `perceive_one` re-runs a single test in isolation to get a clean,
  single-issue traceback and the source files it touches, which is what
  actually goes to the PLAN step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from greenlit.clients.sandbox import Sandbox, SandboxResult

_TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)", line (\d+)')
_SUMMARY_FAILED_RE = re.compile(r"^FAILED (\S+)(?: - (.*))?$", re.MULTILINE)
_MAX_SOURCE_FILES = 5


@dataclass
class FailingTest:
    test_id: str  # e.g. "test_app.py::test_greeting"
    reason: str  # one-line reason from pytest's summary, may be empty


@dataclass
class PerceivedFailure:
    stack_trace: str
    source_files: dict[str, str]
    exit_code: int


def discover_failures(
    sandbox: Sandbox, repo_dir: Path, full_test_command: str
) -> tuple[list[FailingTest], SandboxResult]:
    """Run the whole suite once. Returns every distinct failing test (empty
    list if the suite already passes) plus the raw sandbox result."""
    result = sandbox.run_tests(repo_dir, full_test_command)
    combined = f"{result.stdout}\n{result.stderr}"
    failures = [
        FailingTest(test_id=m.group(1), reason=(m.group(2) or "").strip())
        for m in _SUMMARY_FAILED_RE.finditer(combined)
    ]
    return failures, result


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


def perceive_one(sandbox: Sandbox, repo_dir: Path, scoped_test_command: str) -> PerceivedFailure:
    """`scoped_test_command` must run exactly one test (e.g. the full
    command with a pytest node id like `test_app.py::test_greeting`
    appended), so the resulting traceback is about a single issue."""
    result = sandbox.run_tests(repo_dir, scoped_test_command)
    combined_output = f"{result.stdout}\n{result.stderr}".strip()

    touched = _touched_files(combined_output, repo_dir)
    source_files = {rel: (repo_dir / rel).read_text() for rel in touched}

    return PerceivedFailure(
        stack_trace=combined_output,
        source_files=source_files,
        exit_code=result.exit_code,
    )
