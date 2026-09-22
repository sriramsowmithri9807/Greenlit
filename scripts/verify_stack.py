"""Build-order step 1: prove the required stack is reachable before writing
any orchestration logic. Makes one raw call to the PLAN-tier model, one to
the EVALUATE-tier model, and one sandbox code-execution call.

Usage:
    cp .env.example .env   # fill in NEBIUS_API_KEY, NEBIUS_AI_PROJECT
    pip install -r requirements.txt
    python scripts/verify_stack.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenlit.clients.nebius import NebiusClient
from greenlit.clients.sandbox import Sandbox
from greenlit.config import GreenlitConfig


def main() -> int:
    config = GreenlitConfig.from_env()
    nebius = NebiusClient(config)

    print("== Resolving live Nemotron model IDs from GET /v1/models ==")
    plan_model = nebius.resolve_model(*config.plan_model_keywords)
    eval_model = nebius.resolve_model(*config.eval_model_keywords)
    print(f"PLAN model (expensive reasoning): {plan_model}")
    print(f"EVALUATE model (fast/cheap):       {eval_model}")

    print("\n== Calling PLAN-tier model ==")
    plan_resp = nebius.chat(
        plan_model,
        [{"role": "user", "content": "Reply with exactly: PLAN_OK"}],
        max_tokens=16,
    )
    print(plan_resp.choices[0].message.content)

    print("\n== Calling EVALUATE-tier model ==")
    eval_resp = nebius.chat(
        eval_model,
        [{"role": "user", "content": "Reply with exactly: EVAL_OK"}],
        max_tokens=16,
    )
    print(eval_resp.choices[0].message.content)

    print("\n== Calling Sandbox ==")
    sandbox = Sandbox(config)
    result = sandbox.run_shell("echo SANDBOX_OK")
    print(f"stdout={result.stdout!r} exit_code={result.exit_code}")
    sandbox.close()

    print("\nAll three required-stack calls succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
