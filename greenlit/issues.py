"""The unit of work the agent raises on GitHub and then tries to fix."""
from __future__ import annotations

from dataclasses import dataclass

GREENLIT_FOOTER = "_Raised automatically by Greenlit — NVIDIA Nemotron via Nebius Token Factory._"
_MAX_BODY_OUTPUT_LINES = 60


@dataclass
class Issue:
    key: str  # stable within a run: "test:<pytest node id>" or "review:<n>"
    kind: str  # "test" (backed by a failing test) | "review" (found by code review)
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
        return (
            f"**Location:** `{self.location}`  \n"
            f"**Severity:** {self.severity}\n\n"
            f"{self.description}\n\n"
            f"**Evidence:**\n```python\n{self.evidence}\n```\n\n"
            "Found by AI code review (NVIDIA Nemotron 3 Ultra), not by a failing test — "
            "worth a sanity check.\n\n"
            f"{GREENLIT_FOOTER}"
        )

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
