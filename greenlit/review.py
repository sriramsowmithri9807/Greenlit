"""REVIEW: Nemotron Ultra reads the repo's source for bugs no test catches.

Findings become GitHub issues on someone's real repository, so precision
matters more than recall here: only high-confidence, medium-or-worse
findings that point at a real file and line survive the filter below.
"""
from __future__ import annotations

from pathlib import Path

from greenlit.issues import Issue
from greenlit.llm_client import call_reviewer

MAX_REVIEW_FINDINGS = 5
_MAX_TOTAL_CHARS = 80_000
_SEVERITY_RANK = {"high": 0, "medium": 1}


def number_lines(text: str) -> str:
    return "\n".join(f"{i:>4} | {line}" for i, line in enumerate(text.splitlines(), start=1))


def _load_sources(repo_dir: Path, candidates: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}
    total = 0
    for rel in candidates:
        text = (repo_dir / rel).read_text(errors="replace")
        if total + len(text) > _MAX_TOTAL_CHARS:
            break
        sources[rel] = number_lines(text)
        total += len(text)
    return sources


def _is_credible(finding: dict, repo_dir: Path, reviewed: set[str]) -> bool:
    if finding.get("confidence") != "high" or finding.get("severity") not in _SEVERITY_RANK:
        return False
    rel = finding.get("file", "")
    if rel not in reviewed:
        return False
    line = finding.get("line")
    line_count = len((repo_dir / rel).read_text(errors="replace").splitlines())
    return isinstance(line, int) and 1 <= line <= line_count


def review(repo_dir: Path, candidates: list[str], known_failures: list[str]) -> tuple[list[Issue], int]:
    """Returns (credible issues, number of raw findings dropped by the filter)."""
    sources = _load_sources(repo_dir, candidates)
    if not sources:
        return [], 0

    raw = call_reviewer(sources, known_failures)
    credible = [f for f in raw if _is_credible(f, repo_dir, set(sources))]
    credible.sort(key=lambda f: _SEVERITY_RANK[f["severity"]])
    credible = credible[:MAX_REVIEW_FINDINGS]

    issues = [
        Issue(
            key=f"review:{i}",
            kind="review",
            title=f["title"].strip()[:120],
            file=f["file"],
            line=f["line"],
            severity=f["severity"],
            description=f["description"].strip(),
            evidence=f["evidence"].strip(),
        )
        for i, f in enumerate(credible, start=1)
    ]
    return issues, len(raw) - len(issues)
