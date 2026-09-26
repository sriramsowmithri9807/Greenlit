"""Work out how to install and test an arbitrary cloned Python repo, and
which files are worth sending to the code reviewer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePath

from greenlit.repo_files import iter_repo_files

# pytest runs via `python -m` so the repo root is on sys.path (flat-layout
# repos where tests do `from app import ...` then just work), keeps going
# past a broken test file so one import error doesn't hide every other
# failure, and doesn't try to write a cache dir into the sandbox.
TEST_COMMAND = "python -m pytest -q --continue-on-collection-errors -p no:cacheprovider"

_REQUIREMENTS_FILES = ("requirements.txt", "requirements-dev.txt", "dev-requirements.txt")
_PACKAGE_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")

MAX_REVIEW_FILES = 12
MAX_REVIEW_FILE_CHARS = 20_000


class UnsupportedProject(Exception):
    pass


@dataclass
class ProjectSetup:
    install_command: str
    test_command: str
    review_candidates: list[str]  # repo-relative paths, most substantial first


def is_test_file(rel: PurePath) -> bool:
    name = rel.name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or any(part in ("tests", "test") for part in rel.parts[:-1])
    )


def detect(repo_dir: Path) -> ProjectSetup:
    py_files = [p for p in iter_repo_files(repo_dir) if p.suffix == ".py"]
    if not py_files:
        raise UnsupportedProject(
            "No Python files found. Greenlit currently supports Python projects tested with pytest."
        )

    steps = [
        "export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore",
        "pip install -q pytest",
    ]
    for name in _REQUIREMENTS_FILES:
        if (repo_dir / name).is_file():
            steps.append(f"pip install -q -r {name}")
    if any((repo_dir / marker).is_file() for marker in _PACKAGE_MARKERS):
        # Not every repo with a pyproject is installable; a failed install
        # shows up as ModuleNotFoundError at collection time, which the
        # orchestrator reports as an environment problem rather than a bug.
        steps.append("(pip install -q -e . || true)")

    candidates = [
        p
        for p in py_files
        if not is_test_file(p.relative_to(repo_dir))
        and p.name not in ("setup.py", "__init__.py")
        and 0 < p.stat().st_size <= MAX_REVIEW_FILE_CHARS
    ]
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)

    return ProjectSetup(
        install_command=" && ".join(steps),
        test_command=TEST_COMMAND,
        review_candidates=[p.relative_to(repo_dir).as_posix() for p in candidates[:MAX_REVIEW_FILES]],
    )
