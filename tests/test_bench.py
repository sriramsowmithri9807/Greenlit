"""The SWE-bench harness end to end on a tiny task in SWE-bench's format:
real git checkout by commit, real REPRODUCE/fix/verify loop (scripted
models), and real grading with the task's hidden tests."""
import json
import subprocess
from unittest.mock import patch

from conftest import FakePlanner, FakeTestWriter, LocalSandbox, fake_evaluator, fake_repro_judge, git, make_diff, plan

from greenlit import bench
from greenlit.locate import locate, nearby_tests

SOURCE = "def divide(a, b):\n    return a / b\n\n\ndef double(x):\n    return x * 2\n"
FIXED = SOURCE.replace("    return a / b", '    if b == 0:\n        raise ValueError("b must not be zero")\n    return a / b')
EXISTING_TEST = "from mathlib.ops import divide\n\n\ndef test_divide():\n    assert divide(6, 3) == 2\n"
HIDDEN_TEST_PATCH = """diff --git a/tests/test_hidden.py b/tests/test_hidden.py
new file mode 100644
--- /dev/null
+++ b/tests/test_hidden.py
@@ -0,0 +1,10 @@
+import pytest
+
+from mathlib.ops import divide
+
+
+def test_zero_raises():
+    with pytest.raises(ValueError):
+        divide(1, 0)
+def test_still_divides():
+    assert divide(9, 3) == 3
"""
PROBLEM = "divide() crashes with ZeroDivisionError when b is 0.\n\nCalling `divide(1, 0)` in mathlib.ops should raise a ValueError instead."
REPRO = "import pytest\n\nfrom mathlib.ops import divide\n\n\ndef test_divide_by_zero():\n    with pytest.raises(ValueError):\n        divide(1, 0)\n"


def _make_repo(tmp_path):
    repo = tmp_path / "upstream"
    (repo / "mathlib").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "mathlib" / "__init__.py").write_text("")
    (repo / "mathlib" / "ops.py").write_text(SOURCE)
    (repo / "mathlib" / "strings.py").write_text("def shout(s):\n    return s.upper()\n")
    (repo / "tests" / "test_ops.py").write_text(EXISTING_TEST)
    (repo / "conftest.py").write_text("")  # puts the repo root on sys.path for pytest
    git("init", "-q", "-b", "main", cwd=repo)
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "init", cwd=repo)
    # A later commit, so checking out by the base commit actually matters.
    (repo / "mathlib" / "ops.py").write_text(SOURCE + "\n# later\n")
    git("commit", "-qam", "later", cwd=repo)
    return repo, git("rev-parse", "HEAD~1", cwd=repo)


def _task(base):
    return bench.Task.from_row(
        {
            "instance_id": "octo__mathlib-1",
            "repo": "octo/mathlib",
            "base_commit": base,
            "problem_statement": PROBLEM,
            "test_patch": HIDDEN_TEST_PATCH,
            "FAIL_TO_PASS": json.dumps(["tests/test_hidden.py::test_zero_raises"]),
            "PASS_TO_PASS": json.dumps(["tests/test_hidden.py::test_still_divides", "tests/test_ops.py::test_divide"]),
        }
    )


def _bench(tmp_path, planner):
    repo, base = _make_repo(tmp_path)
    with (
        patch("greenlit.orchestrator.call_planner", planner),
        patch("greenlit.orchestrator.call_evaluator", fake_evaluator),
        patch("greenlit.orchestrator.call_test_writer", FakeTestWriter({"divide() crashes": [REPRO]})),
        patch("greenlit.orchestrator.call_repro_judge", fake_repro_judge),
    ):
        return bench.run_benchmark(
            [_task(base)],
            sandbox_factory=LocalSandbox,
            out_dir=tmp_path / "results",
            repo_url_for=lambda task: str(repo),
        )


