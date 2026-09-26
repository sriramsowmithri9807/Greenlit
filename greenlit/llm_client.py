"""Nemotron LLM client for Greenlit's PLAN and EVALUATE steps.

Standalone module: no orchestration loop, no sandbox integration here — just
the two model-calling functions. Model IDs and endpoint below are pinned
exactly as confirmed against the live Nebius Token Factory console; do not
substitute or guess alternatives.

These are shared/public Token Factory endpoints ("fine for testing, not
production, availability may change without notice"), so calls are wrapped
with a small manual retry on transient errors.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

PLAN_MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"
EVAL_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0


def get_client() -> OpenAI:
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NEBIUS_API_KEY is not set. Get a key from https://tokenfactory.nebius.com "
            "and set it: export NEBIUS_API_KEY=..."
        )
    return OpenAI(base_url=BASE_URL, api_key=api_key)


def _create_with_retry(client: OpenAI, **kwargs: Any):
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except _RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt == _MAX_ATTEMPTS:
                break
            time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise RuntimeError(
        f"Nebius Token Factory call to {kwargs.get('model')!r} failed after "
        f"{_MAX_ATTEMPTS} attempts: {last_exc}"
    ) from last_exc


def _extract_tool_call_args(response, tool_name: str) -> dict:
    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    for call in tool_calls:
        if call.function.name == tool_name:
            return json.loads(call.function.arguments)
    raise RuntimeError(
        f"Model {response.model!r} did not call the required tool {tool_name!r}. "
        f"finish_reason={response.choices[0].finish_reason!r}, "
        f"message content instead: {message.content!r}"
    )


# --- PLAN --------------------------------------------------------------

_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_fix",
        "description": "Propose a fix for the failing test.",
        "parameters": {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "The proposed fix as a unified diff.",
                },
                "rationale": {
                    "type": "string",
                    "description": (
                        "One paragraph, plain English, explaining the root cause "
                        "and why this diff fixes it."
                    ),
                },
                "unfamiliar_api": {
                    "type": "boolean",
                    "description": (
                        "True if confidence in this fix requires looking up external "
                        "docs for an unfamiliar or version-sensitive API."
                    ),
                },
                "unfamiliar_api_query": {
                    "type": ["string", "null"],
                    "description": (
                        "Search query to look up docs for the unfamiliar API. "
                        "Must be null when unfamiliar_api is false."
                    ),
                },
            },
            "required": ["diff", "rationale", "unfamiliar_api", "unfamiliar_api_query"],
            "additionalProperties": False,
        },
    },
}

_PLAN_SYSTEM_PROMPT = (
    "You are the PLAN step of an autonomous bug-fixing agent. You get either a "
    "failing test (stack_trace) or a reported bug (issue: title, location, "
    "description), plus the relevant source files. Reason about the root cause "
    "first, then propose the SMALLEST diff that fixes it. Fix the code under test, "
    "never weaken or delete a test to make it pass. The diff must be a unified diff "
    "whose paths are relative to the repository root with a/ and b/ prefixes "
    "(--- a/pkg/mod.py, +++ b/pkg/mod.py), with exact context lines copied from the "
    "source provided. If prior_attempts is present, never repeat a diff already "
    "listed there — each entry records why that attempt failed, so take a genuinely "
    "different approach. If research_context is present, it is real documentation "
    "pulled to answer a prior unfamiliar_api flag; use it to inform this attempt. "
    "Always respond by calling the propose_fix tool."
)


def call_planner(error_context: dict) -> dict:
    """error_context keys: stack_trace (test issues) or issue (review issues),
    source_files (dict path -> content), prior_attempts (optional list of
    {diff, why_it_failed}), research_context (optional str, Tavily summary)."""
    client = get_client()
    response = _create_with_retry(
        client,
        model=PLAN_MODEL,
        messages=[
            {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(error_context, indent=2)},
        ],
        tools=[_PLAN_TOOL],
        tool_choice={"type": "function", "function": {"name": "propose_fix"}},
    )
    return _extract_tool_call_args(response, "propose_fix")


# --- EVALUATE ------------------------------------------------------------

_EVAL_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_result",
        "description": "Classify a sandboxed test run's result.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["PASS", "FAIL_SAME_ERROR", "FAIL_NEW_ERROR"],
                },
                "error_summary": {
                    "type": "string",
                    "description": (
                        "One line summarizing the current failure, for feeding into "
                        "the next PLAN call. Empty string when status is PASS."
                    ),
                },
            },
            "required": ["status", "error_summary"],
            "additionalProperties": False,
        },
    },
}

_EVAL_SYSTEM_PROMPT = (
    "You are the EVALUATE step of an autonomous test-fix-verify agent. exit_code is "
    "given directly: if it is 0, status is always PASS regardless of stdout/stderr "
    "noise. If exit_code is non-zero, compare the current stdout/stderr against "
    "prior_error (if given): FAIL_SAME_ERROR means the same root cause is still "
    "failing (the fix didn't work or didn't fully work); FAIL_NEW_ERROR means a "
    "different failure than before (the fix changed what breaks). If prior_error is "
    "null, any failure is FAIL_NEW_ERROR. Always respond by calling the "
    "classify_result tool."
)


def call_evaluator(
    test_stdout: str, test_stderr: str, exit_code: int, prior_error: str | None
) -> dict:
    client = get_client()
    response = _create_with_retry(
        client,
        model=EVAL_MODEL,
        messages=[
            {"role": "system", "content": _EVAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "test_stdout": test_stdout,
                        "test_stderr": test_stderr,
                        "exit_code": exit_code,
                        "prior_error": prior_error,
                    },
                    indent=2,
                ),
            },
        ],
        tools=[_EVAL_TOOL],
        tool_choice={"type": "function", "function": {"name": "classify_result"}},
    )
    return _extract_tool_call_args(response, "classify_result")


# --- REVIEW --------------------------------------------------------------

_REVIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "report_bugs",
        "description": "Report concrete bugs found in the source files. Empty list if none.",
        "parameters": {
            "type": "object",
            "properties": {
                "bugs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Short issue title, under 80 chars."},
                            "file": {"type": "string", "description": "Repo-relative path, exactly as given."},
                            "line": {"type": "integer", "description": "1-based line number of the bug."},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            "description": {
                                "type": "string",
                                "description": "What goes wrong, for which input, and what should happen instead.",
                            },
                            "evidence": {
                                "type": "string",
                                "description": "The offending line(s), copied verbatim from the source.",
                            },
                        },
                        "required": ["title", "file", "line", "severity", "confidence", "description", "evidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["bugs"],
            "additionalProperties": False,
        },
    },
}

_REVIEW_SYSTEM_PROMPT = (
    "You are the code-review step of an autonomous bug-fixing agent. Each finding "
    "you report is filed as a GitHub issue on the owner's repository, so a false "
    "positive costs them time: report only concrete defects you can demonstrate from "
    "the code shown — wrong results, crashes, off-by-one errors, unhandled edge cases "
    "that the code's own intent clearly covers, resource leaks, security bugs. Do NOT "
    "report style, naming, missing docs or type hints, performance nitpicks, or "
    "speculative problems that depend on code you cannot see. Source lines are "
    "prefixed with their line numbers; cite those. known_failures lists problems "
    "already found by failing tests; do not report those again. Returning no bugs is "
    "a good answer for correct code. Always respond by calling the report_bugs tool."
)


def call_reviewer(source_files: dict[str, str], known_failures: list[str]) -> list[dict]:
    """source_files: repo-relative path -> line-numbered content."""
    client = get_client()
    response = _create_with_retry(
        client,
        model=PLAN_MODEL,
        messages=[
            {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"source_files": source_files, "known_failures": known_failures}, indent=2
                ),
            },
        ],
        tools=[_REVIEW_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_bugs"}},
    )
    return _extract_tool_call_args(response, "report_bugs").get("bugs", [])
