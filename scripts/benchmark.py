"""Benchmark Greenlit on SWE-bench Lite.

    python scripts/benchmark.py --limit 25                  # default repo subset
    python scripts/benchmark.py --repos psf/requests --limit 5
    python scripts/benchmark.py --ids psf__requests-2317 sympy__sympy-20590
    python scripts/benchmark.py --tasks my_tasks.jsonl     # any SWE-bench-format file

Greenlit gets only each task's problem statement. Its patch is then graded
with the task's hidden tests (FAIL_TO_PASS must pass, PASS_TO_PASS must
still pass). Results go to bench/results/ (latest.json, REPORT.md, and a
timestamped copy); the dashboard's start page shows latest.json.

Every test run happens in a Nebius sandbox, so this needs NEBIUS_API_KEY and
NEBIUS_AI_PROJECT (e.g. in .env). Expect several minutes per task.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from greenlit import bench  # noqa: E402
from greenlit.clients.sandbox import Sandbox  # noqa: E402
from greenlit.config import GreenlitConfig  # noqa: E402
from greenlit.orchestrator import DEFAULT_MAX_ITERATIONS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", type=Path, help="JSONL/JSON file of SWE-bench-format tasks (default: download SWE-bench Lite)")
    parser.add_argument("--repos", nargs="*", default=list(bench.DEFAULT_REPOS), help="Only tasks from these repos")
    parser.add_argument("--ids", nargs="*", help="Only these instance ids (overrides --repos)")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--image", default="python:3.11-slim", help="Sandbox base image")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    parser.add_argument("--out", type=Path, default=ROOT / "bench" / "results")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = GreenlitConfig.from_env()

    if args.tasks:
        text = args.tasks.read_text()
        rows = json.loads(text) if text.lstrip().startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    else:
        rows = bench.fetch_swe_bench_lite(ROOT / "bench" / "cache" / "swe_bench_lite.jsonl")
    tasks = bench.select(rows, repos=tuple(args.repos) if args.repos else None, ids=args.ids, limit=args.limit)
    if not tasks:
        parser.error("no tasks matched")
    print(f"Running {len(tasks)} task(s)")

    def show(result: bench.TaskResult) -> None:
        mark = "✅" if result.resolved else ("⚠️ false fix" if result.claimed else "❌")
        extra = f" error: {result.error}" if result.error else ""
        print(f"{mark} {result.instance_id}  {result.status}/{result.proof}  {result.seconds:.0f}s  ${result.cost_usd:.4f}{extra}")

    report = bench.run_benchmark(
        tasks,
        sandbox_factory=lambda: Sandbox(config, base_image=args.image),
        out_dir=args.out,
        max_iterations=args.max_iterations,
        on_result=show,
    )
    print()
    print(bench.render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
