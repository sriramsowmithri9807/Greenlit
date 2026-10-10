"""The unit of work the agent raises on GitHub and then tries to fix."""
from __future__ import annotations

from dataclasses import dataclass

GREENLIT_FOOTER = "_Raised automatically by Greenlit — NVIDIA Nemotron via Nebius Token Factory._"
_MAX_BODY_OUTPUT_LINES = 60


@dataclass
class Issue:
    key: str  # stable within a run: "test:<pytest node id>" or "review:<n>"
    kind: str  # "test" (backed by a failing test) | "review" (found by code review) | "report" (a bug report, e.g. a GitHub issue)
    title: str
    test_id: str | None = None
    failure_output: str | None = None
    file: str | None = None
    line: int | None = None
    severity: str | None = None
    description: str | None = None
    evidence: str | None = None
    number: int | None = None  # GitHub issue number once raised
    url: str | None = None
    proof: dict | None = None  # orchestrator.Proof.to_event(), once REPRODUCE has run
    files: list[str] | None = None  # for "report": source files it's probably about (greenlit.locate)

    @property
    def location(self) -> str | None:
        if self.kind == "test":
            return self.test_id
        if self.file:
            return f"{self.file}:{self.line}" if self.line else self.file
        return None

    @property
    def ref(self) -> str:
        return f"#{self.number}" if self.number else self.key

    def github_body(self) -> str:
        if self.kind == "test":
            output = "\n".join((self.failure_output or "").strip().splitlines()[-_MAX_BODY_OUTPUT_LINES:])
            return (
                f"**Failing test:** `{self.test_id}`\n\n"
                f"```\n{output}\n```\n\n"
                f"{GREENLIT_FOOTER}"
            )
        body = (
            f"**Location:** `{self.location}`  \n"
            f"**Severity:** {self.severity}\n\n"
            f"{self.description}\n\n"
            f"**Evidence:**\n```python\n{self.evidence}\n```\n\n"
        )
        if self.proof and self.proof.get("status") == "reproduced":
            output = "\n".join((self.proof.get("output") or "").strip().splitlines()[-_MAX_BODY_OUTPUT_LINES:])
            body += (
                "Found by AI code review (NVIDIA Nemotron 3 Ultra) and **reproduced**: this test, "
                f"`{self.proof['test_path']}`, fails on the current code.\n\n"
                f"```python\n{self.proof['test_code']}\n```\n\n"
                f"<details><summary>Failure</summary>\n\n```\n{output}\n```\n</details>\n\n"
            )
        else:
            body += (
                "Found by AI code review (NVIDIA Nemotron 3 Ultra), not by a failing test — "
                "worth a sanity check.\n\n"
            )
        return body + GREENLIT_FOOTER

    def to_event(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "title": self.title,
            "location": self.location,
            "severity": self.severity,
            "number": self.number,
            "url": self.url,
        }
