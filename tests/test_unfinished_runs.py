"""A test run that doesn't finish proves nothing (issue #1).

If a candidate fix crashes the interpreter, hangs, or ends the process
before pytest reports, the run has no FAILED lines to count. These tests pin
down that such a run is treated as a rejection, never as "no failures".
Everything here runs real pytest through LocalSandbox; hangs are real too,
cut off by the same `timeout` wrapper the Nebius sandbox uses.
"""
import time
from unittest.mock import patch

import pytest
from conftest import FakePlanner, FakeTestWriter, LocalSandbox, fake_evaluator, fake_repro_judge, make_diff, plan

from greenlit.agent import run_agent
from greenlit.issues import Issue
from greenlit.orchestrator import FixEngine
from greenlit.parallel import _clean_on_top
from greenlit.perceive import parse_suite_output
from greenlit.project import TEST_COMMAND

ADD_ISSUE = Issue(key="test:test_calculator.py::test_add", kind="test", title="add", test_id="test_calculator.py::test_add")


def _engine(repo, events=None, **kwargs):
    emit = (lambda t, p: events.append((t, p))) if events is not None else (lambda t, p: None)
    return FixEngine(LocalSandbox(), repo, None, TEST_COMMAND, emit=emit, max_iterations=1, **kwargs)


def _fix(engine, issue, planner, *, evaluator=fake_evaluator, writer=None):
    baseline = engine.run_suite()
    with (
        patch("greenlit.orchestrator.call_planner", planner),
        patch("greenlit.orchestrator.call_evaluator", evaluator),
        patch("greenlit.orchestrator.call_test_writer", writer or FakeTestWriter()),
        patch("greenlit.orchestrator.call_repro_judge", fake_repro_judge),
    ):
        return engine.fix(issue, baseline)


# --- SuiteRun.completed ---------------------------------------------------------


@pytest.mark.parametrize(
    "exit_code, output, completed",
    [
        (0, "3 passed in 0.01s", True),
        (1, "FAILED t.py::test_x - assert 1 == 2\n1 failed, 2 passed", True),
        (5, "no tests ran in 0.01s", True),
        (0, "..", False),  # the process ended before pytest's summary: os._exit(0)
        (124, "..", False),  # stopped by `timeout`
        (137, "", False),  # killed after the grace period
        (3, "INTERNALERROR> boom", False),
        (2, "!!! Interrupted: 1 error during collection !!!\n1 error", False),
        (1, "ERROR: Could not install packages", False),  # install step failed, pytest never ran
    ],
)
def test_completed_requires_a_summary_and_a_finished_exit_code(exit_code, output, completed):
    assert parse_suite_output(exit_code, output).completed is completed


def test_incomplete_reasons_say_what_happened():
    assert "timed out" in parse_suite_output(124, "").incomplete_reason()
    assert "internal error" in parse_suite_output(3, "INTERNALERROR> boom").incomplete_reason()
    reason = parse_suite_output(0, "test_calculator.py ..").incomplete_reason()
    assert "without reporting any results" in reason and "test_calculator.py .." in reason


# --- fixes judged on unfinished runs ----------------------------------------------


def test_fix_that_kills_the_suite_elsewhere_is_rejected(copy_fixture):
    """The reproduction from issue #1: add() is fixed, divide() now ends the process."""
    repo = copy_fixture("fixture_multi")
    src = (repo / "calculator.py").read_text()
    bad = src.replace("return a - b", "return a + b").replace("def divide(a, b):\n", "def divide(a, b):\n    import os; os._exit(0)\n")

    result = _fix(_engine(repo), ADD_ISSUE, FakePlanner({"test_add": [plan(make_diff("calculator.py", src, bad))]}))

    assert result.status == "unresolved"
    assert "full test suite didn't finish" in result.attempts[0].why_it_failed
    assert "without reporting any results" in result.attempts[0].why_it_failed
    assert (repo / "calculator.py").read_text() == src  # nothing was applied


def test_fix_that_ends_the_process_before_the_assertion_is_rejected_without_a_nano_call(copy_fixture):
    repo = copy_fixture("fixture_multi")
    src = (repo / "calculator.py").read_text()
    bad = src.replace("    return a - b", "    import os; os._exit(0)")
    nano_calls = []

    def evaluator(**kwargs):
        nano_calls.append(kwargs)
        return fake_evaluator(**kwargs)

    events = []
    result = _fix(_engine(repo, events), ADD_ISSUE, FakePlanner({"test_add": [plan(make_diff("calculator.py", src, bad))]}), evaluator=evaluator)

    assert result.status == "unresolved"
    assert "run of test_calculator.py::test_add didn't finish" in result.attempts[0].why_it_failed
    assert nano_calls == []  # exit code 0, but never shown to Nano as a pass
    assert ("stage_end", {"stage": "evaluate", "result": {"status": "INCOMPLETE"}}) in events


