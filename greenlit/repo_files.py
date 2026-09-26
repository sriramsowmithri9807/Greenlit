"""Walking a cloned repo's files while skipping VCS metadata, virtualenvs,
build output and caches."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "build",
        "dist",
        "site-packages",
    }
)


def iter_repo_files(repo_dir: Path) -> Iterator[Path]:
    for path in repo_dir.rglob("*"):
        rel_parts = path.relative_to(repo_dir).parts
        if any(part in IGNORED_DIRS or part.endswith(".egg-info") for part in rel_parts):
            continue
        if path.is_file() and not path.is_symlink():
            yield path
