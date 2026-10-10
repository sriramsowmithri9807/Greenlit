"""Fix engine: PERCEIVE -> PLAN -> [RESEARCH] -> ACT -> EVALUATE -> LOOP for
one issue at a time, against a working copy of a repo.

Knows nothing about GitHub (that's greenlit.agent).

A bug found by code review has no failing test behind it, so before fixing
it the engine tries to PROVE it (REPRODUCE): Nemotron Ultra writes a pytest
test asserting the correct behaviour, it must fail on the current code in
the sandbox, and Nemotron Nano checks that it fails because of the bug (not
an ImportError in the test). A proven bug is then fixed exactly like a
failing test, and the new test ships with the fix. A finding whose tests
keep passing on the current code is dismissed as a likely false positive.

Every candidate diff is applied to a throwaway copy and run inside the
Sandbox; a fix is accepted only if

- it applies cleanly and touches only paths inside the repo,
- every test run it's judged on actually finished: a run that times out,
  crashes or ends the process before pytest reports is a rejection, never
  a silent "no failures",
- it doesn't edit test files (fix the code under test, don't weaken the test),
- for a failing-test issue: that test now passes (classified by Nemotron Nano)
  AND the full suite has no failures that weren't there before,
- for a proven code-review issue: it edits the reported file, the
  reproduction test now passes, and the full suite has no new failures,
- for a code-review issue that couldn't be proven either way: it edits the
  reported file, compiles, and the full suite has no new failures.

Only then is the diff applied to the working copy. A rejected diff, for any
reason, is fed back to the planner as a failed attempt rather than aborting
the run.

Emits the dashboard's events (dashboard/src/types/events.ts) through an
injected `emit(event_type, payload)` callback.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from greenlit.clients.sandbox import Sandbox
from greenlit.issues import Issue
from greenlit.llm_client import call_evaluator, call_planner, call_repro_judge, call_test_writer
from greenlit.perceive import SuiteRun, failure_section, parse_suite_output, perceive_one, run_suite
from greenlit.project import is_test_file
from greenlit.repo_files import IGNORED_DIRS, iter_repo_files
from greenlit.research import research

Emit = Callable[[str, dict], None]

DEFAULT_MAX_ITERATIONS = 3
DEFAULT_TEST_TIMEOUT = 600  # seconds per test run, override with GREENLIT_TEST_TIMEOUT
_KILL_GRACE_SECONDS = 10
REPRO_ATTEMPTS = 2
_MAX_EXAMPLE_TEST_CHARS = 3000
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


def test_timeout_from_env() -> int:
    try:
        return max(1, int(os.environ.get("GREENLIT_TEST_TIMEOUT", DEFAULT_TEST_TIMEOUT)))
    except ValueError:
        return DEFAULT_TEST_TIMEOUT


def _scratch_copy(repo_dir: Path) -> Path:
    scratch = Path(tempfile.mkdtemp(prefix="greenlit-scratch-"))
    shutil.copytree(repo_dir, scratch, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*IGNORED_DIRS), symlinks=True)
    return scratch


@dataclass
class Attempt:
    diff: str
    why_it_failed: str


@dataclass
class Proof:
    """Whether a code-review finding was shown to be a real bug."""

    status: str  # "reproduced" | "not_reproduced" | "unproven"
    test_path: str | None = None
    test_code: str | None = None
    output: str | None = None
    reason: str = ""

    def to_event(self, key: str) -> dict:
        return {
            "key": key,
            "status": self.status,
            "test_path": self.test_path,
            "test_code": self.test_code,
            "output": (self.output or "")[-2500:],
            "reason": self.reason,
        }


@dataclass
class FixResult:
    status: str  # "fixed" | "unresolved" | "dismissed" (review finding that didn't reproduce)
    iterations: int
    diff: str | None
    rationale: str | None
    changed_files: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    suite_after: SuiteRun | None = None
    proof: Proof | None = None
    # Files the fix adds besides its diff: the reproduction test.
    added_files: dict[str, str] = field(default_factory=dict)

    def apply_to(self, repo_dir: Path) -> list[str]:
        """Apply this verified fix to `repo_dir`; returns the paths touched."""
        changed = apply_diff(repo_dir, self.diff) if self.diff else []
        for rel, content in self.added_files.items():
            (repo_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo_dir / rel).write_text(content)
            if rel not in changed:
                changed.append(rel)
        return changed


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
        suite_targets: list[str] | None = None,
        test_timeout: int | None = None,
    ):
        """`suite_targets` narrows "the full suite" to these test paths, for
        repos whose whole suite is too slow to run on every attempt.

        `test_timeout` caps each pytest run inside the sandbox, in seconds
        (default GREENLIT_TEST_TIMEOUT, else 600), so a fix that loops
        forever is stopped and rejected instead of stalling the run."""
        self.suite_targets = suite_targets
        self.test_timeout = test_timeout or test_timeout_from_env()
        self.sandbox = sandbox
        self.working_dir = working_dir
        self.install_command = install_command
        self.test_command = test_command
        self.emit = emit
        self.max_iterations = max_iterations

    def _cmd(self, command: str) -> str:
        return f"{self.install_command} && {command}" if self.install_command else command

    def _timed(self, command: str) -> str:
        """Run `command` under coreutils `timeout`: exit 124 when it's
        stopped, 137 if it had to be killed after the grace period."""
        return f"timeout -k {_KILL_GRACE_SECONDS} {self.test_timeout} {command}"

    def _suite_command(self) -> str:
        targets = "".join(f" {shlex.quote(t)}" for t in self.suite_targets or [])
        return self._timed(f"{self.test_command}{targets}")

    def run_suite(self, directory: Path | None = None) -> SuiteRun:
        return run_suite(self.sandbox, directory or self.working_dir, self._cmd(self._suite_command()))

    def _scoped_command(self, target: str) -> str:
        return self._cmd(self._timed(f"{self.test_command} {shlex.quote(target)}"))

    def unfinished(self, suite: SuiteRun) -> str | None:
        """None if the run completed; otherwise why it didn't, in words."""
        return None if suite.completed else suite.incomplete_reason(self.test_timeout)

    # --- PERCEIVE ---------------------------------------------------------

    def _perceive(self, issue: Issue) -> dict:
        self.emit("stage_start", {"stage": "perceive"})
        if issue.kind == "test":
            failure = perceive_one(self.sandbox, self.working_dir, self._scoped_command(issue.test_id or ""))
            context = {"stack_trace": failure.stack_trace, "source_files": failure.source_files}
            self.emit("log_line", {"text": f"PERCEIVE: reproduced {issue.test_id} in the sandbox"})
        elif issue.kind == "report":
            files = issue.files or []
            context = {
                "issue": {"title": issue.title, "description": issue.description},
                "source_files": {f: (self.working_dir / f).read_text(errors="replace")[:40_000] for f in files},
            }
            self.emit("log_line", {"text": f"PERCEIVE: bug report points at {', '.join(files) or 'no specific file'}"})
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

    # --- REPRODUCE ---------------------------------------------------------

    def _repro_location(self, issue: Issue) -> tuple[str, dict | None]:
        """Where the reproduction test goes (next to the repo's existing
        tests, so it imports the same way) and an existing test to imitate."""
        tests = sorted(
            (p.relative_to(self.working_dir) for p in iter_repo_files(self.working_dir) if p.suffix == ".py"),
            key=lambda rel: (len(rel.parts), str(rel)),
        )
        tests = [rel for rel in tests if rel.name.startswith("test_") and is_test_file(PurePosixPath(rel.as_posix()))]
        folder = PurePosixPath(tests[0].parent.as_posix()) if tests else PurePosixPath(".")
        stem = "".join(c if c.isalnum() else "_" for c in issue.key).strip("_")
        path = (folder / f"test_greenlit_{stem}.py").as_posix()
        example = None
        if tests:
            text = (self.working_dir / tests[0]).read_text(errors="replace")
            example = {"path": tests[0].as_posix(), "content": text[:_MAX_EXAMPLE_TEST_CHARS]}
        return path, example

    def _reproduce(self, issue: Issue, context: dict) -> Proof:
        self.emit("stage_start", {"stage": "reproduce"})
        path, example = self._repro_location(issue)
        issue_info = context.get("issue", {})
        feedback: str | None = None
        passed = 0

        for _ in range(REPRO_ATTEMPTS):
            written = call_test_writer({**context, "test_path": path, "example_test": example, "prior_attempt": feedback})
            code = written["test_code"]
            try:
                compile(code, path, "exec")
            except SyntaxError as exc:
                feedback = f"the test file has a syntax error: {exc}"
                continue

            scratch = _scratch_copy(self.working_dir)
            try:
                (scratch / path).parent.mkdir(parents=True, exist_ok=True)
                (scratch / path).write_text(code)
                result = self.sandbox.run_tests(scratch, self._scoped_command(path))
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
            output = f"{result.stdout}\n{result.stderr}"
            suite = parse_suite_output(result.exit_code, output)

            # Checked before "did it pass": a run that never finished proves
            # nothing either way, and mustn't get a real bug dismissed.
            unfinished = self.unfinished(suite)
            if unfinished:
                feedback = f"the test run didn't finish: {unfinished}"
                self.emit("log_line", {"text": f"REPRODUCE: test run didn't finish, {unfinished.splitlines()[0]}"})
                continue

            if result.exit_code == 0:
                passed += 1
                feedback = (
                    "the test PASSED on the current code, so it doesn't demonstrate the bug. "
                    "Assert the behaviour the issue says is wrong today."
                )
                self.emit("log_line", {"text": f"REPRODUCE: test passed on the current code, bug not shown ({written['explanation']})"})
                continue

            # A bare "ERROR <file>" is a collection error: the test itself is broken.
            collected = [f for f in suite.failures if f.test_id.startswith(f"{path}::")]
            if not collected or any(f.test_id == path for f in suite.failures):
                tail = "\n".join(output.strip().splitlines()[-12:])
                feedback = f"the test didn't run cleanly (collection or import error):\n{tail}"
                continue

            judged = call_repro_judge(issue_info, code, output)
            if judged["verdict"] == "REPRODUCES_BUG":
                excerpt = failure_section(output, collected[0].test_id) or output
                self.emit("log_line", {"text": f"REPRODUCE (Nemotron Nano): proven, {path} fails on the current code: {judged['reason']}"})
                self.emit("stage_end", {"stage": "reproduce", "result": {"status": "REPRODUCED"}})
                return Proof("reproduced", path, code, excerpt, judged["reason"])
            feedback = f"the test failed for the wrong reason: {judged['reason']}"
            self.emit("log_line", {"text": f"REPRODUCE (Nemotron Nano): test is broken, not the code: {judged['reason']}"})

        if passed == REPRO_ATTEMPTS:
            self.emit("stage_end", {"stage": "reproduce", "result": {"status": "NOT_REPRODUCED"}})
            return Proof("not_reproduced", path, None, None, f"{REPRO_ATTEMPTS} reproduction tests all passed on the current code")
        self.emit("log_line", {"text": "REPRODUCE: couldn't write a working test; falling back to compile + no-regression checks"})
        self.emit("stage_end", {"stage": "reproduce", "result": {"status": "UNPROVEN"}})
        return Proof("unproven", path, None, None, feedback or "")

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
        # An unfinished run reports no failures at all; that's not "no
        # regressions", it's no information.
        unfinished = self.unfinished(suite_after)
        if unfinished:
            return f"the full test suite didn't finish: {unfinished}"
        new_problems = sorted(suite_after.problem_ids - baseline.problem_ids)
        if new_problems:
            return "it made previously-passing tests fail: " + ", ".join(new_problems[:5])
        return None

    def _reject_after_suite(self, reason: str, suite_after: SuiteRun) -> _Verdict:
        status = "REGRESSION" if suite_after.completed else "INCOMPLETE"
        self.emit("log_line", {"text": f"EVALUATE: rejected, {reason.splitlines()[0]}"})
        self.emit("stage_end", {"stage": "evaluate", "result": {"status": status}})
        return _Verdict(ok=False, reason=reason)

    def _act_and_evaluate(
        self, issue: Issue, diff: str, baseline: SuiteRun, prior_error: str | None, proof: Proof | None
    ) -> _Verdict:
        self.emit("stage_start", {"stage": "act"})
        scratch = _scratch_copy(self.working_dir)
        try:
            try:
                changed = apply_diff(scratch, diff)
            except DiffError as exc:
                return self._reject(str(exc))
            proven = proof is not None and proof.status == "reproduced"
            if proven:
                (scratch / proof.test_path).parent.mkdir(parents=True, exist_ok=True)
                (scratch / proof.test_path).write_text(proof.test_code or "")

            touched_tests = [p for p in changed if is_test_file(PurePosixPath(p))]
            if touched_tests:
                return self._reject(
                    f"it edits test files ({', '.join(touched_tests)}); fix the code under test instead"
                )
            if issue.kind == "review" and issue.file not in changed:
                return self._reject(f"it doesn't touch {issue.file}, where the bug was reported")

            self.emit("log_line", {"text": f"ACT: patched {', '.join(changed)}, running it in the sandbox"})

            if issue.kind == "test":
                return self._evaluate_test_fix(issue.test_id or "", scratch, baseline, prior_error)
            if proven:
                return self._evaluate_test_fix(proof.test_path or "", scratch, baseline, prior_error)
            return self._evaluate_review_fix(scratch, changed, baseline)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def _evaluate_test_fix(self, target: str, scratch: Path, baseline: SuiteRun, prior_error: str | None) -> _Verdict:
        scoped = self.sandbox.run_tests(scratch, self._scoped_command(target))
        self.emit("stage_end", {"stage": "act"})

        self.emit("stage_start", {"stage": "evaluate"})
        # Exit code 0 alone isn't a pass: a fix that ends the process before
        # the assertion runs exits 0 too. Rejected here, before spending a
        # Nano call on it.
        unfinished = self.unfinished(parse_suite_output(scoped.exit_code, f"{scoped.stdout}\n{scoped.stderr}"))
        if unfinished:
            reason = f"the run of {target} didn't finish: {unfinished}"
            self.emit("log_line", {"text": f"EVALUATE: rejected, {reason.splitlines()[0]}"})
            self.emit("stage_end", {"stage": "evaluate", "result": {"status": "INCOMPLETE"}})
            return _Verdict(ok=False, reason=reason)

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

        self.emit("log_line", {"text": f"EVALUATE (Nemotron Nano): {target} passes, checking the full suite"})
        suite_after = self.run_suite(scratch)
        regression = self._regressions(suite_after, baseline)
        if regression:
            return self._reject_after_suite(regression, suite_after)

        self.emit("stage_end", {"stage": "evaluate", "result": {"status": "PASS"}})
        return _Verdict(ok=True, reason="", suite_after=suite_after)

    def _evaluate_review_fix(self, scratch: Path, changed: list[str], baseline: SuiteRun) -> _Verdict:
        py_files = " ".join(shlex.quote(p) for p in changed if p.endswith(".py"))
        compile_step = f"(python -m py_compile {py_files} || exit {_COMPILE_FAILED_EXIT}) && " if py_files else ""
        result = self.sandbox.run_tests(scratch, self._cmd(f"{compile_step}{self._suite_command()}"))
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
            return self._reject_after_suite(regression, suite_after)

        self.emit("log_line", {"text": "EVALUATE: compiles, and no test that passed before fails now"})
        self.emit("stage_end", {"stage": "evaluate", "result": {"status": "PASS"}})
        return _Verdict(ok=True, reason="", suite_after=suite_after)

    # --- LOOP -----------------------------------------------------------------

    def fix(self, issue: Issue, baseline: SuiteRun) -> FixResult:
        context = self._perceive(issue)
        proof: Proof | None = None
        if issue.kind in ("review", "report"):
            proof = self._reproduce(issue, context)
            self.emit("proof", proof.to_event(issue.key))
            if proof.status == "not_reproduced":
                self.emit("log_line", {"text": f"Dismissed {issue.ref}: Greenlit couldn't prove it's a real bug, so it won't be raised"})
                return FixResult(status="dismissed", iterations=0, diff=None, rationale=None, proof=proof)
            if proof.status == "reproduced":
                context = {
                    **context,
                    "reproduction_test": {"path": proof.test_path, "code": proof.test_code, "failure_output": proof.output},
                }
        else:
            # The failing test is the proof.
            self.emit("stage_start", {"stage": "reproduce"})
            self.emit("stage_end", {"stage": "reproduce", "result": {"status": "EXISTING_TEST"}})
        attempts: list[Attempt] = []
        prior_error: str | None = None
        diff: str | None = None
        rationale: str | None = None

        for iteration in range(1, self.max_iterations + 1):
            self.emit("iteration", {"count": iteration})
            plan = self._plan(context, attempts)
            diff, rationale = plan["diff"], plan["rationale"]
            self.emit("diff_ready", {"diff": diff})

            verdict = self._act_and_evaluate(issue, diff, baseline, prior_error, proof)
            if verdict.ok:
                result = FixResult(
                    status="fixed",
                    iterations=iteration,
                    diff=diff,
                    rationale=rationale,
                    attempts=attempts,
                    suite_after=verdict.suite_after,
                    proof=proof,
                    added_files={proof.test_path: proof.test_code}
                    if proof and proof.status == "reproduced" and proof.test_path and proof.test_code
                    else {},
                )
                result.changed_files = result.apply_to(self.working_dir)
                return result
            attempts.append(Attempt(diff=diff, why_it_failed=verdict.reason))
            prior_error = verdict.reason

        return FixResult(
            status="unresolved",
            iterations=self.max_iterations,
            diff=diff,
            rationale=rationale,
            attempts=attempts,
            proof=proof,
        )
