"""Repo-wide agent: find every failing test, fix them one at a time.

Two nested loops:

- Outer (repo-level): run the whole suite, get the current worklist of
  failing tests from `perceive.discover_failures`, pick one, hand it to
  the inner loop. Re-runs the whole suite after each accepted fix, so a
  fix that incidentally repairs (or breaks) another test is picked up on
  the next pass rather than working off a stale worklist.
- Inner (issue-level): the original PERCEIVE -> PLAN -> [RESEARCH] -> ACT
  -> EVALUATE -> retry cycle, scoped to one test id, with attempt-history-
  aware re-planning and a per-issue max-iteration cap.

Emits the dashboard's event types (dashboard/src/types/events.ts) via an
injected `emit(event_type, payload)` callback, so this module knows
nothing about HTTP/SSE. Two event types are new since the single-issue
version: `issue_start` / `issue_end`, carrying which test is being worked
and how many are left — see the dashboard event contract note below.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from greenlit.clients.sandbox import Sandbox
from greenlit.config import GreenlitConfig
from greenlit.llm_client import call_evaluator, call_planner
from greenlit.perceive import FailingTest, discover_failures, perceive_one
from greenlit.research import research

Emit = Callable[[str, dict], None]

DEFAULT_MAX_ITERATIONS_PER_ISSUE = 5
DEFAULT_MAX_ISSUES = 10


@dataclass
class Attempt:
    diff: str
    why_it_failed: str


@dataclass
class IssueResult:
    status: str  # "fixed" | "unresolved"
    iterations: int
    final_diff: str | None
    attempts: list[Attempt] = field(default_factory=list)


@dataclass
class RepoRunResult:
    status: str  # "fixed" | "unresolved"
    fixed_issues: list[str]
    unresolved_issues: list[str]
    working_dir: Path


def _noop_emit(event_type: str, payload: dict) -> None:
    pass


def _full_command(install_command: str | None, test_command: str) -> str:
    return f"{install_command} && {test_command}" if install_command else test_command


def _apply_diff(target_dir: Path, diff: str) -> None:
    proc = subprocess.run(
        ["patch", "-p1", "--fuzz=3"],
        input=diff,
        text=True,
        cwd=target_dir,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to apply proposed diff (patch exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}\n\nDiff:\n{diff}"
        )


def _scratch_copy_with_diff(repo_dir: Path, diff: str) -> Path:
    """Copy repo_dir to a throwaway directory and apply `diff` there. The
    caller's real working tree is never touched."""
    scratch = Path(tempfile.mkdtemp(prefix="greenlit-"))
    shutil.copytree(repo_dir, scratch, dirs_exist_ok=True)
    try:
        _apply_diff(scratch, diff)
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    return scratch


def _attempts_payload(attempts: list[Attempt]) -> list[dict] | None:
    return [{"diff": a.diff, "why_it_failed": a.why_it_failed} for a in attempts] or None


