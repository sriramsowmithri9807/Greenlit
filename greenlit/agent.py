"""The Greenlit agent: a GitHub repo goes in; issues get raised, fixed,
verified in a sandbox, and come back as a pull request.

    clone -> scan (test suite + Nemotron code review) -> raise GitHub issues
          -> fix each one (greenlit.orchestrator.FixEngine) -> commit + push
          -> open a PR that closes what was fixed, comment on what wasn't

With a token, everything lands on a new `greenlit/fix-*` branch and a pull
request: nothing is ever pushed to the default branch. Without a token it's
a read-only dry run of the same pipeline: fixes are still verified in the
sandbox and shown in the UI, but nothing is written to GitHub.
"""
from __future__ import annotations

import shutil
import tempfile
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from greenlit.clients.sandbox import Sandbox
from greenlit.config import GreenlitConfig
from greenlit.github import GitHubAPI, GitHubError, GitWorkspace, mask, parse_repo_url
from greenlit.issues import Issue
from greenlit.orchestrator import DEFAULT_MAX_ITERATIONS, FixEngine, FixResult
from greenlit.perceive import failure_section
from greenlit.project import UnsupportedProject, detect
from greenlit.repo_files import IGNORED_DIRS
from greenlit.review import review

Emit = Callable[[str, dict], None]

DEFAULT_MAX_ISSUES = 6
BRANCH_PREFIX = "greenlit/fix-"
LABEL_NAME, LABEL_COLOR, LABEL_DESCRIPTION = "greenlit", "2ea44f", "Raised by the Greenlit agent"


class AgentError(Exception):
    """A failure the user can act on (bad URL, no access, unsupported repo).
    Its message is shown in the UI as-is."""


@dataclass
class AgentResult:
    status: str  # "clean" | "fixed" | "partial" | "unresolved" | "error"
    issues: list[Issue] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    pr_url: str | None = None


def _noop_emit(event_type: str, payload: dict) -> None:
    pass


def _default_sandbox() -> Sandbox:
    return Sandbox(GreenlitConfig.from_env())


def _test_issue_title(test_id: str, reason: str) -> str:
    """`test_add fails: assert -1 == 5` reads better as an issue title than
    the full node id, which is shown separately as the issue's location."""
    name = test_id.split("::")[-1]
    reason = " ".join(reason.split())
    if not reason:
        return f"{name} fails"
    return f"{name} fails: {reason if len(reason) <= 80 else reason[:77] + '...'}"


def _commit_message(issue: Issue, result: FixResult) -> str:
    verified = (
        f"{issue.test_id} passes and no previously-passing test fails"
        if issue.kind == "test"
        else "the patched code compiles and no previously-passing test fails"
    )
    rationale = textwrap.fill(result.rationale or "", width=72)
    return f"Fix {issue.ref}: {issue.title}\n\n{rationale}\n\nVerified by Greenlit in a Nebius Token Factory sandbox: {verified}."


def _pr_body(fixed: list[Issue], unresolved: list[Issue], incidental: set[str], results: dict[str, FixResult]) -> str:
    lines = [
        f"Greenlit scanned this repo, raised {len(fixed) + len(unresolved)} issue(s) and fixed {len(fixed)}. "
        "Every fix was checked by running the test suite in an isolated Nebius Token Factory sandbox "
        "before it was committed.",
        "",
        "### Fixed",
    ]
    for issue in fixed:
        note = " (fixed as a side effect of an earlier change)" if issue.key in incidental else ""
        lines.append(f"- Closes {issue.ref}: {issue.title} (`{issue.location}`){note}")
    if unresolved:
        lines += ["", "### Not fixed"]
        for issue in unresolved:
            attempts = results.get(issue.key)
            reason = attempts.attempts[-1].why_it_failed if attempts and attempts.attempts else "no fix passed verification"
            lines.append(f"- {issue.ref}: {issue.title}. Last attempt rejected because {reason}")
    if any(i.kind == "review" for i in fixed):
        lines += [
            "",
            "> Fixes for issues found by code review aren't backed by a failing test. "
            "They compile and don't break any test, but please review them closely.",
        ]
    lines += [
        "",
        "<details><summary>How this was made</summary>",
        "",
        "Code review and fix planning: NVIDIA Nemotron 3 Ultra. Test-result evaluation: NVIDIA Nemotron 3 Nano. "
        "Both served by Nebius Token Factory. A fix is only accepted if the target test passes and no "
        "previously-passing test fails.",
        "</details>",
    ]
    return "\n".join(lines)


def _unresolved_comment(result: FixResult | None) -> str:
    if not result or not result.attempts:
        return "Greenlit couldn't produce a fix for this that passed verification."
    last = result.attempts[-1]
    return (
        f"Greenlit tried {len(result.attempts)} fix(es) for this and none passed verification in the sandbox.\n\n"
        f"Last attempt was rejected because {last.why_it_failed}\n\n"
        f"<details><summary>Last diff tried</summary>\n\n```diff\n{last.diff}\n```\n</details>"
    )


