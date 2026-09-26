"""Applying model-written diffs: the shapes LLMs actually produce, and the
paths a malicious repo could try to trick the planner into writing."""
import pytest

from greenlit.orchestrator import DiffError, apply_diff, diff_paths

CALC = (
    "def add(a, b):\n    return a - b\n\n\n"
    "def divide(a, b):\n    return a / b\n\n\n"
    "def average(xs):\n    return sum(xs) / len(xs) + 1\n"
)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "calc.py").write_text(CALC)
    return tmp_path


def test_truncated_hunk_with_wrong_line_counts_applies(repo):
    diff = "--- a/calc.py\n+++ b/calc.py\n@@ -1,9 +1,9 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
    assert apply_diff(repo, diff) == ["calc.py"]
    assert "return a + b" in (repo / "calc.py").read_text()


def test_misquoted_context_line_still_applies(repo):
    diff = (
        "--- a/calc.py\n+++ b/calc.py\n@@ -8,4 +8,4 @@\n \n def average(numbers):\n"
        "-    return sum(xs) / len(xs) + 1\n+    return sum(xs) / len(xs)\n"
    )
    apply_diff(repo, diff)
    assert (repo / "calc.py").read_text().endswith("return sum(xs) / len(xs)\n")


def test_new_file(repo):
    diff = "--- /dev/null\n+++ b/helpers.py\n@@ -0,0 +1,2 @@\n+def helper():\n+    return 1\n"
    assert apply_diff(repo, diff) == ["helpers.py"]
    assert (repo / "helpers.py").exists()


def test_removed_lines_must_match_exactly(repo):
    diff = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a * b\n+    return a + b\n"
    with pytest.raises(DiffError, match="did not apply"):
        apply_diff(repo, diff)
    assert (repo / "calc.py").read_text() == CALC


def test_failed_apply_is_atomic_and_leaves_no_backup_files(repo):
    diff = (
        "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
        "--- a/missing.py\n+++ b/missing.py\n@@ -1 +1 @@\n-x\n+y\n"
    )
    with pytest.raises(DiffError):
        apply_diff(repo, diff)
    assert (repo / "calc.py").read_text() == CALC
    assert sorted(p.name for p in repo.iterdir()) == ["calc.py"]


@pytest.mark.parametrize(
    "path",
    ["../outside.py", "/etc/passwd", ".git/config", "pkg/../../outside.py"],
)
def test_unsafe_paths_are_refused(repo, path):
    diff = f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+pwned = True\n"
    with pytest.raises(DiffError, match="refusing"):
        apply_diff(repo, diff)


def test_symlink_escape_is_refused(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (repo / "link").symlink_to(outside)
    diff = "--- /dev/null\n+++ b/link/evil.py\n@@ -0,0 +1 @@\n+pwned = True\n"
    with pytest.raises(DiffError, match="outside the repo"):
        apply_diff(repo, diff)
    assert not (outside / "evil.py").exists()


def test_garbage_is_a_diff_error_not_a_crash(repo):
    with pytest.raises(DiffError, match="no file headers"):
        apply_diff(repo, "I think you should change line 2 to use +")


def test_diff_paths_strips_prefixes_and_dev_null():
    diff = "--- /dev/null\n+++ b/new.py\n--- a/old.py\t2026-01-01\n+++ b/old.py\t2026-01-01\n"
    assert diff_paths(diff) == ["new.py", "old.py"]
