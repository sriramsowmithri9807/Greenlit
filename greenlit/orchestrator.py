"""PERCEIVE -> PLAN -> [RESEARCH] -> ACT -> EVALUATE -> LOOP.

Ties together greenlit.perceive, greenlit.llm_client (Nemotron PLAN/
EVALUATE), greenlit.research (conditional Tavily), and
greenlit.clients.sandbox (Token Factory Sandboxes) into the retry loop
described in the project's build-order.

Emits the six event types the dashboard expects (dashboard/src/types/
events.ts) via an injected `emit(event_type, payload)` callback, so this
module knows nothing about HTTP/SSE — a thin server layer can wire `emit`
to a real /events stream later without touching this code.
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
from greenlit.perceive import perceive
from greenlit.research import research

Emit = Callable[[str, dict], None]

DEFAULT_MAX_ITERATIONS = 5


@dataclass
class Attempt:
    diff: str
    why_it_failed: str


@dataclass
class RunResult:
    status: str  # "fixed" | "unresolved"
    iterations: int
    final_diff: str | None
    attempts: list[Attempt] = field(default_factory=list)


def _noop_emit(event_type: str, payload: dict) -> None:
    pass


def _apply_diff_to_scratch_copy(repo_dir: Path, diff: str) -> Path:
    """Copy repo_dir to a throwaway directory and apply `diff` there with
    the `patch` utility. The caller's real working tree is never touched."""
    scratch = Path(tempfile.mkdtemp(prefix="greenlit-"))
    shutil.copytree(repo_dir, scratch, dirs_exist_ok=True)
    proc = subprocess.run(
        ["patch", "-p1", "--fuzz=3"],
        input=diff,
        text=True,
        cwd=scratch,
        capture_output=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(scratch, ignore_errors=True)
        raise RuntimeError(
            f"Failed to apply proposed diff (patch exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}\n\nDiff:\n{diff}"
        )
    return scratch


def _attempts_payload(attempts: list[Attempt]) -> list[dict] | None:
    return [{"diff": a.diff, "why_it_failed": a.why_it_failed} for a in attempts] or None


def run(
    repo_dir: Path,
    test_command: str,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    emit: Emit = _noop_emit,
) -> RunResult:
    config = GreenlitConfig.from_env()
    sandbox = Sandbox(config)

    try:
        emit("status", {"value": "failing"})
        emit("iteration", {"count": 1})

        emit("stage_start", {"stage": "perceive"})
        failure = perceive(sandbox, repo_dir, test_command)
        emit("log_line", {"text": f"Captured failing test: {test_command}"})
        emit("stage_end", {"stage": "perceive"})
        emit("status", {"value": "testing"})

        attempts: list[Attempt] = []
        prior_error: str | None = None
        diff: str | None = None

        for iteration in range(1, max_iterations + 1):
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
            patched_dir = _apply_diff_to_scratch_copy(repo_dir, diff)
            try:
                emit("log_line", {"text": "ACT: staging patched copy into Sandbox"})
                sandbox_result = sandbox.run_tests(patched_dir, test_command)
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
                emit("status", {"value": "fixed"})
                return RunResult(
                    status="fixed", iterations=iteration, final_diff=diff, attempts=attempts
                )

            attempts.append(Attempt(diff=diff, why_it_failed=verdict["error_summary"]))
            prior_error = verdict["error_summary"]

            if iteration < max_iterations:
                emit("iteration", {"count": iteration + 1})

        emit(
            "log_line",
            {"text": f"Max iterations ({max_iterations}) reached without a passing run"},
        )
        emit("status", {"value": "unresolved"})
        return RunResult(
            status="unresolved", iterations=max_iterations, final_diff=diff, attempts=attempts
        )
    finally:
        sandbox.close()
