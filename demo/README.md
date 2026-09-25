# Demo fixtures

Deliberately broken repos, run via `python scripts/run_repo.py <dir>`:

1. `fixture_simple/` — one file, one bug (`NameError`), one failing test.
   Proves the single-issue PLAN→ACT→EVALUATE→retry loop.
2. `fixture_multi/` — one file, two independent bugs (`test_add`,
   `test_average` both fail; `test_divide` already passes). Proves the
   repo-wide worklist: `greenlit.orchestrator.run` discovers both failures
   up front, fixes them one at a time, and re-runs the whole suite after
   each accepted fix before moving on.

Still to add: a fixture that reliably triggers the Tavily research branch
against a real unfamiliar/version-sensitive external API (the branch
itself is control-flow tested in `scripts/test_orchestrator.py` with a
faked planner response, but not yet demonstrated end-to-end against a live
model, since there's no way to force a live model to flag `unfamiliar_api`
on demand).
