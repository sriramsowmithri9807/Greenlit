# Greenlit

Paste a GitHub repo URL. Greenlit finds the bugs, files each one as a GitHub
issue, writes a fix for each, proves every fix by running the repo's tests in
an isolated sandbox, and opens a pull request that closes the issues it fixed.

Built for the Nebius x NVIDIA Global AI Hackathon (Coding & Agentic
Engineering track).

```
repo URL ─► clone ─► scan ─────────────► raise issues ─► fix each issue ───────────────► commit + PR
                     ├ test suite            (GitHub)    PERCEIVE → PLAN → [RESEARCH]
                     │ (Nebius sandbox)                  → ACT → EVALUATE → retry
                     └ code review
                       (Nemotron 3 Ultra)
```

## What makes a fix "verified"

A proposed diff is applied to a throwaway copy and run in a Nebius Token
Factory sandbox. It's only committed if:

- it applies cleanly and only touches paths inside the repo,
- it doesn't edit test files: Greenlit fixes the code under test, and never
  weakens a test to make it pass,
- for a failing-test issue, that test now passes, **and** the full suite has no
  failure that wasn't there before,
- for a code-review issue, it edits the reported file, compiles, and the full
  suite has no new failures.

A diff that fails any check goes back to the planner as a failed attempt, with
the reason, so the next attempt is different. After the retry budget, the
issue gets a comment explaining what was tried.

## Required stack, and where each piece is used

| Requirement | Where |
|---|---|
| **NVIDIA Nemotron via Nebius Token Factory**, tiered by cost | [greenlit/llm_client.py](greenlit/llm_client.py) |
| Nemotron 3 Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`) for the expensive reasoning: code review and fix planning | `call_reviewer`, `call_planner` |
| Nemotron 3 Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) for the cheap, frequent call: classifying each sandbox test run | `call_evaluator` |
| Structured output via forced tool calling on both models (no free-text parsing) | same file |
| **Token Factory Sandboxes**: every run of the target repo's code happens in a sandbox, never on the host | [greenlit/clients/sandbox.py](greenlit/clients/sandbox.py) |
| **Tavily**, called only when the planner flags an unfamiliar or version-sensitive API, then planning re-runs with the docs | [greenlit/research.py](greenlit/research.py), `FixEngine._plan` |

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # NEBIUS_API_KEY, NEBIUS_AI_PROJECT (+ TAVILY_API_KEY, optional)
python scripts/verify_stack.py    # checks model IDs, tool calling, sandbox, sandbox network

cd dashboard && npm install && npm run build && cd ..
python -m greenlit.server         # open http://127.0.0.1:8000
```

In the UI, paste a repo URL:

- **URL only**: a read-only dry run. Issues are found and fixes verified, and
  the combined diff is shown. Nothing is written to GitHub.
- **URL + token**: the full run. Issues are raised on the repo, each fix is
  pushed as its own commit to a new `greenlit/fix-*` branch, and a pull request
  is opened. Nothing is ever pushed to the default branch. Use a
  [fine-grained token](https://github.com/settings/personal-access-tokens/new)
  for that repo with Contents, Issues and Pull requests set to Read and write.

CLI equivalent:
`python scripts/run_repo.py https://github.com/owner/repo [--live]`. It also
takes a local folder, for example `python scripts/run_repo.py demo/fixture_multi`.

**Demo without credentials:** run the dashboard with `npm run dev` and open
`http://localhost:5173/?mock=1` (or `?mock=partial`). This plays a scripted run
and is labelled as such in the UI.

Supported: Python repos tested with pytest.

## Safety

- The user's token is used for the run only and never written to disk. Git
  receives it as a per-command auth header, not in the remote URL or
  `.git/config`, and it's scrubbed from every error message. Git runs with the
  host's global config and credential helpers disabled, so a rejected token
  can't fall back to credentials stored on the server.
- Repo hooks are disabled for every git command, since the clone is untrusted.
- Model-written diffs are path-checked: absolute paths, `..`, `.git/` and
  symlink escapes are all refused.
- The web API only accepts github.com repos, never local paths.

## Tests

```bash
python -m pytest
```

76 tests. The engine and agent tests run real pytest (on Greenlit's own demo
fixtures), apply real diffs, and push real commits into a local bare git repo
that stands in for GitHub. Only the Nemotron calls and GitHub's REST API are
scripted. `demo/` holds the deliberately broken fixtures and is excluded from
collection.

## Status

Everything above is tested offline. It has **not** yet been run against live
Nemotron models or a live Nebius sandbox: `scripts/verify_stack.py` is the
first thing to run once credentials are available. The open questions it
answers are whether the model IDs above exist in the account's catalog and
whether the sandbox has network access for `pip install`.

## License

MIT, see [LICENSE](LICENSE).
