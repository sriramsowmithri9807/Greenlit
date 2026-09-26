"""The whole agent: clone -> scan -> raise issues -> fix -> commit/push -> PR.

Real: git clone/commit/push (into a local bare repo standing in for GitHub),
diff application, pytest runs, output parsing. Scripted: Nemotron calls and
the GitHub REST API (FakeGitHubAPI records what would have been created).
"""
import json
from unittest.mock import patch

import pytest
from conftest import FIXTURES, FakeGitHubAPI, FakePlanner, LocalSandbox, fake_evaluator, git, make_diff, plan

from greenlit.agent import run_agent

TOKEN = "github_pat_TESTSECRET_123"
REPO_URL = "https://github.com/octo/calc"
CALC = (FIXTURES / "fixture_multi" / "calculator.py").read_text()
ADD_FIX = make_diff("calculator.py", CALC, CALC.replace("return a - b", "return a + b"))
AVG_FIX_ON_TOP = make_diff(
    "calculator.py",
    CALC.replace("return a - b", "return a + b"),
    CALC.replace("return a - b", "return a + b").replace(" + 1\n", "\n"),
)

DIVIDE_FINDING = {
    "title": "divide raises ZeroDivisionError for b=0",
    "file": "calculator.py",
    "line": 6,
    "severity": "medium",
    "confidence": "high",
    "description": "divide(1, 0) crashes instead of raising a clear ValueError",
    "evidence": "return a / b",
}
DIVIDE_FIX_ON_TOP = make_diff(
    "calculator.py",
    CALC.replace("return a - b", "return a + b").replace(" + 1\n", "\n"),
    CALC.replace("return a - b", "return a + b")
    .replace(" + 1\n", "\n")
    .replace("    return a / b", '    if b == 0:\n        raise ValueError("division by zero")\n    return a / b'),
)


def _run(remote, *, token=TOKEN, planner, reviewer=None, api=None, **kwargs):
    events = []
    api = api or FakeGitHubAPI(token)
    with (
        patch("greenlit.orchestrator.call_planner", planner),
        patch("greenlit.orchestrator.call_evaluator", fake_evaluator),
        patch("greenlit.review.call_reviewer", reviewer or (lambda sources, known: [])),
    ):
        result = run_agent(
            REPO_URL,
            token,
            emit=lambda t, p: events.append((t, p)),
            sandbox_factory=LocalSandbox,
            api_factory=lambda _token: api,
            remote_url=str(remote),
            **kwargs,
        )
    return result, events, api


def _types(events):
    return [t for t, _ in events]


def test_live_run_raises_issues_fixes_them_and_opens_a_pr(bare_remote):
    remote = bare_remote("fixture_multi")
    main_before = git("rev-parse", "main", cwd=remote)
    planner = FakePlanner(
        {"test_add": [plan(ADD_FIX, "add subtracted")], "test_average": [plan(AVG_FIX_ON_TOP, "average added 1")],
         "divide raises": [plan(DIVIDE_FIX_ON_TOP, "guard zero")]}
    )

    result, events, api = _run(remote, planner=planner, reviewer=lambda s, k: [DIVIDE_FINDING])

    assert result.status == "fixed"
    # Issues raised on GitHub: two failing tests, one code-review finding.
    assert [i["title"] for i in api.issues] == [
        "[Greenlit] test_add fails: assert -1 == 5",
        "[Greenlit] test_average fails: assert 3.0 == 2",
        "[Greenlit] divide raises ZeroDivisionError for b=0",
    ]
    assert "assert add(2, 3) == 5" in api.issues[0]["body"]
    assert api.labels == ["greenlit"]

    # One commit per fix on a greenlit/ branch, pushed to the remote.
    branches = git("branch", "--format=%(refname:short)", cwd=remote).splitlines()
    fix_branch = next(b for b in branches if b.startswith("greenlit/fix-"))
    log = git("log", "--format=%s|%an|%ae", f"main..{fix_branch}", cwd=remote).splitlines()
    assert [line.split("|")[0] for line in reversed(log)] == [
        "Fix #1: test_add fails: assert -1 == 5",
        "Fix #2: test_average fails: assert 3.0 == 2",
        "Fix #3: divide raises ZeroDivisionError for b=0",
    ]
    assert log[0].split("|")[1:] == ["Octo Cat", "42+octo@users.noreply.github.com"]
    # The pushed code is actually fixed.
    pushed = git("show", f"{fix_branch}:calculator.py", cwd=remote)
    assert "return a + b" in pushed and "raise ValueError" in pushed

    # The default branch was never touched.
    assert git("rev-parse", "main", cwd=remote) == main_before

    # PR from the fix branch into main, closing every issue.
    (pr,) = api.pulls
    assert (pr["head"], pr["base"]) == (fix_branch, "main")
    for n in (1, 2, 3):
        assert f"Closes #{n}" in pr["body"]
    assert "review them closely" in pr["body"]

    types = _types(events)
    phases = [p["value"] for t, p in events if t == "phase"]
    assert phases == ["clone", "scan", "raise", "fix", "publish", "done"]
    assert types.count("issue_raised") == 3 and types.count("commit") == 3
    assert ("pr_opened", {"number": 100, "url": f"{REPO_URL}/pull/100"}) in events
    assert TOKEN not in json.dumps(events)


