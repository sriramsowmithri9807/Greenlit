"""Fix several issues at once, each in its own Nebius sandbox, then merge.

RACE: every issue gets its own copy of the repo, its own sandbox and its own
FixEngine, all running at the same time against the same baseline. Their
events are tagged with the issue key ("lane" events) so the dashboard can
draw one lane per sandbox.

MERGE: the verified fixes are combined in issue order and the whole suite
is re-run once on the result. Fixes made in isolation can still conflict
(two edits to the same lines) or interact (each fine alone, broken
together), so if the combined tree isn't clean, Greenlit falls back to
merging one fix at a time, re-verifying after each, and re-fixing any issue
whose isolated fix no longer fits on top of the others.
"""
from __future__ import annotations

import contextvars
import os
import shutil
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from greenlit import usage
from greenlit.clients.sandbox import Sandbox
from greenlit.issues import Issue
from greenlit.orchestrator import DiffError, FixEngine, FixResult, _scratch_copy
from greenlit.perceive import SuiteRun

Emit = Callable[[str, dict], None]
OnApplied = Callable[[Issue, FixResult], None]

DEFAULT_MAX_SANDBOXES = 4
# Events that belong to one issue's pipeline, drawn in its lane.
_LANE_EVENTS = {"stage_start", "stage_end", "iteration", "diff_ready", "log_line", "proof"}


def max_sandboxes() -> int:
    try:
        return max(1, int(os.environ.get("GREENLIT_MAX_SANDBOXES", DEFAULT_MAX_SANDBOXES)))
    except ValueError:
        return DEFAULT_MAX_SANDBOXES


@dataclass
class Outcome:
    issue: Issue
    status: str  # "fixed" | "unresolved" | "dismissed"
    result: FixResult | None  # None when it was fixed as a side effect of another fix
    incidental: bool = False


@dataclass
class _LaneResult:
    issue: Issue
    result: FixResult
    seconds: float


def _short(issue: Issue) -> str:
    return issue.title if len(issue.title) <= 40 else issue.title[:37] + "..."


def _lane_emitter(emit: Emit, issue: Issue) -> Emit:
    def lane_emit(event_type: str, payload: dict) -> None:
        if event_type == "proof":
            emit("proof", payload)
        if event_type in _LANE_EVENTS:
            emit("lane", {"key": issue.key, "event": event_type, "data": payload})
        if event_type == "log_line":
            emit("log_line", {"text": f"[{_short(issue)}] {payload['text']}"})

    return lane_emit


def race(
    issues: list[Issue],
    engine: FixEngine,
    baseline: SuiteRun,
    *,
    sandbox_factory: Callable[[], Sandbox],
    emit: Emit,
    workers: int,
) -> list[_LaneResult]:
    workers = max(1, min(workers, len(issues)))
    emit(
        "race_start",
        {"sandboxes": workers, "lanes": [{"key": i.key, "title": i.title, "sandbox": n % workers + 1} for n, i in enumerate(issues)]},
    )
    emit("log_line", {"text": f"Racing {len(issues)} fixes across {workers} Nebius sandboxes in parallel"})

    def work(issue: Issue) -> _LaneResult:
        started = time.monotonic()
        emit("issue_start", {"key": issue.key, "remaining": len(issues)})
        copy = _scratch_copy(engine.working_dir)
        sandbox = sandbox_factory()
        try:
            lane = FixEngine(
                sandbox,
                copy,
                engine.install_command,
                engine.test_command,
                emit=_lane_emitter(emit, issue),
                max_iterations=engine.max_iterations,
                suite_targets=engine.suite_targets,
                test_timeout=engine.test_timeout,
            )
            with usage.for_issue(issue.key):
                result = lane.fix(issue, baseline)
        finally:
            sandbox.close()
            shutil.rmtree(copy, ignore_errors=True)
        seconds = time.monotonic() - started
        emit("lane_end", {"key": issue.key, "status": result.status, "seconds": round(seconds, 1), "iterations": result.iterations})
        return _LaneResult(issue, result, seconds)

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="greenlit-lane") as pool:
        # Each lane gets its own copy of the context, so usage tracking (a
        # contextvar) follows it into the worker thread.
        futures = [pool.submit(contextvars.copy_context().run, work, issue) for issue in issues]
        lanes = [f.result() for f in futures]
    wall = time.monotonic() - started
    sequential = sum(lane.seconds for lane in lanes)
    emit(
        "race_end",
        {"sandboxes": workers, "seconds": round(wall, 1), "sequential_seconds": round(sequential, 1)},
    )
    emit("log_line", {"text": f"Race finished in {wall:.1f}s on {workers} sandboxes (one at a time would take ~{sequential:.1f}s)"})
    return lanes


