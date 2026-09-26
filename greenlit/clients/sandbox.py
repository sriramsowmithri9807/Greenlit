"""Wrapper around the Nebius Token Factory Sandboxes SDK (package: contree-sdk).

Confirmed live from https://docs.tokenfactory.nebius.com/sandboxes/ :
 - low-level transport: contree_client.sync.ContreeClient(api_key, project=...)
 - high-level SDK: contree_sdk.ContreeSync(client), with `.images.use(tag)`,
   `.apply_files(files={dest_path: local_path})`, and `.run(shell=...).wait()`
   returning `.stdout` / `.stderr` / `.exit_code`.
No target-repo code ever runs on this host; it only ever runs inside the
sandbox's microVM.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSync

from greenlit.config import GreenlitConfig
from greenlit.repo_files import iter_repo_files

DEFAULT_BASE_IMAGE = "python:3.11-slim"


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int


class Sandbox:
    def __init__(self, config: GreenlitConfig, base_image: str = DEFAULT_BASE_IMAGE):
        self._client = ContreeClient(config.nebius_api_key, project=config.nebius_ai_project)
        self._sdk = ContreeSync(self._client)
        self._base_image = base_image

    def run_shell(self, command: str) -> SandboxResult:
        """Run a bare shell command with no file staging. Used for the
        build-order step 1 connectivity proof, not for real test runs."""
        image = self._sdk.images.use(self._base_image)
        result = image.run(shell=command, disposable=True).wait()
        return SandboxResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.exit_code,
        )

    def run_tests(self, repo_dir: Path, test_command: str) -> SandboxResult:
        """Stage a throwaway copy of `repo_dir` into the sandbox and run
        `test_command` inside it. The caller's real working tree is never
        touched or executed on the host."""
        files = {
            f"/work/{path.relative_to(repo_dir).as_posix()}": path
            for path in iter_repo_files(repo_dir)
        }
        image = self._sdk.images.use(self._base_image)
        staged = image.apply_files(files=files)
        result = staged.run(shell=f"cd /work && {test_command}", disposable=True).wait()
        return SandboxResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.exit_code,
        )

    def close(self) -> None:
        self._client.close()
