"""Shared test doubles.

`LocalSandbox` runs pytest for real, on the host, in the directory it's
given. That's fine here because the only code it ever runs is Greenlit's
own demo fixtures; in production every run goes to a Nebius sandbox. It
drops the dependency-install part of a command, so tests never pip install,
and it emulates coreutils `timeout` (not available on every host, e.g.
macOS): a timed-out command is killed and exits 124, as in the sandbox.

`FakeGitHubAPI` records what the agent would have done on GitHub.

`FakePlanner` hands back fix diffs keyed by a substring of whatever the
planner is shown, so tests can script "the model proposes this for that".
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from greenlit.clients.sandbox import SandboxResult

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "demo"

_INSTALL_PREFIXES = ("export PIP", "pip install", "(pip install")
_TIMEOUT_PREFIX = re.compile(r"timeout -k \d+ (\d+) ")
TIMED_OUT = 124  # what coreutils `timeout` exits with


class LocalSandbox:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run_tests(self, repo_dir: Path, command: str) -> SandboxResult:
        self.commands.append(command)
        kept = [part for part in command.split(" && ") if not part.startswith(_INSTALL_PREFIXES)]
        shell = " && ".join(kept).replace("python -m", f"{sys.executable} -m")
        limits = [int(n) for n in _TIMEOUT_PREFIX.findall(shell)]
        shell = _TIMEOUT_PREFIX.sub("", shell)
        # Its own process group, so a timeout kills pytest too, not just bash.
        proc = subprocess.Popen(
            ["bash", "-c", shell], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
        )
        try:
            stdout, stderr = proc.communicate(timeout=min(limits) if limits else 120)
            return SandboxResult(stdout=stdout, stderr=stderr, exit_code=proc.returncode)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            return SandboxResult(stdout=stdout, stderr=stderr, exit_code=TIMED_OUT)

    def close(self) -> None:
        pass


def make_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def plan(diff: str, rationale: str = "fix", *, unfamiliar: bool = False, query: str | None = None) -> dict:
    return {"diff": diff, "rationale": rationale, "unfamiliar_api": unfamiliar, "unfamiliar_api_query": query}


class FakePlanner:
    """`scripts` maps a substring of what identifies the issue (the failing
    test's traceback, or the reported issue's fields) to the plans to return,
    in order; the last plan repeats. Source files are deliberately not
    matched against: a test file mentions every test in it."""

    def __init__(self, scripts: dict[str, list[dict]]):
        self.scripts = {key: list(plans) for key, plans in scripts.items()}
        self.calls: list[dict] = []
        self._lock = threading.Lock()  # parallel fixes call it from several threads

    def __call__(self, context: dict) -> dict:
        with self._lock:
            self.calls.append(context)
            rendered = f"{context.get('stack_trace', '')}\n{context.get('issue', '')}"
            for key, plans in self.scripts.items():
                if key in rendered and plans:
                    return plans.pop(0) if len(plans) > 1 else plans[0]
        raise AssertionError(f"FakePlanner has no script for: {rendered[:300]}")


BROKEN_TEST = "import greenlit_no_such_module\n\n\ndef test_x():\n    pass\n"


class FakeTestWriter:
    """The REPRODUCE step's test writer. `scripts` maps a substring of the
    issue title to the test files to return, in order (the last repeats).
    Issues with no script get a test that can't even import, which makes
    the engine fall back to "unproven" (compile + no-regression) checks."""

    def __init__(self, scripts: dict[str, list[str]] | None = None):
        self.scripts = {key: list(codes) for key, codes in (scripts or {}).items()}
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def __call__(self, context: dict) -> dict:
        with self._lock:
            self.calls.append(context)
            title = context.get("issue", {}).get("title", "")
            for key, codes in self.scripts.items():
                if key in title and codes:
                    code = codes.pop(0) if len(codes) > 1 else codes[0]
                    return {"test_code": code, "explanation": "scripted"}
        return {"test_code": BROKEN_TEST, "explanation": "unscripted"}


def fake_repro_judge(issue: dict, test_code: str, test_output: str) -> dict:
    """Mirrors the rule in the real judge prompt."""
    for marker in ("ImportError", "ModuleNotFoundError", "NameError", "SyntaxError"):
        if marker in test_output:
            return {"verdict": "TEST_IS_BROKEN", "reason": marker}
    return {"verdict": "REPRODUCES_BUG", "reason": "fails the way the issue describes"}


def fake_evaluator(test_stdout: str, test_stderr: str, exit_code: int, prior_error: str | None) -> dict:
    """Mirrors the rule in the real EVALUATE prompt."""
    if exit_code == 0:
        return {"status": "PASS", "error_summary": ""}
    return {"status": "FAIL_SAME_ERROR" if prior_error else "FAIL_NEW_ERROR", "error_summary": "test still failing"}


class FakeGitHubAPI:
    def __init__(self, token: str | None = None, *, push: bool = True, default_branch: str = "main"):
        self.token = token
        self.push = push
        self.default_branch = default_branch
        self.issues: list[dict] = []
        self.comments: list[tuple[int, str]] = []
        self.pulls: list[dict] = []
        self.labels: list[str] = []

    def get_repo(self, ref) -> dict:
        return {
            "default_branch": self.default_branch,
            "html_url": ref.html_url,
            "permissions": {"push": self.push},
        }

    def get_user(self) -> dict:
        return {"login": "octo", "id": 42, "name": "Octo Cat"}

    def ensure_label(self, ref, name, color, description) -> None:
        self.labels.append(name)

    def create_issue(self, ref, title, body, labels) -> dict:
        number = len(self.issues) + 1
        self.issues.append({"number": number, "title": title, "body": body, "labels": labels})
        return {"number": number, "html_url": f"{ref.html_url}/issues/{number}"}

    def comment_on_issue(self, ref, number, body) -> dict:
        self.comments.append((number, body))
        return {}

    def create_pull(self, ref, *, title, head, base, body) -> dict:
        number = 100 + len(self.pulls)
        self.pulls.append({"number": number, "title": title, "head": head, "base": base, "body": body})
        return {"number": number, "html_url": f"{ref.html_url}/pull/{number}"}

    def close(self) -> None:
        pass


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def copy_fixture(tmp_path):
    def _copy(name: str) -> Path:
        dest = tmp_path / name
        shutil.copytree(FIXTURES / name, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        return dest

    return _copy


@pytest.fixture
def bare_remote(tmp_path):
    """A local bare git repo standing in for GitHub, seeded from a fixture."""

    def _make(name: str) -> Path:
        seed = tmp_path / f"{name}-seed"
        shutil.copytree(FIXTURES / name, seed, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        git("init", "-q", "-b", "main", cwd=seed)
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "initial", cwd=seed)
        remote = tmp_path / f"{name}.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(remote)], check=True)
        return remote

    return _make