def test_resolved_task_is_graded_by_the_hidden_tests(tmp_path):
    planner = FakePlanner({"divide() crashes": [plan(make_diff("mathlib/ops.py", SOURCE, FIXED))]})

    report = _bench(tmp_path, planner)

    (task,) = report["tasks"]
    assert task["error"] is None, task["detail"].get("traceback")
    assert task["resolved"] and task["claimed"] and task["proof"] == "reproduced"
    assert task["files_located"][0] == "mathlib/ops.py"
    assert task["detail"]["fail_to_pass"] == {"tests/test_hidden.py::test_zero_raises": "PASSED"}
    # Greenlit's own regression test is part of its patch.
    assert "tests/test_greenlit_swe_octo__mathlib_1.py" in task["detail"]["patch"]
    assert report["summary"]["resolve_rate"] == 1.0 and report["summary"]["false_fix_rate"] == 0.0
    assert (tmp_path / "results" / "latest.json").is_file()
    assert "| Resolved | 1 (100%) |" in (tmp_path / "results" / "REPORT.md").read_text()


def test_a_fix_that_fools_greenlit_but_not_the_hidden_tests_is_a_false_fix(tmp_path):
    # Passes Greenlit's repro test and the visible suite (6 / 3), but breaks a
    # case only the hidden PASS_TO_PASS test checks (9 / 3).
    sloppy = SOURCE.replace("    return a / b", '    if b == 0:\n        raise ValueError("zero")\n    return a / b if a < 9 else 0.0')
    planner = FakePlanner({"divide() crashes": [plan(make_diff("mathlib/ops.py", SOURCE, sloppy))]})

    report = _bench(tmp_path, planner)

    (task,) = report["tasks"]
    assert task["claimed"] and not task["resolved"]
    assert task["detail"]["pass_to_pass_failed"] == ["tests/test_hidden.py::test_still_divides"]
    assert report["summary"]["false_fixes"] == 1 and report["summary"]["false_fix_rate"] == 1.0


def test_unresolved_when_greenlit_cannot_fix(tmp_path):
    planner = FakePlanner({"divide() crashes": [plan("--- a/mathlib/ops.py\n+++ b/mathlib/ops.py\n@@ -1 +1 @@\n-nope\n+x\n")]})

    report = _bench(tmp_path, planner)

    (task,) = report["tasks"]
    assert task["status"] == "unresolved" and not task["resolved"] and not task["claimed"]
    assert report["summary"]["resolved"] == 0


def test_parse_results_and_bare_function_names():
    out = "PASSED tests/test_a.py::test_x\nFAILED tests/test_a.py::test_y - assert 1 == 2\nPASSED t.py::test_p[1]\n"
    results = bench.parse_results(out)
    assert results == {"tests/test_a.py::test_x": "PASSED", "tests/test_a.py::test_y": "FAILED", "t.py::test_p[1]": "PASSED"}
    assert bench._outcome(results, "test_y") == "FAILED"  # sympy-style ids
    assert bench._outcome(results, "test_missing") is None


def test_fetch_swe_bench_lite_pages_and_caches(tmp_path):
    pages = []

    def fake_get(url, params):
        pages.append(params["offset"])
        rows = [{"row": {"instance_id": f"x-{params['offset'] + i}"}} for i in range(100 if params["offset"] < 200 else 50)]
        return {"rows": rows, "num_rows_total": 250}

    cache = tmp_path / "lite.jsonl"
    rows = bench.fetch_swe_bench_lite(cache, fake_get)
    assert len(rows) == 250 and pages == [0, 100, 200]
    assert bench.fetch_swe_bench_lite(cache, lambda *a: (_ for _ in ()).throw(AssertionError("no network"))) == rows


def test_locate_ranks_the_defining_file_first(tmp_path):
    repo, _ = _make_repo(tmp_path)
    assert locate(repo, PROBLEM)[0] == "mathlib/ops.py"
    assert nearby_tests(repo, ["mathlib/ops.py"]) == ["tests/test_ops.py"]
