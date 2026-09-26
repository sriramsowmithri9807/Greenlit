"""GitHub side of the agent: parse repo URLs, call the REST API (issues,
pull requests), and drive git (clone, branch, commit, push).

The token is never written to disk: git gets it per command as an HTTP
auth header (the same mechanism actions/checkout uses), not embedded in the
remote URL or .git/config, and every error message is scrubbed of it.
Repo hooks are disabled on every git call, since the clone is untrusted.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

API_URL = "https://api.github.com"
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com[/:](?P<owner>[^/\s]+)/(?P<name>[^/\s#?]+?)(?:\.git)?(?:[/#?].*)?$"
)
_SHORT_RE = re.compile(r"^(?P<owner>[^/\s]+)/(?P<name>[^/\s]+?)(?:\.git)?$")
_SSH_RE = re.compile(r"^git@github\.com:(?P<owner>[^/\s]+)/(?P<name>[^/\s]+?)(?:\.git)?$")


class GitHubError(Exception):
    pass


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.full_name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.full_name}.git"


def parse_repo_url(text: str) -> RepoRef:
    """Accepts https://github.com/owner/repo (with or without .git, a
    trailing slash, or a /tree/... suffix), git@github.com:owner/repo.git,
    or plain owner/repo. Anything not on github.com is rejected."""
    text = (text or "").strip()
    for pattern in (_URL_RE, _SSH_RE, _SHORT_RE):
        match = pattern.match(text)
        if match:
            owner, name = match.group("owner"), match.group("name")
            if _NAME_RE.match(owner) and _NAME_RE.match(name) and name not in (".", ".."):
                return RepoRef(owner, name)
    raise ValueError(f"Not a GitHub repository URL: {text!r}. Expected https://github.com/<owner>/<repo>")


def mask(text: str, token: str | None) -> str:
    if not token:
        return text
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return text.replace(token, "***").replace(encoded, "***")


class GitHubAPI:
    def __init__(self, token: str | None, *, base_url: str = API_URL, transport: httpx.BaseTransport | None = None):
        self._token = token
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "greenlit-agent",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=30, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubError(mask(f"Couldn't reach GitHub: {exc}", self._token)) from None
        if response.status_code < 400:
            return response.json() if response.content else {}

        try:
            detail = response.json().get("message", "")
        except ValueError:
            detail = response.text[:200]
        hint = {
            401: "The token was rejected — check it hasn't expired or been revoked.",
            403: "The token doesn't have permission for this. It needs Contents, Issues and "
            "Pull requests set to Read and write for this repo.",
            404: "Repository not found. If it's private, a token with access to it is required.",
        }.get(response.status_code, "")
        raise GitHubError(mask(f"GitHub {method} {path} failed ({response.status_code}): {detail} {hint}".strip(), self._token))

    def get_repo(self, ref: RepoRef) -> dict:
        return self._request("GET", f"/repos/{ref.full_name}")

    def get_user(self) -> dict:
        return self._request("GET", "/user")

    def ensure_label(self, ref: RepoRef, name: str, color: str, description: str) -> None:
        try:
            self._request("GET", f"/repos/{ref.full_name}/labels/{name}")
        except GitHubError:
            self._request(
                "POST",
                f"/repos/{ref.full_name}/labels",
                json={"name": name, "color": color, "description": description},
            )

    def create_issue(self, ref: RepoRef, title: str, body: str, labels: list[str]) -> dict:
        return self._request(
            "POST", f"/repos/{ref.full_name}/issues", json={"title": title, "body": body, "labels": labels}
        )

    def comment_on_issue(self, ref: RepoRef, number: int, body: str) -> dict:
        return self._request("POST", f"/repos/{ref.full_name}/issues/{number}/comments", json={"body": body})

    def create_pull(self, ref: RepoRef, *, title: str, head: str, base: str, body: str) -> dict:
        return self._request(
            "POST",
            f"/repos/{ref.full_name}/pulls",
            json={"title": title, "head": head, "base": base, "body": body},
        )


class GitWorkspace:
    """A local clone the agent commits into. `remote_url` is normally the
    repo's https clone URL; tests point it at a local bare repo."""

    def __init__(self, remote_url: str, directory: Path, token: str | None = None):
        self.remote_url = remote_url
        self.directory = directory
        self._token = token

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        # Isolated from the host's git config: no global/system config and no
        # credential helpers, so a rejected user token can never fall back to
        # whatever credentials the machine running Greenlit has stored.
        config = [
            "-c", "core.hooksPath=/dev/null",
            "-c", "credential.helper=",
            "-c", "advice.detachedHead=false",
        ]
        if self._token:
            basic = base64.b64encode(f"x-access-token:{self._token}".encode()).decode()
            config += ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]
        proc = subprocess.run(
            ["git", *config, *args],
            cwd=cwd or self.directory,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        )
        if proc.returncode != 0:
            raise GitHubError(mask(f"git {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}", self._token))
        return proc.stdout.strip()

    def init_from_directory(self, source: Path, ignore: set[str] | frozenset[str]) -> None:
        """Stand in for a clone when working from a local folder: copy it and
        commit the copy as a baseline so pending_diff() has something to
        diff against."""
        shutil.copytree(source, self.directory, ignore=shutil.ignore_patterns(*ignore), symlinks=True)
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("-c", "user.name=greenlit", "-c", "user.email=greenlit@localhost", "commit", "-q", "-m", "baseline")

    def clone(self, branch: str | None = None) -> None:
        args = ["clone", "--depth", "1", "--no-tags"]
        if branch:
            args += ["--branch", branch]
        self._git(*args, self.remote_url, str(self.directory), cwd=self.directory.parent)

    def create_branch(self, name: str) -> None:
        self._git("checkout", "-b", name)

    def commit(self, paths: list[str], message: str, *, author_name: str, author_email: str) -> str:
        self._git("add", "--", *paths)
        self._git(
            "-c", f"user.name={author_name}",
            "-c", f"user.email={author_email}",
            "commit", "-q", "-m", message,
        )
        return self._git("rev-parse", "HEAD")

    def push(self, branch: str) -> None:
        self._git("push", "-q", "origin", f"HEAD:refs/heads/{branch}")

    def pending_diff(self) -> str:
        """Everything changed in the working tree since the clone, new files
        included (used for dry runs, where nothing is committed)."""
        self._git("add", "-A")
        return self._git("diff", "--cached")
