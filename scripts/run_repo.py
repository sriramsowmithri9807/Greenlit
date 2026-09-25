"""CLI entry point: point Greenlit at any repo and fix every failing test.

Runs the repo-wide agent (greenlit.orchestrator.run): discovers every
currently-failing test, fixes them one at a time via Nemotron, verifying
each fix inside a Sandbox before moving to the next issue.

Usage:
    export NEBIUS_API_KEY=...
    export NEBIUS_AI_PROJECT=...
    python scripts/run_repo.py [repo_dir] [--install "pip install -q -r requirements.txt"] [--test "pytest -q"]

With no repo_dir, defaults to demo/fixture_simple.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenlit.orchestrator import DEFAULT_MAX_ISSUES, DEFAULT_MAX_ITERATIONS_PER_ISSUE, run

DEFAULT_FIXTURE = Path(__file__).resolve().parent.parent / "demo" / "fixture_simple"


def emit(event_type: str, payload: dict) -> None:
    print(f"[{event_type}] {payload}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to the repo to fix (default: demo/fixture_simple)",
    )
    parser.add_argument(
        "--install",
        default=None,
        help='Setup command to run before each test invocation, e.g. "pip install -q -r requirements.txt"',
    )
    parser.add_argument("--test", default="pytest -q", help='Base test command (default: "pytest -q")')
    parser.add_argument("--max-issues", type=int, default=DEFAULT_MAX_ISSUES)
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS_PER_ISSUE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(
        args.repo_dir.resolve(),
        install_command=args.install,
        test_command=args.test,
        max_issues=args.max_issues,
        max_iterations_per_issue=args.max_iterations,
        emit=emit,
    )

    print()
    print(f"Result: {result.status}")
    print(f"Fixed ({len(result.fixed_issues)}): {', '.join(result.fixed_issues) or '(none)'}")
    print(f"Unresolved ({len(result.unresolved_issues)}): {', '.join(result.unresolved_issues) or '(none)'}")
    print(f"Patched copy left at: {result.working_dir}")
    return 0 if result.status == "fixed" else 1


if __name__ == "__main__":
    sys.exit(main())
