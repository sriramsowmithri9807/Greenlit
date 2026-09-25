"""Control-flow test for greenlit/orchestrator.py's repo-wide agent.

Doesn't need real credentials: call_planner, call_evaluator, research, and
Sandbox are all faked. What's real: diff application via `patch` against
the actual demo/fixture_simple files, and perceive.py's regex parsing
(both the per-test traceback parser and the whole-suite failure-summary
parser) — that's what actually proves the multi-issue control flow
(worklist discovery, per-issue retry with attempt history, give-up +
skip-list, re-discovery after each accepted fix) is correct, independent
of whether the live models/sandbox are reachable yet.

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

ORIGINAL_APP_PY = (FIXTURE_DIR / "app.py").read_text()
FIXED_APP_PY = ORIGINAL_APP_PY.replace(
    "def main():\n    print(greeting)",
    'def main():\n    greeting = "Hello, Greenlit"\n    print(greeting)',
)
assert FIXED_APP_PY != ORIGINAL_APP_PY, "fixture text didn't match, fix the test"


def _make_fix_diff() -> str:
    return "".join(
        difflib.unified_diff(
            ORIGINAL_APP_PY.splitlines(keepends=True),
            FIXED_APP_PY.splitlines(keepends=True),
            fromfile="a/app.py",
            tofile="b/app.py",
        )
    )


def _suite_result(failing_test_ids: list[str]) -> SandboxResult:
    """A whole-suite pytest result: exit_code + a short-summary block
    listing each failing test id, matching real pytest's output shape."""
    if not failing_test_ids:
        return SandboxResult(stdout="3 passed in 0.05s", stderr="", exit_code=0)
    summary = "\n".join(f"FAILED {tid} - AssertionError" for tid in failing_test_ids)
    return SandboxResult(
        stdout=f"{len(failing_test_ids)} failed\n{summary}", stderr="", exit_code=1
    )


def _scoped_fail_result(test_id: str) -> SandboxResult:
    return SandboxResult(
        stdout="",
        stderr=(
            "Traceback (most recent call last):\n"
            f'  File "test_app.py", line 4, in {test_id.split("::")[-1]}\n'
            "    main()\n"
            '  File "app.py", line 2, in main\n'
            "    print(greeting)\n"
            "NameError: name 'greeting' is not defined"
        ),
        exit_code=1,
    )


SCOPED_PASS_RESULT = SandboxResult(stdout="1 passed in 0.02s", stderr="", exit_code=0)


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
            raise AssertionError(f"FakeSandbox ran out of canned responses at call {len(self.calls)}")
        return self._responses.pop(0)

    def close(self) -> None:
        pass


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run_with_fakes(
    *, sandbox_responses, planner_side_effect, evaluator_side_effect, max_issues=10, max_iterations=5
):
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
        result = run(
            FIXTURE_DIR, max_issues=max_issues, max_iterations_per_issue=max_iterations, emit=emit
        )

    return result, events, fake_sandbox, mock_planner, mock_evaluator, mock_research


def test_already_passing_repo_does_nothing() -> None:
    result, events, sandbox, planner, evaluator, research_mock = _run_with_fakes(
        sandbox_responses=[_suite_result([])],
        planner_side_effect=[],
        evaluator_side_effect=[],
    )
    _check(result.status == "fixed", f"expected fixed, got {result.status}")
    _check(result.fixed_issues == [], "no issues should have been touched")
    _check(planner.call_count == 0, "planner should never be called on an already-passing repo")
    _check(len(sandbox.calls) == 1, f"expected exactly 1 discovery call, got {len(sandbox.calls)}")
    print("test_already_passing_repo_does_nothing OK")


