"""The code-review filter: findings become issues on real repos, so anything
not high-confidence, too minor, or pointing at a line that doesn't exist
must be dropped."""
from unittest.mock import patch

from greenlit.review import number_lines, review


def _finding(**overrides):
    base = {
        "title": "average adds 1 to the result",
        "file": "calc.py",
        "line": 2,
        "severity": "high",
        "confidence": "high",
        "description": "average([1, 2, 3]) returns 3.0 instead of 2.0",
        "evidence": "return sum(xs) / len(xs) + 1",
    }
    return {**base, **overrides}


def test_only_credible_findings_become_issues(tmp_path):
    (tmp_path / "calc.py").write_text("def average(xs):\n    return sum(xs) / len(xs) + 1\n")
    raw = [
        _finding(),
        _finding(title="maybe slow", confidence="medium"),
        _finding(title="naming", severity="low"),
        _finding(title="hallucinated line", line=99),
        _finding(title="file it never saw", file="other.py"),
    ]
    with patch("greenlit.review.call_reviewer", return_value=raw) as reviewer:
        issues, dropped = review(tmp_path, ["calc.py"], known_failures=["test_x: boom"])

    assert [i.title for i in issues] == ["average adds 1 to the result"]
    assert dropped == 4
    assert issues[0].key == "review:1" and issues[0].location == "calc.py:2"
    sources, known = reviewer.call_args.args
    assert sources["calc.py"].startswith("   1 | def average")
    assert known == ["test_x: boom"]


def test_high_severity_sorts_first_and_output_is_capped(tmp_path):
    (tmp_path / "calc.py").write_text("x = 1\n" * 10)
    raw = [_finding(title=f"medium {i}", severity="medium", line=1) for i in range(6)]
    raw.append(_finding(title="the high one", line=1))
    with patch("greenlit.review.call_reviewer", return_value=raw):
        issues, _ = review(tmp_path, ["calc.py"], known_failures=[])
    assert issues[0].title == "the high one"
    assert len(issues) == 5


def test_number_lines():
    assert number_lines("a\nb") == "   1 | a\n   2 | b"