def _fix_one_issue(
    sandbox: Sandbox,
    working_dir: Path,
    issue: FailingTest,
    install_command: str | None,
    test_command: str,
    max_iterations: int,
    emit: Emit,
) -> IssueResult:
    scoped_command = _full_command(install_command, f"{test_command} {issue.test_id}")

    emit("stage_start", {"stage": "perceive"})
    failure = perceive_one(sandbox, working_dir, scoped_command)
    emit("log_line", {"text": f"Captured failure for {issue.test_id}: {issue.reason}"})
    emit("stage_end", {"stage": "perceive"})

    attempts: list[Attempt] = []
    prior_error: str | None = None
    diff: str | None = None

    for iteration in range(1, max_iterations + 1):
        emit("iteration", {"count": iteration})

        emit("stage_start", {"stage": "plan"})
        plan = call_planner(
            {
                "stack_trace": failure.stack_trace,
                "source_files": failure.source_files,
                "prior_attempts": _attempts_payload(attempts),
                "research_context": None,
            }
        )
        emit("log_line", {"text": plan["rationale"]})
        emit(
            "stage_end",
            {"stage": "plan", "result": {"unfamiliar_api": plan["unfamiliar_api"]}},
        )

        if plan["unfamiliar_api"] and plan.get("unfamiliar_api_query"):
            query = plan["unfamiliar_api_query"]
            emit("stage_start", {"stage": "research"})
            emit("log_line", {"text": f'RESEARCH: querying "{query}"'})
            research_context = research(query)
            emit(
                "log_line",
                {
                    "text": "Found relevant docs, feeding back into PLAN"
                    if research_context
                    else "No usable results (or TAVILY_API_KEY unset) — proceeding without them"
                },
            )
            emit("stage_end", {"stage": "research"})

            # Re-run PLAN once, now informed, before acting.
            emit("stage_start", {"stage": "plan"})
            plan = call_planner(
                {
                    "stack_trace": failure.stack_trace,
                    "source_files": failure.source_files,
                    "prior_attempts": _attempts_payload(attempts),
                    "research_context": research_context,
                }
            )
            emit("log_line", {"text": plan["rationale"]})
            emit("stage_end", {"stage": "plan", "result": {"unfamiliar_api": False}})

        diff = plan["diff"]
        emit("diff_ready", {"diff": diff})

        emit("stage_start", {"stage": "act"})
        patched_dir = _scratch_copy_with_diff(working_dir, diff)
        try:
            emit("log_line", {"text": "ACT: staging patched copy into Sandbox"})
            sandbox_result = sandbox.run_tests(patched_dir, scoped_command)
        finally:
            shutil.rmtree(patched_dir, ignore_errors=True)
        emit("stage_end", {"stage": "act"})

        emit("stage_start", {"stage": "evaluate"})
        verdict = call_evaluator(
            test_stdout=sandbox_result.stdout,
            test_stderr=sandbox_result.stderr,
            exit_code=sandbox_result.exit_code,
            prior_error=prior_error,
        )
        emit("log_line", {"text": verdict["error_summary"] or "PASS"})
        emit("stage_end", {"stage": "evaluate", "result": {"status": verdict["status"]}})

        if verdict["status"] == "PASS":
            return IssueResult(status="fixed", iterations=iteration, final_diff=diff, attempts=attempts)

        attempts.append(Attempt(diff=diff, why_it_failed=verdict["error_summary"]))
        prior_error = verdict["error_summary"]

    return IssueResult(status="unresolved", iterations=max_iterations, final_diff=diff, attempts=attempts)


def run(
    repo_dir: Path,
    *,
    install_command: str | None = None,
    test_command: str = "pytest -q",
    max_issues: int = DEFAULT_MAX_ISSUES,
    max_iterations_per_issue: int = DEFAULT_MAX_ITERATIONS_PER_ISSUE,
    emit: Emit = _noop_emit,
) -> RepoRunResult:
    config = GreenlitConfig.from_env()
    sandbox = Sandbox(config)

    working_dir = Path(tempfile.mkdtemp(prefix="greenlit-working-"))
    shutil.copytree(repo_dir, working_dir, dirs_exist_ok=True)

    full_suite_command = _full_command(install_command, test_command)
    fixed_issues: list[str] = []
    unresolved_issues: list[str] = []
    gave_up: set[str] = set()

    try:
        emit("status", {"value": "failing"})

        for _pass_num in range(1, max_issues + 1):
            emit("stage_start", {"stage": "perceive"})
            failures, suite_result = discover_failures(sandbox, working_dir, full_suite_command)
            emit("stage_end", {"stage": "perceive"})

            remaining = [f for f in failures if f.test_id not in gave_up]

            if not failures:
                emit("log_line", {"text": "Full suite passes."})
                break
            if not remaining:
                emit(
                    "log_line",
                    {"text": f"{len(failures)} test(s) still failing, all previously given up on"},
                )
                break

            emit(
                "log_line",
                {
                    "text": f"{len(remaining)}/{len(failures)} failing test(s) to work: "
                    + ", ".join(f.test_id for f in remaining)
                },
            )
            emit("status", {"value": "testing"})

            issue = remaining[0]
            emit("issue_start", {"issue": issue.test_id, "remaining": len(remaining)})

            result = _fix_one_issue(
                sandbox,
                working_dir,
                issue,
                install_command,
                test_command,
                max_iterations_per_issue,
                emit,
            )

            if result.status == "fixed" and result.final_diff:
                _apply_diff(working_dir, result.final_diff)
                fixed_issues.append(issue.test_id)
                emit("issue_end", {"issue": issue.test_id, "status": "fixed"})
            else:
                gave_up.add(issue.test_id)
                emit("issue_end", {"issue": issue.test_id, "status": "unresolved"})
                emit(
                    "log_line",
                    {
                        "text": f"Giving up on {issue.test_id} after "
                        f"{max_iterations_per_issue} attempt(s); moving on"
                    },
                )
        else:
            emit("log_line", {"text": f"Hit the {max_issues}-issue pass cap"})

        unresolved_issues = sorted(gave_up)
        final_status = "fixed" if not unresolved_issues else "unresolved"
        emit("status", {"value": final_status})

        return RepoRunResult(
            status=final_status,
            fixed_issues=fixed_issues,
            unresolved_issues=unresolved_issues,
            working_dir=working_dir,
        )
    finally:
        sandbox.close()