def _clean_on_top(suite: SuiteRun, baseline: SuiteRun, issues: list[Issue], results: dict[str, FixResult]) -> bool:
    # Fixes that each finished alone can still hang or crash together.
    if not suite.completed:
        return False
    if suite.problem_ids - baseline.problem_ids:
        return False
    for issue in issues:
        if issue.kind == "test" and issue.test_id in suite.problem_ids:
            return False
        proof = results[issue.key].proof
        if proof and proof.status == "reproduced" and any(p.startswith(f"{proof.test_path}") for p in suite.problem_ids):
            return False
    return True


def merge(
    lanes: list[_LaneResult],
    engine: FixEngine,
    baseline: SuiteRun,
    *,
    emit: Emit,
    on_applied: OnApplied,
) -> tuple[list[Outcome], SuiteRun]:
    """Combine the lanes' verified fixes into engine.working_dir. Calls
    `on_applied` for each fix as it lands there, in order."""
    emit("merge_start", {"fixes": sum(1 for lane in lanes if lane.result.status == "fixed")})
    outcomes: dict[str, Outcome] = {}
    verified = [lane for lane in lanes if lane.result.status == "fixed"]
    for lane in lanes:
        if lane.result.status != "fixed":
            outcomes[lane.issue.key] = Outcome(lane.issue, lane.result.status, lane.result)

    results = {lane.issue.key: lane.result for lane in verified}

    # Fast path: everything at once, one verification run.
    scratch = _scratch_copy(engine.working_dir)
    try:
        combined = True
        for lane in verified:
            try:
                lane.result.apply_to(scratch)
            except DiffError:
                combined = False
                break
        suite = engine.run_suite(scratch) if combined and verified else None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if suite is not None and _clean_on_top(suite, baseline, [lane.issue for lane in verified], results):
        emit("log_line", {"text": f"MERGE: all {len(verified)} fixes combine cleanly, full suite re-verified in the sandbox"})
        for lane in verified:
            lane.result.changed_files = lane.result.apply_to(engine.working_dir)
            on_applied(lane.issue, lane.result)
            outcomes[lane.issue.key] = Outcome(lane.issue, "fixed", lane.result)
        emit("merge_end", {"clean": True})
        return [outcomes[lane.issue.key] for lane in lanes], suite

    # Slow path: one at a time, re-verifying, re-fixing what doesn't fit.
    if verified:
        why = f" (the combined suite didn't finish: {engine.unfinished(suite).splitlines()[0]})" if suite is not None and not suite.completed else ""
        emit("log_line", {"text": f"MERGE: fixes interact when combined{why}; merging one at a time and re-verifying each"})
    for lane in verified:
        issue = lane.issue
        if issue.kind == "test" and issue.test_id not in baseline.problem_ids:
            emit("log_line", {"text": f"MERGE: {issue.ref} already passes after the fixes merged before it"})
            outcomes[issue.key] = Outcome(issue, "fixed", None, incidental=True)
            continue
        scratch = _scratch_copy(engine.working_dir)
        try:
            try:
                lane.result.apply_to(scratch)
                suite = engine.run_suite(scratch)
                fits = _clean_on_top(suite, baseline, [issue], results)
            except DiffError:
                fits = False
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        if fits:
            lane.result.changed_files = lane.result.apply_to(engine.working_dir)
            baseline = suite
            on_applied(issue, lane.result)
            outcomes[issue.key] = Outcome(issue, "fixed", lane.result)
            emit("log_line", {"text": f"MERGE: {issue.ref} merged and re-verified"})
            continue

        emit("log_line", {"text": f"MERGE: {issue.ref}'s fix conflicts with the others, re-fixing it on top of them"})
        with usage.for_issue(issue.key):
            redo = engine.fix(issue, baseline)
        if redo.status == "fixed":
            baseline = redo.suite_after or baseline
            on_applied(issue, redo)
        outcomes[issue.key] = Outcome(issue, redo.status, redo)

    emit("merge_end", {"clean": False})
    return [outcomes[lane.issue.key] for lane in lanes], baseline
