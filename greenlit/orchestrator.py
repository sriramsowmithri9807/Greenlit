"""Fix engine: PERCEIVE -> PLAN -> [RESEARCH] -> ACT -> EVALUATE -> LOOP for
one issue at a time, against a working copy of a repo.

Knows nothing about GitHub (that's greenlit.agent). Every candidate diff is
applied to a throwaway copy and run inside the Sandbox; a fix is accepted
only if

- it applies cleanly and touches only paths inside the repo,
- it doesn't edit test files (fix the code under test, don't weaken the test),
- for a failing-test issue: that test now passes (classified by Nemotron Nano)
  AND the full suite has no failures that weren't there before,
- for a code-review issue: it edits the reported file, compiles, and the full
  suite has no new failures.

Only then is the diff applied to the working copy. A rejected diff, for any
reason, is fed back to the planner as a failed attempt rather than aborting
the run.

Emits the dashboard's events (dashboard/src/types/events.ts) through an
injected `emit(event_type, payload)` callback.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from greenlit.clients.sandbox import Sandbox
from greenlit.issues import Issue
from greenlit.llm_client import call_evaluator, call_planner
from greenlit.perceive import SuiteRun, parse_suite_output, perceive_one, run_suite
from greenlit.project import is_test_file
from greenlit.repo_files import IGNORED_DIRS
from greenlit.research import research

Emit = Callable[[str, dict], None]

DEFAULT_MAX_ITERATIONS = 3
_COMPILE_FAILED_EXIT = 97

# Each rung loosens how strictly hunk context must match. LLM diffs often
# have wrong hunk line counts (--recount fixes those), omit trailing
# context (--unidiff-zero stops git anchoring such hunks to end-of-file),
# or misquote a context line (-C1/-C0 relax context matching). Removed
# lines must always match exactly, and the sandbox run verifies the result.
_APPLY_LADDER: tuple[tuple[str, ...], ...] = (
    (),
    ("--unidiff-zero",),
    ("--unidiff-zero", "-C1"),
    ("--unidiff-zero", "-C0"),
)


class DiffError(Exception):
    pass


def _noop_emit(event_type: str, payload: dict) -> None:
    pass


def diff_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        if not line.startswith(("--- ", "+++ ")):
            continue
        raw = line[4:].split("\t")[0].strip()
        if raw == "/dev/null":
            continue
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        if raw and raw not in paths:
            paths.append(raw)
    return paths


def validate_diff(diff: str, repo_dir: Path) -> list[str]:
    paths = diff_paths(diff)
    if not paths:
        raise DiffError("no file headers found; expected a unified diff with '--- a/<path>' / '+++ b/<path>' lines")
    root = repo_dir.resolve()
    for rel in paths:
        pure = PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts or (pure.parts and pure.parts[0] == ".git"):
            raise DiffError(f"refusing unsafe path in diff: {rel}")
        if not (repo_dir / rel).resolve().is_relative_to(root):
            raise DiffError(f"refusing path that resolves outside the repo: {rel}")
    return paths


def apply_diff(target_dir: Path, diff: str) -> list[str]:
    """Apply `diff` to `target_dir` atomically. Returns the paths it touched."""
    paths = validate_diff(diff, target_dir)
    if not diff.endswith("\n"):
        diff += "\n"
    last_error = ""
    for extra in _APPLY_LADDER:
        proc = subprocess.run(
            ["git", "apply", "--recount", "--whitespace=nowarn", *extra],
            input=diff,
            text=True,
            cwd=target_dir,
            capture_output=True,
        )
        if proc.returncode == 0:
            return paths
        last_error = proc.stderr.strip()
    raise DiffError(f"diff did not apply: {last_error}")


def _scratch_copy(repo_dir: Path) -> Path:
    scratch = Path(tempfile.mkdtemp(prefix="greenlit-scratch-"))
    shutil.copytree(repo_dir, scratch, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*IGNORED_DIRS), symlinks=True)
    return scratch


@dataclass
class Attempt:
    diff: str
    why_it_failed: str


@dataclass
class FixResult:
    status: str  # "fixed" | "unresolved"
    iterations: int
    diff: str | None
    rationale: str | None
    changed_files: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    suite_after: SuiteRun | None = None


@dataclass
class _Verdict:
    ok: bool
    reason: str
    suite_after: SuiteRun | None = None


class FixEngine:
    def __init__(
        self,
        sandbox: Sandbox,
        working_dir: Path,
        install_command: str | None,
        test_command: str,
        *,
        emit: Emit = _noop_emit,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ):
        self.sandbox = sandbox
        self.working_dir = working_dir
        self.install_command = install_command
        self.test_command = test_command
        self.emit = emit
        self.max_iterations = max_iterations

    def _cmd(self, command: str) -> str:
        return f"{self.install_command} && {command}" if self.install_command else command

    def run_suite(self, directory: Path | None = None) -> SuiteRun:
        return run_suite(self.sandbox, directory or self.working_dir, self._cmd(self.test_command))

    def _scoped_command(self, issue: Issue) -> str:
        return self._cmd(f"{self.test_command} {shlex.quote(issue.test_id or '')}")

    # --- PERCEIVE ---------------------------------------------------------

    def _perceive(self, issue: Issue) -> dict:
        self.emit("stage_start", {"stage": "perceive"})
        if issue.kind == "test":
            failure = perceive_one(self.sandbox, self.working_dir, self._scoped_command(issue))
            context = {"stack_trace": failure.stack_trace, "source_files": failure.source_files}
            self.emit("log_line", {"text": f"PERCEIVE: reproduced {issue.test_id} in the sandbox"})
        else:
            source = (self.working_dir / issue.file).read_text() if issue.file else ""
            context = {
                "issue": {
                    "title": issue.title,
                    "location": issue.location,
                    "description": issue.description,
                    "evidence": issue.evidence,
                },
                "source_files": {issue.file: source} if issue.file else {},
            }
            self.emit("log_line", {"text": f"PERCEIVE: loaded {issue.location} for the reported bug"})
        self.emit("stage_end", {"stage": "perceive"})
        return context

    # --- PLAN (+ conditional RESEARCH) -------------------------------------

    def _plan(self, context: dict, attempts: list[Attempt]) -> dict:
        prior = [{"diff": a.diff, "why_it_failed": a.why_it_failed} for a in attempts] or None

        self.emit("stage_start", {"stage": "plan"})
        plan = call_planner({**context, "prior_attempts": prior, "research_context": None})
        self.emit("log_line", {"text": f"PLAN (Nemotron Ultra): {plan['rationale']}"})
        self.emit("stage_end", {"stage": "plan", "result": {"unfamiliar_api": plan["unfamiliar_api"]}})

        if plan["unfamiliar_api"] and plan.get("unfamiliar_api_query"):
            query = plan["unfamiliar_api_query"]
            self.emit("stage_start", {"stage": "research"})
            self.emit("log_line", {"text": f'RESEARCH (Tavily): "{query}"'})
            research_context = research(query)
            self.emit(
                "log_line",
                {
                    "text": "Found relevant docs, feeding them back into PLAN"
                    if research_context
                    else "No usable results (or TAVILY_API_KEY unset), planning without them"
                },
            )
            self.emit("stage_end", {"stage": "research"})

            self.emit("stage_start", {"stage": "plan"})
            plan = call_planner({**context, "prior_attempts": prior, "research_context": research_context})
            self.emit("log_line", {"text": f"PLAN (Nemotron Ultra, with docs): {plan['rationale']}"})
            self.emit("stage_end", {"stage": "plan", "result": {"unfamiliar_api": False}})
        return plan

    # --- ACT + EVALUATE ------------------------------------------------------

    def _reject(self, reason: str) -> _Verdict:
        self.emit("stage_end", {"stage": "act"})
        self.emit("stage_start", {"stage": "evaluate"})
        self.emit("log_line", {"text": f"EVALUATE: rejected, {reason}"})
        self.emit("stage_end", {"stage": "evaluate", "result": {"status": "REJECTED"}})
        return _Verdict(ok=False, reason=reason)

    def _regressions(self, suite_after: SuiteRun, baseline: SuiteRun) -> str | None:
        new_problems = sorted(suite_after.problem_ids - baseline.problem_ids)
        if new_problems:
            return "it made previously-passing tests fail: " + ", ".join(new_problems[:5])
        return None

    def _act_and_evaluate(self, issue: Issue, diff: str, baseline: SuiteRun, prior_error: str | None) -> _Verdict:
        self.emit("stage_start", {"stage": "act"})
        scratch = _scratch_copy(self.working_dir)
        try:
            try:
                changed = apply_diff(scratch, diff)
            except DiffError as exc:
                return self._reject(str(exc))

            touched_tests = [p for p in changed if is_test_file(PurePosixPath(p))]
            if touched_tests:
                return self._reject(
                    f"it edits test files ({', '.join(touched_tests)}); fix the code under test instead"
                )
            if issue.kind == "review" and issue.file not in changed:
                return self._reject(f"it doesn't touch {issue.file}, where the bug was reported")

            self.emit("log_line", {"text": f"ACT: patched {', '.join(changed)}, running it in the sandbox"})

            if issue.kind == "test":
                return self._evaluate_test_fix(issue, scratch, baseline, prior_error)
            return self._evaluate_review_fix(scratch, changed, baseline)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def _evaluate_test_fix(self, issue: Issue, scratch: Path, baseline: SuiteRun, prior_error: str | None) -> _Verdict:
        scoped = self.sandbox.run_tests(scratch, self._scoped_command(issue))
        self.emit("stage_end", {"stage": "act"})

        self.emit("stage_start", {"stage": "evaluate"})
        verdict = call_evaluator(
            test_stdout=scoped.stdout,
            test_stderr=scoped.stderr,
            exit_code=scoped.exit_code,
            prior_error=prior_error,
        )
        if verdict["status"] != "PASS":
            self.emit("log_line", {"text": f"EVALUATE (Nemotron Nano): {verdict['status']}, {verdict['error_summary']}"})
            self.emit("stage_end", {"stage": "evaluate", "result": {"status": verdict["status"]}})
            return _Verdict(ok=False, reason=verdict["error_summary"] or verdict["status"])

        self.emit("log_line", {"text": f"EVALUATE (Nemotron Nano): {issue.test_id} passes, checking the full suite"})
        suite_after = self.run_suite(scratch)
        regression = self._regressions(suite_after, baseline)
        if regression:
            self.emit("log_line", {"text": f"EVALUATE: rejected, {regression}"})
            self.emit("stage_end", {"stage": "evaluate", "result": {"status": "REGRESSION"}})
            return _Verdict(ok=False, reason=regression)

        self.emit("stage_end", {"stage": "evaluate", "result": {"status": "PASS"}})
        return _Verdict(ok=True, reason="", suite_after=suite_after)

    def _evaluate_review_fix(self, scratch: Path, changed: list[str], baseline: SuiteRun) -> _Verdict:
        py_files = " ".join(shlex.quote(p) for p in changed if p.endswith(".py"))
        compile_step = f"(python -m py_compile {py_files} || exit {_COMPILE_FAILED_EXIT}) && " if py_files else ""
        result = self.sandbox.run_tests(scratch, self._cmd(f"{compile_step}{self.test_command}"))
        self.emit("stage_end", {"stage": "act"})

        self.emit("stage_start", {"stage": "evaluate"})
        if result.exit_code == _COMPILE_FAILED_EXIT:
            reason = f"the patched file doesn't compile: {result.stderr.strip()[-400:]}"
            self.emit("log_line", {"text": f"EVALUATE: rejected, {reason}"})
            self.emit("stage_end", {"stage": "evaluate", "result": {"status": "REJECTED"}})
            return _Verdict(ok=False, reason=reason)

        suite_after = parse_suite_output(result.exit_code, f"{result.stdout}\n{result.stderr}")
        regression = self._regressions(suite_after, baseline)
        if regression:
            self.emit("log_line", {"text": f"EVALUATE: rejected, {regression}"})
            self.emit("stage_end", {"stage": "evaluate", "result": {"status": "REGRESSION"}})
            return _Verdict(ok=False, reason=regression)

        self.emit("log_line", {"text": "EVALUATE: compiles, and no test that passed before fails now"})
        self.emit("stage_end", {"stage": "evaluate", "result": {"status": "PASS"}})
        return _Verdict(ok=True, reason="", suite_after=suite_after)

    # --- LOOP -----------------------------------------------------------------

    def fix(self, issue: Issue, baseline: SuiteRun) -> FixResult:
        context = self._perceive(issue)
        attempts: list[Attempt] = []
        prior_error: str | None = None
        diff: str | None = None
        rationale: str | None = None

        for iteration in range(1, self.max_iterations + 1):
            self.emit("iteration", {"count": iteration})
            plan = self._plan(context, attempts)
            diff, rationale = plan["diff"], plan["rationale"]
            self.emit("diff_ready", {"diff": diff})

            verdict = self._act_and_evaluate(issue, diff, baseline, prior_error)
            if verdict.ok:
                changed = apply_diff(self.working_dir, diff)
                return FixResult(
                    status="fixed",
                    iterations=iteration,
                    diff=diff,
                    rationale=rationale,
                    changed_files=changed,
                    attempts=attempts,
                    suite_after=verdict.suite_after,
                )
            attempts.append(Attempt(diff=diff, why_it_failed=verdict.reason))
            prior_error = verdict.reason

        return FixResult(
            status="unresolved",
            iterations=self.max_iterations,
            diff=diff,
            rationale=rationale,
            attempts=attempts,
        )
