# Greenlit

Autonomous test-fix-verify agent. The moment a test suite goes red, Greenlit
diagnoses the failure, writes a fix, verifies it by re-running the tests
inside an isolated sandbox, and iterates until the suite passes — or reports
exactly what it tried and why it's stuck. No PR, no GitHub/GitLab
integration, no human in the loop until it's done.

Built for the Nebius x NVIDIA Global AI Hackathon (Coding & Agentic
Engineering track).

> Status: early scaffold. This README covers setup for build-order step 1
> (confirming stack access). The full judging-oriented writeup — model
> tiering rationale, sandbox usage, conditional Tavily usage mapped to the
> judging criteria — lands in week 4.

## Required stack

- **Nebius Token Factory** — OpenAI-compatible inference API
  (`https://api.tokenfactory.nebius.com/v1/`) serving open NVIDIA **Nemotron**
  models, tiered by cost/latency:
  - **PLAN** (root-cause reasoning + patch proposal): Nemotron Ultra
  - **EVALUATE** (parse test output, classify pass/fail/retry): Nemotron Nano/Super
  - Model IDs are *resolved live* against `GET /v1/models`
    ([greenlit/clients/nebius.py](greenlit/clients/nebius.py)) rather than
    hardcoded — see that file's docstring for why.
- **Nebius Token Factory Sandboxes** (SDK package `contree-sdk`, branded
  ConTree) — every target-repo test run happens inside an isolated
  sandbox/microVM, never on the host. See
  [greenlit/clients/sandbox.py](greenlit/clients/sandbox.py).
- **Tavily** — called conditionally, only when the PLAN step flags the
  failure as involving an unfamiliar/version-sensitive external library.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in NEBIUS_API_KEY and NEBIUS_AI_PROJECT
```

## Step 1: verify stack access

Before any orchestration logic is built, prove the three required-stack
calls actually work:

```bash
python scripts/verify_stack.py
```

This resolves live PLAN/EVALUATE model IDs, makes one chat completion call
to each tier, and runs one command inside a Sandbox — printing what it did
at each step.

## License

MIT — see [LICENSE](LICENSE).
