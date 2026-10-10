"""Benchmark Greenlit on SWE-bench Lite (or any tasks in the same format).

The setting is the honest one: Greenlit sees only the problem statement,
like a maintainer reading a GitHub issue. It locates the code, writes a test
that reproduces the bug (REPRODUCE), fixes it and verifies the fix in the
sandbox. Only afterwards are SWE-bench's own hidden tests (the task's
`test_patch`) applied on top of Greenlit's patch, and the task counts as
resolved only if every FAIL_TO_PASS test now passes and every PASS_TO_PASS
test still does.

Reported per task: resolved, whether Greenlit *claimed* a fix (so the
false-fix rate, claimed but not resolved, is visible), proof status,
attempts, wall time and model cost (from greenlit.usage).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from greenlit import usage
from greenlit.clients.sandbox import Sandbox
from greenlit.issues import Issue
from greenlit.locate import locate, nearby_tests
from greenlit.orchestrator import DEFAULT_MAX_ITERATIONS, FixEngine, test_timeout_from_env
from greenlit.project import detect

SWE_BENCH_LITE = "princeton-nlp/SWE-bench_Lite"
_ROWS_API = "https://datasets-server.huggingface.co/rows"
# Repos in SWE-bench Lite that are plain pytest projects installable with
# `pip install -e .` on a recent Python: the default subset.
DEFAULT_REPOS = ("psf/requests", "pytest-dev/pytest", "sympy/sympy", "pallets/flask", "pylint-dev/pylint")
EVAL_COMMAND = "python -m pytest -p no:cacheprovider -rA -q"
_RESULT_LINE = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(\S+)", re.MULTILINE)
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


# --- tasks -------------------------------------------------------------------


@dataclass
class Task:
    instance_id: str
    repo: str  # owner/name
    base_commit: str
    problem_statement: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]

    @classmethod
    def from_row(cls, row: dict) -> Task:
        def ids(value) -> list[str]:
            return json.loads(value) if isinstance(value, str) else list(value or [])

        return cls(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            problem_statement=row["problem_statement"],
            test_patch=row["test_patch"],
            fail_to_pass=ids(row["FAIL_TO_PASS"]),
            pass_to_pass=ids(row["PASS_TO_PASS"]),
        )


def fetch_swe_bench_lite(cache: Path, http_get: Callable[[str, dict], dict] | None = None) -> list[dict]:
    """All SWE-bench Lite test rows, from Hugging Face's datasets server,
    cached as JSONL after the first download."""
    if cache.is_file():
        return [json.loads(line) for line in cache.read_text().splitlines() if line.strip()]
    if http_get is None:
        import httpx

        def http_get(url: str, params: dict) -> dict:
            response = httpx.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()

    rows: list[dict] = []
    while True:
        page = http_get(
            _ROWS_API,
            {"dataset": SWE_BENCH_LITE, "config": "default", "split": "test", "offset": len(rows), "length": 100},
        )
        batch = [item["row"] for item in page.get("rows", [])]
        rows += batch
        if not batch or len(rows) >= page.get("num_rows_total", len(rows)):
            break
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return rows


def select(rows: list[dict], *, repos: tuple[str, ...] | None, ids: list[str] | None, limit: int | None) -> list[Task]:
    tasks = [Task.from_row(r) for r in rows]
    if ids:
        wanted = set(ids)
        tasks = [t for t in tasks if t.instance_id in wanted]
    elif repos:
        tasks = [t for t in tasks if t.repo in repos]
    return tasks[:limit] if limit else tasks


# --- running one task ----------------------------------------------------------


def _git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "advice.detachedHead=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def checkout(repo_url: str, commit: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    _git("init", "-q", cwd=dest)
    _git("fetch", "-q", "--depth", "1", repo_url, commit, cwd=dest)
    _git("checkout", "-q", "FETCH_HEAD", cwd=dest)


def _apply_patch(repo: Path, patch: str) -> None:
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"], input=patch, text=True, cwd=repo, capture_output=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"patch did not apply: {proc.stderr.strip()}")


def patch_files(patch: str) -> list[str]:
    return sorted({line[6:].strip() for line in patch.splitlines() if line.startswith("+++ b/")})


def parse_results(output: str) -> dict[str, str]:
    """pytest -rA summary lines -> {node id: outcome}."""
    return {match.group(2): match.group(1) for match in _RESULT_LINE.finditer(output)}


def _outcome(results: dict[str, str], test: str) -> str | None:
    if test in results:
        return results[test]
    # SWE-bench lists some repos' tests by bare function name (sympy).
    for node, outcome in results.items():
        if node.endswith(f"::{test}") or node.split("::")[-1].split("[")[0] == test:
            return outcome
    return None


def evaluate(task: Task, repo: Path, sandbox: Sandbox, install_command: str) -> tuple[bool, dict]:
    """Apply the hidden tests and check FAIL_TO_PASS / PASS_TO_PASS."""
    _apply_patch(repo, task.test_patch)
    named = {t.split("::")[0] for t in task.fail_to_pass + task.pass_to_pass if "::" in t and t.split("::")[0].endswith(".py")}
    files = " ".join(shlex.quote(f) for f in sorted(set(patch_files(task.test_patch)) | named))
    timed = f"timeout -k 10 {test_timeout_from_env()} {EVAL_COMMAND}"
    run = sandbox.run_tests(repo, f"{install_command} && {timed} {files}")
    results = parse_results(f"{run.stdout}\n{run.stderr}")
    f2p = {t: _outcome(results, t) for t in task.fail_to_pass}
    p2p = {t: _outcome(results, t) for t in task.pass_to_pass}
    resolved = all(o == "PASSED" for o in f2p.values()) and all(o in ("PASSED", "XFAIL", "SKIPPED") for o in p2p.values())
    return resolved, {
        "fail_to_pass": f2p,
        "pass_to_pass_failed": sorted(t for t, o in p2p.items() if o not in ("PASSED", "XFAIL", "SKIPPED")),
    }


@dataclass
class TaskResult:
    instance_id: str
    repo: str
    resolved: bool = False
    claimed: bool = False  # Greenlit said "fixed"
    status: str = "error"  # FixResult.status, or "error"
    proof: str | None = None  # reproduced | not_reproduced | unproven
    iterations: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0
    ultra_only_usd: float = 0.0
    tokens: int = 0
    files_located: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    error: str | None = None


def run_task(
    task: Task,
    *,
    sandbox_factory: Callable[[], Sandbox],
    workdir: Path,
    repo_url: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    emit: Callable[[str, dict], None] = lambda t, p: None,
) -> TaskResult:
    out = TaskResult(task.instance_id, task.repo)
    started = time.monotonic()
    tally = usage.Tally()
    sandbox = sandbox_factory()
    try:
        repo = workdir / "repo"
        checkout(repo_url or f"https://github.com/{task.repo}", task.base_commit, repo)
        pristine = workdir / "pristine"
        shutil.copytree(repo, pristine, symlinks=True)

        setup = detect(repo)
        out.files_located = locate(repo, task.problem_statement)
        title = next((line.strip() for line in task.problem_statement.splitlines() if line.strip()), task.instance_id)
        issue = Issue(
            key=f"swe:{task.instance_id}",
            kind="report",
            title=title[:120],
            description=task.problem_statement,
            files=out.files_located,
        )
        engine = FixEngine(
            sandbox,
            repo,
            setup.install_command,
            setup.test_command,
            emit=emit,
            max_iterations=max_iterations,
            suite_targets=nearby_tests(repo, out.files_located) or None,
        )
        with usage.track(tally), usage.for_issue(issue.key):
            baseline = engine.run_suite()
            result = engine.fix(issue, baseline)
        out.status = result.status
        out.claimed = result.status == "fixed"
        out.proof = result.proof.status if result.proof else None
        out.iterations = result.iterations

        # Evaluate on a clean checkout: Greenlit's changes, then the hidden tests.
        _git("add", "-A", "--", ".", ":(exclude)**/__pycache__/**", ":(exclude)*.pyc", ":(exclude).pytest_cache", cwd=repo)
        patch = _git("diff", "--cached", "HEAD", cwd=repo)
        out.detail["patch"] = patch
        if patch.strip():
            _apply_patch(pristine, patch)
            out.resolved, evaluation = evaluate(task, pristine, sandbox, setup.install_command)
            out.detail.update(evaluation)
    except Exception as exc:  # noqa: BLE001 - one broken task mustn't stop the benchmark
        out.error = f"{type(exc).__name__}: {exc}"
        out.detail["traceback"] = traceback.format_exc()[-4000:]
    finally:
        sandbox.close()
        summary = tally.summary()
        out.seconds = round(time.monotonic() - started, 1)
        out.cost_usd = summary["total_usd"]
        out.ultra_only_usd = summary["ultra_only_usd"]
        out.tokens = sum(u.prompt_tokens + u.completion_tokens for u in tally.calls)
    return out


# --- the whole run ---------------------------------------------------------------


def summarize(results: list[TaskResult]) -> dict:
    n = len(results)
    resolved = sum(r.resolved for r in results)
    claimed = sum(r.claimed for r in results)
    false_fixes = sum(r.claimed and not r.resolved for r in results)
    total_cost = sum(r.cost_usd for r in results)
    ultra_only = sum(r.ultra_only_usd for r in results)
    return {
        "tasks": n,
        "resolved": resolved,
        "resolve_rate": resolved / n if n else 0.0,
        "claimed": claimed,
        "false_fixes": false_fixes,
        # Of the fixes Greenlit claimed, how many the hidden tests rejected.
        "false_fix_rate": false_fixes / claimed if claimed else 0.0,
        "reproduced": sum(r.proof == "reproduced" for r in results),
        "errors": sum(r.error is not None for r in results),
        "avg_seconds": sum(r.seconds for r in results) / n if n else 0.0,
        "total_cost_usd": total_cost,
        "avg_cost_usd": total_cost / n if n else 0.0,
        "cost_per_resolved_usd": total_cost / resolved if resolved else None,
        "savings_pct": (1 - total_cost / ultra_only) * 100 if ultra_only else 0.0,
    }


def run_benchmark(
    tasks: list[Task],
    *,
    sandbox_factory: Callable[[], Sandbox],
    out_dir: Path,
    repo_url_for: Callable[[Task], str | None] = lambda task: None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    on_result: Callable[[TaskResult], None] = lambda r: None,
) -> dict:
    results: list[TaskResult] = []
    for task in tasks:
        workdir = Path(tempfile.mkdtemp(prefix="greenlit-bench-"))
        try:
            result = run_task(
                task,
                sandbox_factory=sandbox_factory,
                workdir=workdir,
                repo_url=repo_url_for(task),
                max_iterations=max_iterations,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        results.append(result)
        on_result(result)

    report = {
        "benchmark": "SWE-bench Lite (problem statement only; hidden tests applied after)",
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models": {"plan_review_write_test": usage.ULTRA_MODEL, "evaluate_judge": usage.NANO_MODEL},
        "prices_per_million": {"ultra": usage.prices("ultra"), "nano": usage.prices("nano")},
        "summary": summarize(results),
        "tasks": [asdict(r) for r in results],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (out_dir / f"run-{stamp}.json").write_text(json.dumps(report, indent=2))
    (out_dir / "latest.json").write_text(json.dumps(report, indent=2))
    (out_dir / "REPORT.md").write_text(render_markdown(report))
    return report


def render_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# Greenlit benchmark",
        "",
        f"{report['benchmark']}. Finished {report['finished_at']}.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Tasks | {s['tasks']} |",
        f"| Resolved | {s['resolved']} ({s['resolve_rate']:.0%}) |",
        f"| Fixes claimed by Greenlit | {s['claimed']} |",
        f"| False fixes (claimed, but hidden tests fail) | {s['false_fixes']} ({s['false_fix_rate']:.0%} of claimed) |",
        f"| Bugs reproduced with a failing test first | {s['reproduced']} |",
        f"| Average time per task | {s['avg_seconds']:.0f}s |",
        f"| Average model cost per task (est.) | ${s['avg_cost_usd']:.4f} |",
        f"| Cost per resolved task (est.) | {'$%.4f' % s['cost_per_resolved_usd'] if s['cost_per_resolved_usd'] is not None else 'n/a'} |",
        f"| Saved by Ultra/Nano tiering vs Ultra-only | {s['savings_pct']:.0f}% |",
        f"| Tasks that errored (setup, clone, install) | {s['errors']} |",
        "",
        "| Task | Resolved | Greenlit status | Proof | Attempts | Time | Cost |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in report["tasks"]:
        lines.append(
            f"| {t['instance_id']} | {'✅' if t['resolved'] else '❌'} | {t['status']} | {t['proof'] or '-'} | "
            f"{t['iterations']} | {t['seconds']:.0f}s | ${t['cost_usd']:.4f} |"
        )
    lines += [
        "",
        f"Prices (USD per 1M tokens, in/out): Ultra {report['prices_per_million']['ultra']}, "
        f"Nano {report['prices_per_million']['nano']}. Estimates; confirm against your Token Factory console.",
    ]
    return "\n".join(lines) + "\n"
