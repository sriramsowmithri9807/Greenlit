"""CLI entry point for the full PERCEIVE-PLAN-ACT-EVALUATE retry loop,
run against the one-shot-fix fixture (demo/fixture_simple).

Usage:
    export NEBIUS_API_KEY=...
    export NEBIUS_AI_PROJECT=...
    python scripts/run_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenlit.orchestrator import run

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "demo" / "fixture_simple"
TEST_COMMAND = "pip install -q pytest >/dev/null && pytest -q"


def emit(event_type: str, payload: dict) -> None:
    print(f"[{event_type}] {payload}")


def main() -> int:
    result = run(FIXTURE_DIR, TEST_COMMAND, emit=emit)
    print()
    print(f"Result: {result.status} after {result.iterations} iteration(s)")
    if result.final_diff:
        print("Final diff:")
        print(result.final_diff)
    return 0 if result.status == "fixed" else 1


if __name__ == "__main__":
    sys.exit(main())
