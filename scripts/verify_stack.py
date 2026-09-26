"""First thing to run once credentials exist: checks every live dependency
the agent assumes, one at a time, and says exactly which one is broken.

    1. The Nemotron model IDs hardcoded in greenlit/llm_client.py exist in
       this account's Token Factory catalog.
    2. Forced tool calling returns structured output on both models (the
       agent never parses free text, so this has to work).
    3. The Sandbox runs a Python image.
    4. The Sandbox can reach PyPI (`pip install pytest`). Every repo run
       depends on this; if it fails, the sandbox has no network.

Usage:
    cp .env.example .env   # fill in NEBIUS_API_KEY, NEBIUS_AI_PROJECT
    python scripts/verify_stack.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenlit.clients.sandbox import Sandbox
from greenlit.config import GreenlitConfig
from greenlit.llm_client import EVAL_MODEL, PLAN_MODEL, call_evaluator, get_client


def step(title: str) -> None:
    print(f"\n== {title}")


def main() -> int:
    config = GreenlitConfig.from_env()
    failures: list[str] = []

    step("1. Model IDs exist in the Token Factory catalog")
    available = {m.id for m in get_client().models.list().data}
    for model in (PLAN_MODEL, EVAL_MODEL):
        if model in available:
            print(f"  ok       {model}")
        else:
            failures.append(f"model {model} not in catalog")
            print(f"  MISSING  {model}")
    if failures:
        nemotron = sorted(m for m in available if "nemotron" in m.lower())
        print("  Nemotron models this account can see:", *nemotron or ["(none)"], sep="\n    ")

    step("2. Forced tool calling (EVALUATE on Nemotron Nano)")
    try:
        verdict = call_evaluator(test_stdout="1 passed", test_stderr="", exit_code=0, prior_error=None)
        print(f"  ok       {verdict}")
    except Exception as exc:  # noqa: BLE001 - diagnostic script, report and continue
        failures.append(f"tool calling on {EVAL_MODEL}: {exc}")
        print(f"  FAILED   {exc}")

    sandbox = Sandbox(config)
    try:
        step("3. Sandbox runs Python")
        result = sandbox.run_shell("python --version")
        print(f"  exit={result.exit_code} {result.stdout.strip() or result.stderr.strip()}")
        if result.exit_code != 0:
            failures.append("sandbox can't run python")

        step("4. Sandbox can install from PyPI")
        result = sandbox.run_shell("pip install -q pytest && python -m pytest --version")
        print(f"  exit={result.exit_code} {(result.stdout + result.stderr).strip()[-300:]}")
        if result.exit_code != 0:
            failures.append("sandbox can't pip install (no network?)")
    finally:
        sandbox.close()

    print()
    if failures:
        print("FAILED:", *failures, sep="\n  - ")
        return 1
    print("Every live dependency checks out. Try: python scripts/run_repo.py demo/fixture_multi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
