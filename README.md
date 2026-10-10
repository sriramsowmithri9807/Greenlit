# Greenlit

Paste a GitHub repo URL. Greenlit finds the bugs, writes a fix for each,
proves every fix by running the repo's tests in an isolated sandbox, and shows
you exactly what it changed: every file, line number and line of code. Then it
asks you. Only when you say yes does it file the bugs as GitHub issues and
open a pull request that closes the ones it fixed.

Built for the Nebius x NVIDIA Global AI Hackathon (Coding & Agentic
Engineering track).

```
repo URL ─► clone ─► scan ──────────► issues ─► fix, in parallel ─────────────► merge ──► review ───────► publish
                     ├ test suite              one Nebius sandbox per issue:   combine,  files, lines,  (only on yes)
                     │ (Nebius sandbox)        PERCEIVE → PROVE BUG → PLAN     re-verify code; ask to   issues, commits,
                     └ code review             → [RESEARCH] → ACT → EVALUATE   the suite raise the PR   push, PR
                       (Nemotron 3 Ultra)      → retry
```

Three things set it apart:

- **Proven bugs, not guesses.** A bug found by AI code review isn't fixed on
  the model's say-so. Nemotron Ultra first writes a test that reproduces it,
  which must fail on the current code in the sandbox, and Nemotron Nano checks
  it fails *because of the bug* (not an import error in the test). Then the
  fix must make that test pass, and the test ships in the PR so the bug can't
  come back. A finding whose tests keep passing on today's code is dropped as
  a false positive and never raised.
- **Parallel sandboxes.** Every issue is fixed at the same time in its own
  Nebius sandbox. The verified fixes are merged and the whole suite re-run on
  the result. Fixes that conflict or interact are merged one at a time instead,
  and re-fixed on top of each other if needed.
- **Visible cost tiering.** Every Nemotron call is metered. The dashboard shows
  spend per model and per issue, live, and how much routing the frequent
  checks to Nano saved compared with running everything on Ultra.

## What makes a fix "verified"

A proposed diff is applied to a throwaway copy and run in a Nebius Token
Factory sandbox. It's only committed if:

- it applies cleanly and only touches paths inside the repo,
- every test run it's judged on actually finished: a run that times out
  (each is capped, `GREENLIT_TEST_TIMEOUT`, default 600 s), crashes, or ends the
  process before pytest reports its results counts as a failure, never as
  "no failures",
- it doesn't edit test files: Greenlit fixes the code under test, and never
  weakens a test to make it pass,
- for a failing-test issue, that test now passes, **and** the full suite has no
  failure that wasn't there before,
- for a code-review issue, it edits the reported file, the reproduction test
  written for it now passes, and the full suite has no new failures. (If no
  working reproduction test could be written, the fix must compile and break
  nothing, and the PR flags it for a closer look.)

A diff that fails any check goes back to the planner as a failed attempt, with
the reason, so the next attempt is different. After the retry budget, the
issue gets a comment explaining what was tried.

## Required stack, and where each piece is used

| Requirement | Where |
|---|---|
| **NVIDIA Nemotron via Nebius Token Factory**, tiered by cost | [greenlit/llm_client.py](greenlit/llm_client.py) |
| Nemotron 3 Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`) for the expensive reasoning: code review, writing reproduction tests, fix planning | `call_reviewer`, `call_test_writer`, `call_planner` |
| Nemotron 3 Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`) for the cheap, frequent calls: classifying each sandbox test run, judging reproduction tests | `call_evaluator`, `call_repro_judge` |
| Per-call token and cost metering, split by tier | [greenlit/usage.py](greenlit/usage.py) |
| Structured output via forced tool calling on both models (no free-text parsing) | same file |
| **Token Factory Sandboxes**: every run of the target repo's code happens in a sandbox, never on the host; issues are fixed in parallel, one sandbox each | [greenlit/clients/sandbox.py](greenlit/clients/sandbox.py), [greenlit/parallel.py](greenlit/parallel.py) |
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
- **URL + token**: the full run. Once every fix is verified, the run pauses
  on a change report (each fix's files, changed line numbers, and the removed
  and added code) and asks **Raise pull request?** Nothing has touched GitHub
  at that point. On yes, the issues are raised, each fix is pushed as its own
  commit to a new `greenlit/fix-*` branch, and a pull request is opened. On
  no, or with no answer within 30 minutes, nothing is written. Nothing is ever
  pushed to the default branch. Use a
  [fine-grained token](https://github.com/settings/personal-access-tokens/new)
  for that repo with Contents, Issues and Pull requests set to Read and write.

CLI equivalent:
`python scripts/run_repo.py https://github.com/owner/repo [--live]`. It prints
the same change report in the terminal, then asks `Raise the pull request on
owner/repo? [y/N]`. Pass `--yes` to skip the question. Without a terminal to ask
on, it doesn't publish. It also takes a local folder, for example
`python scripts/run_repo.py demo/fixture_multi`.

Options: `--sequential` fixes one issue at a time in a single sandbox (the UI
has the same switch); `GREENLIT_MAX_SANDBOXES` caps parallel sandboxes
(default 4); `GREENLIT_TEST_TIMEOUT` caps each test run in the sandbox
(seconds, default 600).

**Demo without credentials:** run the dashboard with `npm run dev` and open
`http://localhost:5173/?mock=1` (or `?mock=partial`). This plays a scripted run
and is labelled as such in the UI.

Supported: Python repos tested with pytest.

## Cost

Costs are estimated from per-token prices: by default Ultra $1.00 in / $3.00
out and Nano $0.06 / $0.24 per million tokens, taken from public price
listings rather than Nebius's own page. Confirm them in your Token Factory
console and override with `GREENLIT_PRICE_ULTRA="<in>,<out>"` and
`GREENLIT_PRICE_NANO`. The UI marks every figure "est.".

## Benchmark

```bash
python scripts/benchmark.py --limit 25
```

Runs Greenlit on SWE-bench Lite tasks (by default from requests, pytest,
sympy, flask and pylint). Greenlit sees only each task's problem statement,
like a maintainer reading a GitHub issue. It locates the code, proves the bug
with a test, then fixes and verifies it. Its patch is then graded with
SWE-bench's hidden tests. The report gives the resolve rate, the false-fix
rate (fixes Greenlit claimed that the hidden tests reject), and time and cost
per task. It's written to `bench/results/` (`REPORT.md`, `latest.json`), and
the dashboard's start page shows the latest result. No result is shown until
a real run has produced one.

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

120 tests. The engine, agent and benchmark tests run real pytest (on Greenlit's own demo
fixtures), apply real diffs, and push real commits into a local bare git repo
that stands in for GitHub. Only the Nemotron calls and GitHub's REST API are
scripted. `demo/` holds the deliberately broken fixtures and is excluded from
collection.

## Status

Everything above is tested offline. It has **not** yet been run against live
Nemotron models or a live Nebius sandbox, and the benchmark has no results
yet: `scripts/verify_stack.py` is the first thing to run once credentials are
available. The open questions it answers are whether the model IDs above exist
in the account's catalog and whether the sandbox has network access for
`pip install`.

## License

MIT, see [LICENSE](LICENSE).