def run_agent(
    repo_url: str,
    token: str | None = None,
    *,
    include_review: bool = True,
    max_issues: int = DEFAULT_MAX_ISSUES,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    emit: Emit = _noop_emit,
    sandbox_factory: Callable[[], Sandbox] = _default_sandbox,
    api_factory: Callable[[str | None], GitHubAPI] = GitHubAPI,
    remote_url: str | None = None,
    allow_local: bool = False,
) -> AgentResult:
    """`repo_url` is a GitHub URL, or (only when `allow_local`, i.e. from the
    CLI, never from the web server) a local folder, which always runs as a
    dry run."""
    token = (token or "").strip() or None
    local_dir = Path(repo_url).expanduser() if allow_local and Path(repo_url).expanduser().is_dir() else None
    live = token is not None and local_dir is None
    workdir = Path(tempfile.mkdtemp(prefix="greenlit-run-"))
    sandbox: Sandbox | None = None
    api: GitHubAPI | None = None
    issues: list[Issue] = []

    try:
        emit("status", {"value": "scanning"})
        emit("phase", {"value": "clone"})

        if local_dir is not None:
            ref = None
            workspace = GitWorkspace(str(local_dir), workdir / "repo")
            workspace.init_from_directory(local_dir, IGNORED_DIRS)
            emit("repo", {"full_name": local_dir.name, "url": None, "default_branch": None, "mode": "dry_run"})
            emit("log_line", {"text": f"Copied local folder {local_dir}"})
            default_branch = ""
        else:
            try:
                ref = parse_repo_url(repo_url)
            except ValueError as exc:
                raise AgentError(str(exc)) from None
            api = api_factory(token)
            try:
                info = api.get_repo(ref)
            except GitHubError as exc:
                raise AgentError(str(exc)) from None
            default_branch = info.get("default_branch") or "main"
            if live and not info.get("permissions", {}).get("push"):
                raise AgentError(
                    f"This token can read {ref.full_name} but can't push to it, so Greenlit can't open a pull request. "
                    "Use a token with Contents, Issues and Pull requests set to Read and write, "
                    "or leave the token empty for a read-only dry run."
                )
            emit(
                "repo",
                {
                    "full_name": ref.full_name,
                    "url": info.get("html_url") or ref.html_url,
                    "default_branch": default_branch,
                    "mode": "live" if live else "dry_run",
                },
            )
            workspace = GitWorkspace(remote_url or ref.clone_url, workdir / "repo", token)
            try:
                workspace.clone(default_branch)
            except GitHubError as exc:
                raise AgentError(f"Couldn't clone {ref.full_name}: {exc}") from None
            emit("log_line", {"text": f"Cloned {ref.full_name} ({default_branch})"})

        # --- scan ---------------------------------------------------------------
        emit("phase", {"value": "scan"})
        try:
            setup = detect(workspace.directory)
        except UnsupportedProject as exc:
            raise AgentError(str(exc)) from None

        sandbox = sandbox_factory()
        engine = FixEngine(
            sandbox,
            workspace.directory,
            setup.install_command,
            setup.test_command,
            emit=emit,
            max_iterations=max_iterations,
        )
        emit("log_line", {"text": "Running the test suite in a Nebius Token Factory sandbox"})
        baseline = engine.run_suite()
        if not baseline.ran:
            tail = "\n".join(baseline.output.strip().splitlines()[-15:])
            raise AgentError(f"The test suite didn't run in the sandbox (the install step may have failed). Last output:\n{tail}")

        if baseline.no_tests:
            emit("log_line", {"text": "No tests found, relying on code review"})
        else:
            emit("log_line", {"text": f"Test suite: {len(baseline.failures)} failing"})
        for env_error in baseline.env_errors:
            emit("log_line", {"text": f"Skipping {env_error.test_id}: {env_error.reason} (a missing dependency, not a code bug)"})

        issues = [
            Issue(
                key=f"test:{f.test_id}",
                kind="test",
                title=_test_issue_title(f.test_id, f.reason),
                test_id=f.test_id,
                failure_output=failure_section(baseline.output, f.test_id) or f.reason,
            )
            for f in baseline.failures
        ]

        if include_review:
            emit("log_line", {"text": f"Code review (Nemotron Ultra) over {len(setup.review_candidates)} file(s)"})
            known = [f"{f.test_id}: {f.reason}" for f in baseline.failures]
            review_issues, dropped = review(workspace.directory, setup.review_candidates, known)
            emit(
                "log_line",
                {"text": f"Code review: {len(review_issues)} credible bug(s)" + (f", {dropped} low-confidence finding(s) dropped" if dropped else "")},
            )
            issues += review_issues

        if len(issues) > max_issues:
            emit("log_line", {"text": f"Found {len(issues)} issues, working the first {max_issues}"})
            issues = issues[:max_issues]

        if not issues:
            emit("log_line", {"text": "No issues found. Every test passes and code review came back clean."})
            emit("status", {"value": "clean"})
            emit("phase", {"value": "done"})
            return AgentResult(status="clean")

        # --- raise ----------------------------------------------------------------
        emit("phase", {"value": "raise"})
        if live:
            labels = [LABEL_NAME]
            try:
                api.ensure_label(ref, LABEL_NAME, LABEL_COLOR, LABEL_DESCRIPTION)
            except GitHubError:
                labels = []
            for issue in issues:
                created = api.create_issue(ref, f"[Greenlit] {issue.title}", issue.github_body(), labels)
                issue.number, issue.url = created["number"], created["html_url"]
                emit("issue_raised", issue.to_event())
            emit("log_line", {"text": f"Raised {len(issues)} issue(s) on {ref.full_name}"})
        else:
            for issue in issues:
                emit("issue_raised", issue.to_event())
            emit("log_line", {"text": "Dry run: not raising issues on GitHub (no token)"})

        # --- fix --------------------------------------------------------------------
        emit("phase", {"value": "fix"})
        emit("status", {"value": "testing"})
        branch = f"{BRANCH_PREFIX}{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        author_name = author_email = ""
        if live:
            workspace.create_branch(branch)
            user = api.get_user()
            author_name = user.get("name") or user["login"]
            author_email = f"{user['id']}+{user['login']}@users.noreply.github.com"

        fixed: list[Issue] = []
        unresolved: list[Issue] = []
        incidental: set[str] = set()
        results: dict[str, FixResult] = {}
        pushed = False

        for position, issue in enumerate(issues):
            emit("issue_start", {"key": issue.key, "remaining": len(issues) - position})
            if issue.kind == "test" and issue.test_id not in baseline.problem_ids:
                emit("log_line", {"text": f"{issue.ref} already passes after an earlier fix"})
                fixed.append(issue)
                incidental.add(issue.key)
                emit("issue_end", {"key": issue.key, "status": "fixed"})
                continue

            result = engine.fix(issue, baseline)
            results[issue.key] = result
            if result.status != "fixed":
                unresolved.append(issue)
                emit("issue_end", {"key": issue.key, "status": "unresolved"})
                continue

            baseline = result.suite_after or baseline
            fixed.append(issue)
            if live:
                message = _commit_message(issue, result)
                sha = workspace.commit(result.changed_files, message, author_name=author_name, author_email=author_email)
                workspace.push(branch)
                pushed = True
                emit(
                    "commit",
                    {
                        "key": issue.key,
                        "sha": sha,
                        "message": message.splitlines()[0],
                        "url": f"{ref.html_url}/commit/{sha}",
                    },
                )
            emit("issue_end", {"key": issue.key, "status": "fixed"})

        # --- publish -----------------------------------------------------------------
        emit("phase", {"value": "publish"})
        pr_url = None
        if live:
            if pushed:
                pr = api.create_pull(
                    ref,
                    title=f"Greenlit: fix {len(fixed)} issue(s)",
                    head=branch,
                    base=default_branch,
                    body=_pr_body(fixed, unresolved, incidental, results),
                )
                pr_url = pr["html_url"]
                emit("pr_opened", {"number": pr["number"], "url": pr_url})
            for issue in unresolved:
                if issue.number:
                    api.comment_on_issue(ref, issue.number, _unresolved_comment(results.get(issue.key)))
        else:
            combined = workspace.pending_diff()
            if combined:
                emit("diff_ready", {"diff": combined})
            emit(
                "log_line",
                {"text": f"Dry run complete: {len(fixed)} fix(es) verified in the sandbox, nothing pushed. Add a token to raise issues and open a pull request."},
            )

        status = "fixed" if not unresolved else ("partial" if fixed else "unresolved")
        emit("status", {"value": status})
        emit("phase", {"value": "done"})
        return AgentResult(
            status=status,
            issues=issues,
            fixed=[i.key for i in fixed],
            unresolved=[i.key for i in unresolved],
            pr_url=pr_url,
        )

    except AgentError as exc:
        emit("run_error", {"message": mask(str(exc), token)})
        emit("status", {"value": "error"})
        return AgentResult(status="error", issues=issues)
    except Exception as exc:  # noqa: BLE001 - surface anything else to the UI instead of dying silently
        emit("run_error", {"message": mask(f"Unexpected error: {type(exc).__name__}: {exc}", token)})
        emit("status", {"value": "error"})
        return AgentResult(status="error", issues=issues)
    finally:
        if sandbox is not None:
            sandbox.close()
        if api is not None:
            api.close()
        shutil.rmtree(workdir, ignore_errors=True)