def test_unfixable_issue_gets_a_comment_and_the_rest_still_ship(bare_remote):
    remote = bare_remote("fixture_multi")
    never_applies = "--- a/calculator.py\n+++ b/calculator.py\n@@ -1 +1 @@\n-nope\n+nope2\n"
    planner = FakePlanner({"test_add": [plan(ADD_FIX)], "test_average": [plan(never_applies)]})

    result, events, api = _run(remote, planner=planner, max_iterations=2)

    assert result.status == "partial"
    assert result.fixed == ["test:test_calculator.py::test_add"]
    assert result.unresolved == ["test:test_calculator.py::test_average"]
    ((number, comment),) = api.comments
    assert number == 2 and "tried 2 fix(es)" in comment and "did not apply" in comment
    (pr,) = api.pulls
    assert "Closes #1" in pr["body"] and "Closes #2" not in pr["body"]
    assert ("status", {"value": "partial"}) in events


def test_dry_run_verifies_fixes_but_writes_nothing_to_github(bare_remote):
    remote = bare_remote("fixture_multi")
    branches_before = git("branch", "--format=%(refname:short)", cwd=remote)
    planner = FakePlanner({"test_add": [plan(ADD_FIX)], "test_average": [plan(AVG_FIX_ON_TOP)]})

    result, events, api = _run(remote, token=None, planner=planner)

    assert result.status == "fixed"
    assert api.issues == [] and api.pulls == [] and api.comments == []
    assert git("branch", "--format=%(refname:short)", cwd=remote) == branches_before
    repo_event = next(p for t, p in events if t == "repo")
    assert repo_event["mode"] == "dry_run"
    raised = [p for t, p in events if t == "issue_raised"]
    assert len(raised) == 2 and all(p["number"] is None for p in raised)
    final_diff = [p["diff"] for t, p in events if t == "diff_ready"][-1]
    assert "+    return a + b" in final_diff and "+    return sum(numbers) / len(numbers)" in final_diff
    assert _types(events).count("commit") == 0 and "pr_opened" not in _types(events)


def test_clean_repo_raises_nothing(bare_remote):
    remote = bare_remote("fixture_multi")
    # Point the agent at a clean copy by fixing the fixture in the seed first.
    seed_fix = remote.parent / "clean"
    git("clone", "-q", str(remote), str(seed_fix), cwd=remote.parent)
    (seed_fix / "calculator.py").write_text(CALC.replace("return a - b", "return a + b").replace(" + 1\n", "\n"))
    git("commit", "-qam", "clean", cwd=seed_fix)
    git("push", "-q", "origin", "main", cwd=seed_fix)

    result, events, api = _run(remote, planner=FakePlanner({}))

    assert result.status == "clean"
    assert api.issues == [] and api.pulls == []
    assert ("status", {"value": "clean"}) in events


def test_token_without_push_access_is_refused_before_cloning(bare_remote):
    remote = bare_remote("fixture_multi")
    result, events, api = _run(remote, planner=FakePlanner({}), api=FakeGitHubAPI(TOKEN, push=False))

    assert result.status == "error"
    (message,) = [p["message"] for t, p in events if t == "run_error"]
    assert "can't push" in message and "dry run" in message
    assert api.issues == []


def test_bad_url_is_a_friendly_error():
    events = []
    result = run_agent("https://gitlab.com/octo/calc", emit=lambda t, p: events.append((t, p)))
    assert result.status == "error"
    assert "Not a GitHub repository URL" in next(p["message"] for t, p in events if t == "run_error")


def test_crash_mid_run_is_reported_without_leaking_the_token(bare_remote):
    remote = bare_remote("fixture_multi")

    def exploding_planner(context):
        raise RuntimeError(f"upstream blew up while holding {TOKEN}")

    result, events, _ = _run(remote, planner=exploding_planner)

    assert result.status == "error"
    message = next(p["message"] for t, p in events if t == "run_error")
    assert "upstream blew up" in message and TOKEN not in message


def test_local_folder_runs_as_dry_run(copy_fixture):
    events = []
    planner = FakePlanner({"test_add": [plan(ADD_FIX)], "test_average": [plan(AVG_FIX_ON_TOP)]})
    with (
        patch("greenlit.orchestrator.call_planner", planner),
        patch("greenlit.orchestrator.call_evaluator", fake_evaluator),
        patch("greenlit.review.call_reviewer", lambda s, k: []),
    ):
        result = run_agent(
            str(copy_fixture("fixture_multi")),
            "a-token-that-must-be-ignored",
            emit=lambda t, p: events.append((t, p)),
            sandbox_factory=LocalSandbox,
            allow_local=True,
        )
    assert result.status == "fixed"
    assert next(p for t, p in events if t == "repo")["mode"] == "dry_run"


def test_local_folders_are_refused_unless_allowed(copy_fixture):
    events = []
    result = run_agent(str(copy_fixture("fixture_multi")), emit=lambda t, p: events.append((t, p)))
    assert result.status == "error"


@pytest.mark.parametrize("fixture", ["fixture_simple", "fixture_multi"])
def test_demo_fixtures_are_still_broken(fixture, copy_fixture):
    """If someone 'fixes' a demo fixture, the demo stops demonstrating anything."""
    suite = LocalSandbox().run_tests(copy_fixture(fixture), "python -m pytest -q -p no:cacheprovider")
    assert suite.exit_code == 1
