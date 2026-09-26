"""FixEngine end to end: real diff application, real pytest runs (via
LocalSandbox), real output parsing. Only the Nemotron calls are scripted."""
from unittest.mock import patch

import pytest
from conftest import FakePlanner, LocalSandbox, fake_evaluator, make_diff, plan

from greenlit.issues import Issue
from greenlit.orchestrator import FixEngine
from greenlit.project import TEST_COMMAND

ADD_FIXED = "    return a + b"
AVG_FIXED = "    return sum(numbers) / len(numbers)"


def _calc_diff(repo, old: str, new: str) -> str:
    text = (repo / "calculator.py").read_text()
    assert old in text
    return make_diff("calculator.py", text, text.replace(old, new))


def _test_issue(test_id: str) -> Issue:
    return Issue(key=f"test:{test_id}", kind="test", title=f"Failing test: {test_id}", test_id=test_id)


def _run_fix(repo, issue, planner, *, max_iterations=3, research=None):
    events = []
    sandbox = LocalSandbox()
    engine = FixEngine(sandbox, repo, None, TEST_COMMAND, emit=lambda t, p: events.append((t, p)), max_iterations=max_iterations)
    baseline = engine.run_suite()
    with (
        patch("greenlit.orchestrator.call_planner", planner),
        patch("greenlit.orchestrator.call_evaluator", fake_evaluator),
        patch("greenlit.orchestrator.research", research or (lambda q: None)),
    ):
        result = engine.fix(issue, baseline)
    return result, events, baseline


def test_failing_test_fixed_first_try(copy_fixture):
    repo = copy_fixture("fixture_multi")
    planner = FakePlanner({"test_add": [plan(_calc_diff(repo, "    return a - b", ADD_FIXED))]})

    result, events, baseline = _run_fix(repo, _test_issue("test_calculator.py::test_add"), planner)

    assert result.status == "fixed" and result.iterations == 1
    assert result.changed_files == ["calculator.py"]
    assert ADD_FIXED in (repo / "calculator.py").read_text()
    assert "test_calculator.py::test_add" not in result.suite_after.problem_ids
    assert "test_calculator.py::test_average" in result.suite_after.problem_ids
    # The planner got the real traceback and the real source files.
    assert "assert add(2, 3) == 5" in planner.calls[0]["stack_trace"]
    assert set(planner.calls[0]["source_files"]) == {"calculator.py", "test_calculator.py"}
    stages = [p["stage"] for t, p in events if t == "stage_start"]
    assert stages == ["perceive", "plan", "act", "evaluate"]


def test_diff_that_does_not_apply_is_retried_not_fatal(copy_fixture):
    repo = copy_fixture("fixture_multi")
    garbage = "--- a/calculator.py\n+++ b/calculator.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a * b\n+    return a + b\n"
    good = _calc_diff(repo, "    return a - b", ADD_FIXED)
    planner = FakePlanner({"test_add": [plan(garbage), plan(good)]})

    result, _, _ = _run_fix(repo, _test_issue("test_calculator.py::test_add"), planner)

    assert result.status == "fixed" and result.iterations == 2
    assert "did not apply" in result.attempts[0].why_it_failed
    assert planner.calls[1]["prior_attempts"][0]["diff"] == garbage


def test_editing_the_test_instead_of_the_code_is_rejected(copy_fixture):
    repo = copy_fixture("fixture_multi")
    test_text = (repo / "test_calculator.py").read_text()
    cheat = make_diff("test_calculator.py", test_text, test_text.replace("== 5", "== -1"))
    planner = FakePlanner({"test_add": [plan(cheat)]})

    result, _, _ = _run_fix(repo, _test_issue("test_calculator.py::test_add"), planner, max_iterations=2)

    assert result.status == "unresolved"
    assert all("edits test files" in a.why_it_failed for a in result.attempts)
    assert (repo / "test_calculator.py").read_text() == test_text


