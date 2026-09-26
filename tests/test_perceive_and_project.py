"""Parsing real pytest output (not hand-written strings), and project
detection. Output format drift in pytest would break these first."""
import sys

import pytest
from conftest import LocalSandbox

from greenlit.perceive import failure_section, parse_suite_output, run_suite, touched_files
from greenlit.project import TEST_COMMAND, UnsupportedProject, detect, is_test_file


def _run(repo):
    return run_suite(LocalSandbox(), repo, TEST_COMMAND)


def test_suite_run_finds_each_failure_on_real_pytest_output(copy_fixture):
    repo = copy_fixture("fixture_multi")
    suite = _run(repo)
    assert suite.ran and not suite.no_tests
    assert [f.test_id for f in suite.failures] == [
        "test_calculator.py::test_add",
        "test_calculator.py::test_average",
    ]
    assert suite.failures[0].reason == "assert -1 == 5"
    assert suite.env_errors == []


def test_failure_section_extracts_one_test(copy_fixture):
    suite = _run(copy_fixture("fixture_multi"))
    section = failure_section(suite.output, "test_calculator.py::test_add")
    assert "assert add(2, 3) == 5" in section
    assert "average" not in section


def test_touched_files_reads_pytest_style_locations(copy_fixture):
    repo = copy_fixture("fixture_simple")
    suite = _run(repo)
    assert set(touched_files(suite.output, repo)) == {"app.py", "test_app.py"}


def test_missing_third_party_module_is_an_environment_problem_not_a_bug(tmp_path):
    (tmp_path / "test_needs_dep.py").write_text("import surely_not_installed_pkg\n\ndef test_x():\n    pass\n")
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    suite = _run(tmp_path)
    assert suite.failures == []
    assert [e.test_id for e in suite.env_errors] == ["test_needs_dep.py"]


def test_syntax_error_in_a_module_is_a_real_failure(tmp_path):
    (tmp_path / "broken.py").write_text("def f(:\n    pass\n")
    (tmp_path / "test_broken.py").write_text("from broken import f\n\ndef test_f():\n    f()\n")
    suite = _run(tmp_path)
    assert [f.test_id for f in suite.failures] == ["test_broken.py"]


def test_no_tests_and_did_not_run_are_distinguished(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    assert _run(tmp_path).no_tests
    assert not parse_suite_output(1, "ERROR: Could not find a version that satisfies the requirement nope").ran


def test_detect_builds_install_command_and_review_candidates(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text("def f():\n    return 1\n" * 5)
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_core.py").write_text("def test_f():\n    pass\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "junk.py").write_text("x = 1\n")

    setup = detect(tmp_path)
    assert "pip install -q -r requirements.txt" in setup.install_command
    assert "pip install -q -e ." in setup.install_command
    assert setup.review_candidates == ["pkg/core.py"]


def test_detect_rejects_non_python_repos(tmp_path):
    (tmp_path / "index.js").write_text("console.log(1)\n")
    with pytest.raises(UnsupportedProject):
        detect(tmp_path)


@pytest.mark.parametrize(
    "path,expected",
    [("test_x.py", True), ("x_test.py", True), ("tests/helpers.py", True), ("conftest.py", True), ("src/app.py", False)],
)
def test_is_test_file(path, expected):
    from pathlib import PurePosixPath

    assert is_test_file(PurePosixPath(path)) is expected


def test_local_sandbox_uses_this_interpreter():
    assert "python -m pytest" in TEST_COMMAND and sys.executable
