"""Find the source files a bug report is probably about.

A reported issue (a GitHub issue, a SWE-bench problem statement) names
functions, classes and modules but not a file and line. This ranks the
repo's non-test Python files by how many of the identifiers mentioned in the
report they define or use, with a strong bonus for files that *define* a
mentioned name (def/class) or whose path matches a mentioned module.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path, PurePosixPath

from greenlit.project import is_test_file
from greenlit.repo_files import iter_repo_files

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_DOTTED = re.compile(r"\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+\b")
# Words too common in prose or Python to say anything about location.
_STOP = {
    "the", "and", "for", "that", "this", "with", "not", "but", "are", "was", "when", "have", "has", "should",
    "would", "could", "from", "import", "return", "def", "class", "self", "none", "true", "false", "print",
    "error", "raise", "raises", "expected", "actual", "result", "test", "tests", "python", "version", "issue",
    "bug", "like", "also", "into", "than", "then", "there", "which", "what", "does", "doesn", "instead", "using",
    "used", "value", "values", "list", "dict", "str", "int", "float", "type", "object", "function", "method",
}
MAX_FILE_CHARS = 40_000


def mentioned_names(text: str) -> Counter:
    names = Counter(w for w in _IDENT.findall(text) if w.lower() not in _STOP)
    return names


def locate(repo_dir: Path, report: str, limit: int = 5) -> list[str]:
    names = mentioned_names(report)
    modules = {m for m in _DOTTED.findall(report)}
    if not names and not modules:
        return []
    scores: dict[str, float] = {}
    for path in iter_repo_files(repo_dir):
        if path.suffix != ".py":
            continue
        rel = path.relative_to(repo_dir).as_posix()
        if is_test_file(PurePosixPath(rel)):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if len(text) > MAX_FILE_CHARS * 4:
            continue
        score = 0.0
        for name, count in names.items():
            if re.search(rf"^\s*(?:def|class)\s+{re.escape(name)}\b", text, re.MULTILINE):
                score += 5.0 * count
            elif name in text:
                score += 0.3 * min(count, 3)
        dotted = rel[:-3].replace("/", ".")
        if any(dotted.endswith(m) or m.startswith(dotted) for m in modules):
            score += 8.0
        if score > 0:
            scores[rel] = score
    return [rel for rel, _ in sorted(scores.items(), key=lambda kv: (-kv[1], len(kv[0])))[:limit]]


def nearby_tests(repo_dir: Path, sources: list[str]) -> list[str]:
    """Test files that look like they cover `sources` (test_<module>.py
    anywhere in the repo): the regression scope for big repos where running
    the whole suite on every attempt is too slow."""
    stems = {PurePosixPath(s).stem for s in sources}
    found = []
    for path in iter_repo_files(repo_dir):
        rel = PurePosixPath(path.relative_to(repo_dir).as_posix())
        if rel.suffix == ".py" and rel.name.startswith("test_") and rel.stem[5:] in stems:
            found.append(rel.as_posix())
    return sorted(found)
