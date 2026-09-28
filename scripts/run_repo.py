"""CLI: run the Greenlit agent against a GitHub repo or a local folder.

    python scripts/run_repo.py https://github.com/owner/repo            # dry run
    GITHUB_TOKEN=... python scripts/run_repo.py https://github.com/owner/repo --live
    python scripts/run_repo.py demo/fixture_multi                       # local folder, dry run

A dry run finds issues and verifies fixes in the sandbox but writes nothing
to GitHub. With --live (needs GITHUB_TOKEN), once every fix is verified the
full change report is printed (files, line numbers, removed and added code)
and you're asked whether to publish: only on "y" does Greenlit raise the
issues, push the fixes to a new greenlit/fix-* branch and open a pull
request. --yes skips the question.

Needs NEBIUS_API_KEY and NEBIUS_AI_PROJECT (e.g. in .env).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenlit.agent import DEFAULT_MAX_ISSUES, run_agent
from greenlit.changes import render_text
from greenlit.orchestrator import DEFAULT_MAX_ITERATIONS


COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
_reported = False  # after the change report, the combined diff would just repeat it


def ask_to_publish(request: dict, *, assume_yes: bool) -> bool:
    print("Publishing will:")
    for action in request["actions"]:
        print(f"  - {action}")
    if assume_yes:
        print("Publishing (--yes).")
        return True
    if not sys.stdin.isatty():
        print("Not publishing: no terminal to ask for permission (pass --yes to publish anyway).")
        return False
    try:
        what = "the pull request" if request["commits"] else "these issues"
        answer = input(f"Raise {what} on {request['repo']}? [y/N] ")
    except EOFError:
        answer = ""
    return answer.strip().lower() in ("y", "yes")


def emit(event_type: str, payload: dict) -> None:
    global _reported
    if event_type == "log_line":
        print(f"  {payload['text']}")
    elif event_type == "diff_ready":
        if _reported:
            return
        print("  ┌ diff")
        for line in payload["diff"].splitlines():
            print(f"  │ {line}")
        print("  └")
    elif event_type == "changes_ready":
        _reported = True
        print()
        print(render_text(payload, color=COLOR))
        print()
    elif event_type in ("stage_start", "stage_end", "iteration", "approval_required", "approval"):
        return
    else:
        print(f"[{event_type}] {payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", help="GitHub repo URL, owner/repo, or a local folder")
    parser.add_argument("--live", action="store_true", help="Raise issues and open a PR (reads GITHUB_TOKEN)")
    parser.add_argument("--yes", action="store_true", help="With --live: publish without asking")
    parser.add_argument("--no-review", action="store_true", help="Skip the Nemotron code review; failing tests only")
    parser.add_argument("--max-issues", type=int, default=DEFAULT_MAX_ISSUES)
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    args = parser.parse_args()

    token = None
    if args.live:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            parser.error("--live needs a GitHub token in the GITHUB_TOKEN environment variable")

    result = run_agent(
        args.repo,
        token,
        include_review=not args.no_review,
        max_issues=args.max_issues,
        max_iterations=args.max_iterations,
        emit=emit,
        approve=lambda request: ask_to_publish(request, assume_yes=args.yes),
        allow_local=True,
    )
    print()
    print(f"Result: {result.status}")
    print(f"Fixed: {len(result.fixed)}  Unresolved: {len(result.unresolved)}")
    if result.pr_url:
        print(f"Pull request: {result.pr_url}")
    elif args.live and result.status in ("fixed", "partial", "unresolved") and not result.published:
        print("Not published: nothing was written to GitHub.")
    return 0 if result.status in ("clean", "fixed") else 1


if __name__ == "__main__":
    sys.exit(main())
