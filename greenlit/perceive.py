"""PERCEIVE: run a repo's suite and find what's broken, then capture one
failing test's output and the source it touches.

Both run inside the Sandbox, never on the host, per the project's
compliance requirement:

- `run_suite` runs the whole suite and parses pytest's short test summary
  into distinct failures. Collection errors caused by a missing
  third-party package are split out as environment problems rather than
  code bugs, so the agent doesn't file "numpy isn't installed" as an issue.
- `perceive_one` re-runs a single test in isolation to get a clean,
  single-issue traceback plus the repo source files it touches, which is
  what goes to the PLAN step.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from greenlit.clients.sandbox import Sandbox

_TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)", line (\d+)')
_PYTEST_LOCATION_RE = re.compile(r"^([\w./-]+\.py):(\d+):", re.MULTILINE)
_SUMMARY_RE = re.compile(r"^(FAILED|ERROR) (\S+)(?: - (.*))?$", re.MULTILINE)
_PYTEST_RESULT_RE = re.compile(
    r"\b(?:\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|deselected)|no tests ran)\b"
)
_MAX_SOURCE_FILES = 5
PYTEST_NO_TESTS_COLLECTED = 5


@dataclass
class FailingTest:
    test_id: str  # pytest node id, e.g. "tests/test_calc.py::test_add"
    reason: str  # one-line reason from pytest's summary, may be empty


@dataclass
class SuiteRun:
    exit_code: int
    output: str
    failures: list[FailingTest] = field(default_factory=list)
    env_errors: list[FailingTest] = field(default_factory=list)

    @property
    def no_tests(self) -> bool:
        return self.exit_code == PYTEST_NO_TESTS_COLLECTED

    @property
    def ran(self) -> bool:
        """False when pytest never produced a result line, e.g. because the
        install step failed before it started."""
        return bool(_PYTEST_RESULT_RE.search(self.output))

    @property
    def problem_ids(self) -> set[str]:
        """Everything that isn't passing — used to detect a fix that breaks
        something that used to work."""
        return {f.test_id for f in self.failures} | {e.test_id for e in self.env_errors}


def parse_suite_output(exit_code: int, output: str) -> SuiteRun:
    run = SuiteRun(exit_code=exit_code, output=output)
    seen: set[str] = set()
    for match in _SUMMARY_RE.finditer(output):
        kind, test_id, reason = match.group(1), match.group(2), (match.group(3) or "").strip()
        if test_id in seen:
            continue
        seen.add(test_id)
        if not reason:
            # Collection errors are summarized as a bare "ERROR path.py"; the
            # actual exception is the last "E   ..." line of that file's section.
            section = failure_section(output, test_id) or ""
            error_lines = [line[1:].strip() for line in section.splitlines() if line.startswith("E ")]
            reason = error_lines[-1] if error_lines else ""
        entry = FailingTest(test_id=test_id, reason=reason)
        if kind == "ERROR" and reason.startswith("ModuleNotFoundError"):
            run.env_errors.append(entry)
        else:
            run.failures.append(entry)
    return run


_SECTION_HEADER_RE = re.compile(r"^_{3,} (.+?) _{3,}$", re.MULTILINE)
_SECTION_END_RE = re.compile(r"^={3,} ", re.MULTILINE)


def failure_section(output: str, test_id: str) -> str | None:
    """pytest prints each failure under a `____ test_name ____` header
    (`TestClass.test_method` for methods). Pull out the one for `test_id`."""
    parts = test_id.split("::")
    wanted = ".".join(parts[1:]) if len(parts) > 1 else None
    headers = list(_SECTION_HEADER_RE.finditer(output))
    for i, header in enumerate(headers):
        title = header.group(1)
        if title not in (wanted, f"ERROR collecting {parts[0]}"):
            continue
        end = headers[i + 1].start() if i + 1 < len(headers) else len(output)
        section_end = _SECTION_END_RE.search(output, header.end(), end)
        return output[header.end() : section_end.start() if section_end else end].strip("\n")
    return None


def run_suite(sandbox: Sandbox, repo_dir: Path, full_command: str) -> SuiteRun:
    result = sandbox.run_tests(repo_dir, full_command)
    return parse_suite_output(result.exit_code, f"{result.stdout}\n{result.stderr}")


@dataclass
class PerceivedFailure:
    stack_trace: str
    source_files: dict[str, str]
    exit_code: int


def touched_files(output: str, repo_dir: Path, limit: int = _MAX_SOURCE_FILES) -> list[str]:
    """Repo files referenced in a traceback (python-style `File "x", line n`
    or pytest-style `x.py:12:`), skipping stdlib/site-packages frames."""
    seen: list[str] = []
    candidates = [m.group(1) for m in _TRACEBACK_FILE_RE.finditer(output)]
    candidates += [m.group(1) for m in _PYTEST_LOCATION_RE.finditer(output)]
    for raw in candidates:
        rel = raw.removeprefix("/work/").removeprefix("./")
        if rel in seen or rel.startswith("/"):
            continue
        if (repo_dir / rel).is_file():
            seen.append(rel)
        if len(seen) >= limit:
            break
    return seen


def _resolve_module(module: str, repo_dir: Path) -> str | None:
    parts = module.split(".")
    for root in ("", "src/"):
        for candidate in (f"{root}{'/'.join(parts)}.py", f"{root}{'/'.join(parts)}/__init__.py"):
            if (repo_dir / candidate).is_file():
                return candidate
    return None


def imported_repo_modules(test_file: str, repo_dir: Path) -> list[str]:
    """Repo modules a test file imports. An assertion failure's traceback
    usually only shows the test itself (the function under test returned,
    just with the wrong value), so this is how the planner gets to see the
    code that actually needs fixing. Parsed with ast, never executed."""
    try:
        tree = ast.parse((repo_dir / test_file).read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    found: list[str] = []
    for module in modules:
        rel = _resolve_module(module, repo_dir)
        if rel and rel != test_file and rel not in found:
            found.append(rel)
    return found


def perceive_one(sandbox: Sandbox, repo_dir: Path, scoped_test_command: str) -> PerceivedFailure:
    """`scoped_test_command` must run exactly one test, so the resulting
    traceback is about a single issue."""
    result = sandbox.run_tests(repo_dir, scoped_test_command)
    combined_output = f"{result.stdout}\n{result.stderr}".strip()
    files = touched_files(combined_output, repo_dir)
    test_file = scoped_test_command.rsplit(" ", 1)[-1].strip("'\"").split("::")[0]
    if (repo_dir / test_file).is_file():
        for rel in imported_repo_modules(test_file, repo_dir):
            if rel not in files and len(files) < _MAX_SOURCE_FILES:
                files.append(rel)
    source_files = {rel: (repo_dir / rel).read_text() for rel in files}
    return PerceivedFailure(
        stack_trace=combined_output,
        source_files=source_files,
        exit_code=result.exit_code,
    )
