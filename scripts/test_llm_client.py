"""Smoke test for greenlit/llm_client.py — run this once to confirm both
Nemotron tiers + auth are working before building anything else on top.

Usage:
    export NEBIUS_API_KEY=...   # or put it in .env and `source` it
    python scripts/test_llm_client.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenlit.llm_client import call_evaluator, call_planner

FAKE_ERROR_CONTEXT = {
    "stack_trace": (
        "Traceback (most recent call last):\n"
        '  File "app.py", line 3, in <module>\n'
        "    print(greeting)\n"
        "NameError: name 'greeting' is not defined"
    ),
    "source_files": {
        "app.py": "def main():\n    print(greeting)\n\nmain()\n",
    },
}

FAKE_PASS = {
    "test_stdout": "3 passed in 0.12s",
    "test_stderr": "",
    "exit_code": 0,
    "prior_error": "NameError: name 'greeting' is not defined",
}

FAKE_FAIL_SAME = {
    "test_stdout": "",
    "test_stderr": (
        "Traceback (most recent call last):\n"
        '  File "app.py", line 3, in <module>\n'
        "    print(greeting)\n"
        "NameError: name 'greeting' is not defined"
    ),
    "exit_code": 1,
    "prior_error": "NameError: name 'greeting' is not defined",
}


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    print("== call_planner (fake NameError) ==")
    plan_result = call_planner(FAKE_ERROR_CONTEXT)
    print(plan_result)
    _check(isinstance(plan_result, dict), "call_planner did not return a dict")
    for key in ("diff", "rationale", "unfamiliar_api", "unfamiliar_api_query"):
        _check(key in plan_result, f"call_planner result missing key {key!r}")
    _check(isinstance(plan_result["unfamiliar_api"], bool), "unfamiliar_api is not a bool")

    print("\n== call_evaluator (fake PASS) ==")
    pass_result = call_evaluator(**FAKE_PASS)
    print(pass_result)
    _check(pass_result.get("status") == "PASS", f"expected PASS, got {pass_result.get('status')!r}")

    print("\n== call_evaluator (fake FAIL, same error as prior_error) ==")
    fail_result = call_evaluator(**FAKE_FAIL_SAME)
    print(fail_result)
    _check(
        fail_result.get("status") in ("FAIL_SAME_ERROR", "FAIL_NEW_ERROR"),
        f"unexpected status {fail_result.get('status')!r}",
    )

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - top-level smoke test, want a readable message
        print(f"\nSMOKE TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