def test_fix_that_hangs_is_stopped_by_the_time_limit_and_rejected(copy_fixture):
    repo = copy_fixture("fixture_multi")
    src = (repo / "calculator.py").read_text()
    hangs = src.replace("return a - b", "return a + b").replace("def divide(a, b):\n", "def divide(a, b):\n    while True:\n        pass\n")
    engine = _engine(repo, test_timeout=2)

    started = time.monotonic()
    result = _fix(engine, ADD_ISSUE, FakePlanner({"test_add": [plan(make_diff("calculator.py", src, hangs))]}))

    assert time.monotonic() - started < 30
    assert result.status == "unresolved"
    assert "timed out after 2s" in result.attempts[0].why_it_failed
    assert all(cmd.count("timeout -k 10 2 ") == 1 for cmd in engine.sandbox.commands)


def test_the_planner_hears_why_and_the_next_attempt_can_succeed(copy_fixture):
    repo = copy_fixture("fixture_multi")
    src = (repo / "calculator.py").read_text()
    bad = src.replace("return a - b", "return a + b").replace("def divide(a, b):\n", "def divide(a, b):\n    import os; os._exit(0)\n")
    good = src.replace("return a - b", "return a + b")
    planner = FakePlanner({"test_add": [plan(make_diff("calculator.py", src, bad)), plan(make_diff("calculator.py", src, good))]})
    engine = FixEngine(LocalSandbox(), repo, None, TEST_COMMAND, max_iterations=2)

    result = _fix(engine, ADD_ISSUE, planner)

    assert result.status == "fixed" and result.iterations == 2
    assert "didn't finish" in planner.calls[1]["prior_attempts"][0]["why_it_failed"]
    assert result.suite_after.completed


@pytest.fixture
def review_repo(tmp_path):
    (tmp_path / "limits.py").write_text("def clamp(x, lo, hi):\n    return max(lo, x)\n\n\ndef double(x):\n    return x * 2\n")
    (tmp_path / "test_limits.py").write_text(
        "from limits import clamp, double\n\n\ndef test_low():\n    assert clamp(-5, 0, 10) == 0\n\n\ndef test_double():\n    assert double(2) == 4\n"
    )
    return tmp_path


def test_review_fix_that_kills_the_suite_is_rejected(review_repo):
    text = (review_repo / "limits.py").read_text()
    bad = text.replace("max(lo, x)", "min(hi, max(lo, x))").replace("    return x * 2", "    import os; os._exit(0)")
    issue = Issue(key="review:1", kind="review", title="clamp ignores hi", file="limits.py", line=2, severity="high", description="d", evidence="e")

    # No reproduction test (the writer's tests can't import), so this is the
    # compile + no-regression path.
    result = _fix(_engine(review_repo), issue, FakePlanner({"clamp ignores": [plan(make_diff("limits.py", text, bad))]}))

    assert result.proof.status == "unproven"
    assert result.status == "unresolved"
    assert "full test suite didn't finish" in result.attempts[0].why_it_failed


def test_reproduction_test_that_hangs_is_not_mistaken_for_passing(tmp_path):
    """A real hang bug mustn't be dismissed as a false positive because its
    reproduction test never finished."""
    (tmp_path / "countdown.py").write_text("def countdown(n):\n    while n != 0:\n        n -= 1\n    return True\n")
    (tmp_path / "test_countdown.py").write_text("from countdown import countdown\n\n\ndef test_three():\n    assert countdown(3)\n")
    issue = Issue(
        key="review:1", kind="review", title="countdown never returns for negative n", file="countdown.py", line=2,
        severity="high", description="countdown(-1) loops forever", evidence="while n != 0",
    )
    hang_test = "from countdown import countdown\n\n\ndef test_negative():\n    assert countdown(-1)\n"
    text = (tmp_path / "countdown.py").read_text()
    fix = make_diff("countdown.py", text, text.replace("while n != 0", "while n > 0"))

    result = _fix(
        _engine(tmp_path, test_timeout=2),
        issue,
        FakePlanner({"countdown never": [plan(fix)]}),
        writer=FakeTestWriter({"countdown never": [hang_test]}),
    )

    assert result.proof.status == "unproven"  # not "not_reproduced"
    assert result.status == "fixed"


# --- merge and baseline ------------------------------------------------------------


def test_merge_never_accepts_an_unfinished_combined_suite():
    baseline = parse_suite_output(1, "FAILED t.py::test_a - x\n1 failed, 1 passed")
    crashed = parse_suite_output(0, "t.py .")
    hung = parse_suite_output(124, "t.py .")
    for suite in (crashed, hung):
        assert _clean_on_top(suite, baseline, [], {}) is False


def test_baseline_that_times_out_is_a_clear_error(tmp_path, monkeypatch):
    (tmp_path / "slow.py").write_text("def wait():\n    while True:\n        pass\n")
    (tmp_path / "test_slow.py").write_text("from slow import wait\n\n\ndef test_wait():\n    wait()\n")
    monkeypatch.setenv("GREENLIT_TEST_TIMEOUT", "2")
    events = []

    result = run_agent(
        str(tmp_path), emit=lambda t, p: events.append((t, p)), sandbox_factory=LocalSandbox, allow_local=True, include_review=False
    )

    assert result.status == "error"
    message = next(p["message"] for t, p in events if t == "run_error")
    assert "didn't finish within 2s" in message and "GREENLIT_TEST_TIMEOUT" in message