def test_fix_that_breaks_a_passing_test_is_rejected(copy_fixture):
    repo = copy_fixture("fixture_multi")
    text = (repo / "calculator.py").read_text()
    # Fixes add() but also breaks divide(), which currently passes.
    breaking = make_diff(
        "calculator.py",
        text,
        text.replace("    return a - b", ADD_FIXED).replace("    return a / b", "    return a // b + 1"),
    )
    planner = FakePlanner({"test_add": [plan(breaking)]})

    result, _, _ = _run_fix(repo, _test_issue("test_calculator.py::test_add"), planner, max_iterations=1)

    assert result.status == "unresolved"
    assert "previously-passing" in result.attempts[0].why_it_failed
    assert "test_calculator.py::test_divide" in result.attempts[0].why_it_failed
    assert (repo / "calculator.py").read_text() == text


@pytest.fixture
def review_repo(tmp_path):
    """A bug no test covers: clamp() ignores its upper bound."""
    (tmp_path / "limits.py").write_text("def clamp(x, lo, hi):\n    return max(lo, x)\n")
    (tmp_path / "test_limits.py").write_text("from limits import clamp\n\ndef test_low():\n    assert clamp(-5, 0, 10) == 0\n")
    return tmp_path


def _review_issue():
    return Issue(
        key="review:1",
        kind="review",
        title="clamp ignores the upper bound",
        file="limits.py",
        line=2,
        severity="high",
        description="clamp(50, 0, 10) returns 50",
        evidence="return max(lo, x)",
    )


def test_review_issue_fixed_when_it_compiles_and_breaks_nothing(review_repo):
    text = (review_repo / "limits.py").read_text()
    fix = make_diff("limits.py", text, text.replace("max(lo, x)", "min(hi, max(lo, x))"))
    planner = FakePlanner({"clamp ignores": [plan(fix)]})

    result, _, _ = _run_fix(review_repo, _review_issue(), planner)

    assert result.status == "fixed"
    assert "min(hi, max(lo, x))" in (review_repo / "limits.py").read_text()
    assert planner.calls[0]["issue"]["location"] == "limits.py:2"
    assert "def clamp" in planner.calls[0]["source_files"]["limits.py"]


def test_review_fix_that_does_not_compile_is_rejected(review_repo):
    text = (review_repo / "limits.py").read_text()
    broken = make_diff("limits.py", text, text.replace("max(lo, x)", "min(hi, max(lo, x)"))
    planner = FakePlanner({"clamp ignores": [plan(broken)]})

    result, _, _ = _run_fix(review_repo, _review_issue(), planner, max_iterations=1)

    assert result.status == "unresolved"
    assert "doesn't compile" in result.attempts[0].why_it_failed


def test_review_fix_must_touch_the_reported_file(review_repo):
    unrelated = "--- /dev/null\n+++ b/notes.py\n@@ -0,0 +1 @@\n+x = 1\n"
    planner = FakePlanner({"clamp ignores": [plan(unrelated)]})

    result, _, _ = _run_fix(review_repo, _review_issue(), planner, max_iterations=1)

    assert result.status == "unresolved"
    assert "doesn't touch limits.py" in result.attempts[0].why_it_failed


def test_unfamiliar_api_triggers_research_then_replans(copy_fixture):
    repo = copy_fixture("fixture_multi")
    good = _calc_diff(repo, "    return a - b", ADD_FIXED)
    planner = FakePlanner({"test_add": [plan(good, unfamiliar=True, query="python operator docs"), plan(good)]})
    queries = []

    def fake_research(query):
        queries.append(query)
        return "DOCS: use + for addition"

    result, events, _ = _run_fix(repo, _test_issue("test_calculator.py::test_add"), planner, research=fake_research)

    assert result.status == "fixed"
    assert queries == ["python operator docs"]
    assert planner.calls[1]["research_context"] == "DOCS: use + for addition"
    stages = [p["stage"] for t, p in events if t == "stage_start"]
    assert stages == ["perceive", "plan", "research", "plan", "act", "evaluate"]
