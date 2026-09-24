"""Control-flow test for greenlit/orchestrator.py.

Doesn't need real credentials: call_planner, call_evaluator, research, and
Sandbox are all faked. What's real: diff application via `patch` against
the actual demo/fixture_simple files, and perceive()'s traceback parsing.
This is what actually proves the loop's control flow (iteration counting,
attempt-history accumulation, max-iteration cutoff, the research
re-plan branch) is correct, independent of whether the live models/sandbox
are reachable yet.

Usage: python scripts/test_orchestrator.py
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenlit.clients.sandbox import SandboxResult
from greenlit.orchestrator import run

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "demo" / "fixture_simple"
TEST_COMMAND = "pytest -q"

ORIGINAL_APP_PY = (FIXTURE_DIR / "app.py").read_text()
FIXED_APP_PY = ORIGINAL_APP_PY.replace(
    "def main():\n    print(greeting)",
    'def main():\n    greeting = "Hello, Greenlit"\n    print(greeting)',
)
assert FIXED_APP_PY != ORIGINAL_APP_PY, "fixture text didn't match, fix the test"

FAIL_RESULT = SandboxResult(
    stdout="",
    stderr=(
        "Traceback (most recent call last):\n"
        '  File "test_app.py", line 4, in test_greeting\n'
        "    main()\n"
        '  File "app.py", line 2, in main\n'
        "    print(greeting)\n"
        "NameError: name 'greeting' is not defined"
    ),
    exit_code=1,
)
PASS_RESULT = SandboxResult(stdout="1 passed in 0.05s", stderr="", exit_code=0)


def _make_fix_diff() -> str:
    return "".join(
        difflib.unified_diff(
            ORIGINAL_APP_PY.splitlines(keepends=True),
            FIXED_APP_PY.splitlines(keepends=True),
            fromfile="a/app.py",
            tofile="b/app.py",
        )
    )


class FakeSandbox:
    """Records what it's asked to run and hands back canned results in
    order. Constructed as `Sandbox(config)` by the orchestrator, so this
    class's __init__ must accept (and ignore) a config arg."""

    def __init__(self, _config, *, responses):
        self._responses = list(responses)
        self.calls: list[tuple[Path, str]] = []

    def run_tests(self, repo_dir: Path, test_command: str) -> SandboxResult:
        self.calls.append((repo_dir, test_command))
        if not self._responses:
            raise AssertionError("FakeSandbox ran out of canned responses")
        return self._responses.pop(0)

    def close(self) -> None:
        pass


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run_with_fakes(*, sandbox_responses, planner_side_effect, evaluator_side_effect, max_iterations=5):
    events: list[tuple[str, dict]] = []

    def emit(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    fake_sandbox = FakeSandbox(None, responses=sandbox_responses)

    with (
        patch("greenlit.orchestrator.GreenlitConfig") as MockConfig,
        patch("greenlit.orchestrator.Sandbox", return_value=fake_sandbox),
        patch("greenlit.orchestrator.call_planner", side_effect=planner_side_effect) as mock_planner,
        patch("greenlit.orchestrator.call_evaluator", side_effect=evaluator_side_effect) as mock_evaluator,
        patch("greenlit.orchestrator.research") as mock_research,
    ):
        MockConfig.from_env.return_value = object()
        result = run(FIXTURE_DIR, TEST_COMMAND, max_iterations=max_iterations, emit=emit)

    return result, events, fake_sandbox, mock_planner, mock_evaluator, mock_research


def test_pass_on_first_try() -> None:
    diff = _make_fix_diff()
    result, events, sandbox, planner, evaluator, research_mock = _run_with_fakes(
        sandbox_responses=[FAIL_RESULT, PASS_RESULT],
        planner_side_effect=[
            {"diff": diff, "rationale": "fix it", "unfamiliar_api": False, "unfamiliar_api_query": None}
        ],
        evaluator_side_effect=[{"status": "PASS", "error_summary": ""}],
    )
    _check(result.status == "fixed", f"expected fixed, got {result.status}")
    _check(result.iterations == 1, f"expected 1 iteration, got {result.iterations}")
    _check(len(result.attempts) == 0, "no failed attempts expected on first-try pass")
    _check(planner.call_count == 1, f"expected 1 planner call, got {planner.call_count}")
    _check(len(sandbox.calls) == 2, f"expected perceive+act = 2 sandbox calls, got {len(sandbox.calls)}")
    _check(("status", {"value": "fixed"}) in events, "expected a fixed status event")
    print("test_pass_on_first_try OK")


def test_fail_then_pass_accumulates_attempts() -> None:
    diff = _make_fix_diff()
    result, events, sandbox, planner, evaluator, research_mock = _run_with_fakes(
        sandbox_responses=[FAIL_RESULT, FAIL_RESULT, PASS_RESULT],
        planner_side_effect=[
            {"diff": diff, "rationale": "attempt 1", "unfamiliar_api": False, "unfamiliar_api_query": None},
            {"diff": diff, "rationale": "attempt 2", "unfamiliar_api": False, "unfamiliar_api_query": None},
        ],
        evaluator_side_effect=[
            {"status": "FAIL_SAME_ERROR", "error_summary": "still broken"},
            {"status": "PASS", "error_summary": ""},
        ],
    )
    _check(result.status == "fixed", f"expected fixed, got {result.status}")
    _check(result.iterations == 2, f"expected 2 iterations, got {result.iterations}")
    _check(len(result.attempts) == 1, f"expected 1 recorded failed attempt, got {len(result.attempts)}")
    _check(result.attempts[0].why_it_failed == "still broken", "attempt should carry evaluator's summary")
    iteration_events = [p["count"] for t, p in events if t == "iteration"]
    _check(iteration_events == [1, 2], f"expected iteration events [1, 2], got {iteration_events}")
    print("test_fail_then_pass_accumulates_attempts OK")


def test_hits_max_iterations() -> None:
    diff = _make_fix_diff()
    result, events, sandbox, planner, evaluator, research_mock = _run_with_fakes(
        sandbox_responses=[FAIL_RESULT, FAIL_RESULT, FAIL_RESULT],
        planner_side_effect=[
            {"diff": diff, "rationale": f"attempt {i}", "unfamiliar_api": False, "unfamiliar_api_query": None}
            for i in range(1, 3)
        ],
        evaluator_side_effect=[
            {"status": "FAIL_SAME_ERROR", "error_summary": "still broken"},
            {"status": "FAIL_SAME_ERROR", "error_summary": "still broken"},
        ],
        max_iterations=2,
    )
    _check(result.status == "unresolved", f"expected unresolved, got {result.status}")
    _check(result.iterations == 2, f"expected 2 iterations (the cap), got {result.iterations}")
    _check(len(result.attempts) == 2, f"expected 2 recorded attempts, got {len(result.attempts)}")
    _check(("status", {"value": "unresolved"}) in events, "expected an unresolved status event")
    print("test_hits_max_iterations OK")


def test_unfamiliar_api_triggers_research_and_replan() -> None:
    diff = _make_fix_diff()
    result, events, sandbox, planner, evaluator, research_mock = _run_with_fakes(
        sandbox_responses=[FAIL_RESULT, PASS_RESULT],
        planner_side_effect=[
            {
                "diff": diff,
                "rationale": "need docs first",
                "unfamiliar_api": True,
                "unfamiliar_api_query": "some library changelog",
            },
            {
                "diff": diff,
                "rationale": "now informed",
                "unfamiliar_api": False,
                "unfamiliar_api_query": None,
            },
        ],
        evaluator_side_effect=[{"status": "PASS", "error_summary": ""}],
    )
    _check(result.status == "fixed", f"expected fixed, got {result.status}")
    _check(planner.call_count == 2, f"expected 2 planner calls (research re-plan), got {planner.call_count}")
    _check(research_mock.call_count == 1, f"expected 1 research call, got {research_mock.call_count}")
    research_mock.assert_called_with("some library changelog")
    stage_starts = [p["stage"] for t, p in events if t == "stage_start"]
    _check("research" in stage_starts, f"expected a research stage in {stage_starts}")
    _check(
        stage_starts.count("plan") == 2,
        f"expected plan to start twice (before and after research), got {stage_starts.count('plan')}",
    )
    print("test_unfamiliar_api_triggers_research_and_replan OK")


def main() -> int:
    for test in [
        test_pass_on_first_try,
        test_fail_then_pass_accumulates_attempts,
        test_hits_max_iterations,
        test_unfamiliar_api_triggers_research_and_replan,
    ]:
        test()
    print("\nAll orchestrator control-flow checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - top-level smoke test, want a readable message
        print(f"\nTEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