def test_single_issue_fixed_in_one_attempt() -> None:
    diff = _make_fix_diff()
    result, events, sandbox, planner, evaluator, research_mock = _run_with_fakes(
        sandbox_responses=[
            _suite_result(["test_app.py::test_greeting"]),  # pass 1 discovery
            _scoped_fail_result("test_app.py::test_greeting"),  # perceive_one
            SCOPED_PASS_RESULT,  # act (iteration 1)
            _suite_result([]),  # pass 2 discovery: now clean
        ],
        planner_side_effect=[
            {"diff": diff, "rationale": "fix it", "unfamiliar_api": False, "unfamiliar_api_query": None}
        ],
        evaluator_side_effect=[{"status": "PASS", "error_summary": ""}],
    )
    _check(result.status == "fixed", f"expected fixed, got {result.status}")
    _check(result.fixed_issues == ["test_app.py::test_greeting"], f"got {result.fixed_issues}")
    _check(result.unresolved_issues == [], f"expected no unresolved issues, got {result.unresolved_issues}")
    _check(len(sandbox.calls) == 4, f"expected 4 sandbox calls, got {len(sandbox.calls)}")
    _check(("issue_start", {"issue": "test_app.py::test_greeting", "remaining": 1}) in events, "missing issue_start")
    _check(("issue_end", {"issue": "test_app.py::test_greeting", "status": "fixed"}) in events, "missing issue_end")
    # The accepted diff must have been applied to the *working* copy, not just a scratch copy.
    applied_content = (result.working_dir / "app.py").read_text()
    _check(applied_content == FIXED_APP_PY, "accepted diff wasn't persisted onto the working copy")
    print("test_single_issue_fixed_in_one_attempt OK")


def test_two_issues_one_fixed_one_given_up() -> None:
    diff = _make_fix_diff()
    result, events, sandbox, planner, evaluator, research_mock = _run_with_fakes(
        sandbox_responses=[
            _suite_result(["test_a.py::test_a", "test_b.py::test_b"]),  # pass 1: two failures
            _scoped_fail_result("test_a.py::test_a"),  # perceive_one(A)
            SCOPED_PASS_RESULT,  # act(A) iter 1 -> pass
            _suite_result(["test_b.py::test_b"]),  # pass 2: only B left
            _scoped_fail_result("test_b.py::test_b"),  # perceive_one(B)
            _scoped_fail_result("test_b.py::test_b"),  # act(B) iter 1 -> fail
            _scoped_fail_result("test_b.py::test_b"),  # act(B) iter 2 -> fail (max_iterations=2)
            _suite_result(["test_b.py::test_b"]),  # pass 3: B still failing, but now given up
        ],
        planner_side_effect=[
            {"diff": diff, "rationale": "fix A", "unfamiliar_api": False, "unfamiliar_api_query": None},
            {"diff": diff, "rationale": "attempt 1 on B", "unfamiliar_api": False, "unfamiliar_api_query": None},
            {"diff": diff, "rationale": "attempt 2 on B", "unfamiliar_api": False, "unfamiliar_api_query": None},
        ],
        evaluator_side_effect=[
            {"status": "PASS", "error_summary": ""},
            {"status": "FAIL_SAME_ERROR", "error_summary": "B still broken"},
            {"status": "FAIL_SAME_ERROR", "error_summary": "B still broken"},
        ],
        max_iterations=2,
    )
    _check(result.status == "unresolved", f"expected unresolved, got {result.status}")
    _check(result.fixed_issues == ["test_a.py::test_a"], f"got {result.fixed_issues}")
    _check(result.unresolved_issues == ["test_b.py::test_b"], f"got {result.unresolved_issues}")
    _check(len(sandbox.calls) == 8, f"expected 8 sandbox calls, got {len(sandbox.calls)}")
    issue_starts = [p["issue"] for t, p in events if t == "issue_start"]
    _check(
        issue_starts == ["test_a.py::test_a", "test_b.py::test_b"],
        f"expected A then B, got {issue_starts}",
    )
    print("test_two_issues_one_fixed_one_given_up OK")


def main() -> int:
    for test in [
        test_already_passing_repo_does_nothing,
        test_single_issue_fixed_in_one_attempt,
        test_two_issues_one_fixed_one_given_up,
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
