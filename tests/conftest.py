"""Shared test doubles.

`LocalSandbox` runs pytest for real, on the host, in the directory it's
given. That's fine here because the only code it ever runs is Greenlit's
own demo fixtures; in production every run goes to a Nebius sandbox. It
drops the dependency-install part of a command, so tests never pip install.

`FakeGitHubAPI` records what the agent would have done on GitHub.

`FakePlanner` hands back fix diffs keyed by a substring of whatever the
planner is shown, so tests can script "the model proposes this for that".
"""
from __future__ import annotations

import difflib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from greenlit.clients.sandbox import SandboxResult

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "demo"

_INSTALL_PREFIXES = ("export PIP", "pip install", "(pip install")


class LocalSandbox:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run_tests(self, repo_dir: Path, command: str) -> SandboxResult:
        self.commands.append(command)
        kept = [part for part in command.split(" && ") if not part.startswith(_INSTALL_PREFIXES)]
        shell = " && ".join(kept).replace("python -m", f"{sys.executable} -m")
        proc = subprocess.run(["bash", "-c", shell], cwd=repo_dir, capture_output=True, text=True, timeout=120)
        return SandboxResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)

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

    def __call__(self, context: dict) -> dict:
        self.calls.append(context)
        rendered = f"{context.get('stack_trace', '')}\n{context.get('issue', '')}"
        for key, plans in self.scripts.items():
            if key in rendered and plans:
                return plans.pop(0) if len(plans) > 1 else plans[0]
        raise AssertionError(f"FakePlanner has no script for: {rendered[:300]}")


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
