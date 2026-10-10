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

from greenlit import usage
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

PLAN_MODEL = usage.ULTRA_MODEL
EVAL_MODEL = usage.NANO_MODEL

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


def _record_usage(role: str, model: str, response, started: float) -> None:
    tokens = getattr(response, "usage", None)
    usage.record(
        role,
        model,
        getattr(tokens, "prompt_tokens", 0) or 0,
        getattr(tokens, "completion_tokens", 0) or 0,
        int((time.monotonic() - started) * 1000),
    )


def _create_with_retry(client: OpenAI, *, role: str, **kwargs: Any):
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
            _record_usage(role, kwargs["model"], response, started)
            return response
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
        role="plan",
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
        role="evaluate",
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
        role="review",
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


# --- REPRODUCE: write a test that proves a reported bug (Ultra) ------------

_WRITE_TEST_TOOL = {
    "type": "function",
    "function": {
        "name": "write_reproduction_test",
        "description": "Write a pytest test that fails on the current code because of the reported bug.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_code": {
                    "type": "string",
                    "description": "The complete contents of the new test file (imports included).",
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence: what the test checks and why it fails today.",
                },
            },
            "required": ["test_code", "explanation"],
            "additionalProperties": False,
        },
    },
}

_WRITE_TEST_SYSTEM_PROMPT = (
    "You are the REPRODUCE step of an autonomous bug-fixing agent. A code reviewer "
    "reported a bug (issue: title, location, description, evidence). Before anyone "
    "fixes it, prove it: write a small pytest test file that asserts the CORRECT "
    "behaviour the issue describes, so it FAILS on the current code because of this "
    "bug and will PASS once the bug is fixed. Rules: the file will be saved at "
    "test_path, so import the code under test the way example_test does (or relative "
    "to the repository root); use only the standard library and pytest; keep it to "
    "one to three focused test functions named test_*; never import or call anything "
    "that isn't in source_files; no network, no file writes. If prior_attempt is "
    "present, it says why your last test didn't prove the bug; fix that. Always "
    "respond by calling the write_reproduction_test tool."
)


def call_test_writer(context: dict) -> dict:
    """context keys: issue, source_files, test_path, example_test (optional
    {path, content}), prior_attempt (optional str)."""
    client = get_client()
    response = _create_with_retry(
        client,
        role="write_test",
        model=PLAN_MODEL,
        messages=[
            {"role": "system", "content": _WRITE_TEST_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, indent=2)},
        ],
        tools=[_WRITE_TEST_TOOL],
        tool_choice={"type": "function", "function": {"name": "write_reproduction_test"}},
    )
    return _extract_tool_call_args(response, "write_reproduction_test")


# --- REPRODUCE: does the failure actually show the bug? (Nano) -------------

_JUDGE_TEST_TOOL = {
    "type": "function",
    "function": {
        "name": "judge_reproduction",
        "description": "Decide whether a failing test demonstrates the reported bug.",
        "parameters": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["REPRODUCES_BUG", "TEST_IS_BROKEN"]},
                "reason": {"type": "string", "description": "One line."},
            },
            "required": ["verdict", "reason"],
            "additionalProperties": False,
        },
    },
}

_JUDGE_TEST_SYSTEM_PROMPT = (
    "You check a test written to reproduce a reported bug. It ran against the "
    "current code and failed. REPRODUCES_BUG: the failure is the behaviour the issue "
    "describes (a wrong value in an assertion, or the crash/exception the issue "
    "reports). TEST_IS_BROKEN: the test failed for its own reasons, e.g. ImportError, "
    "NameError, AttributeError on something that doesn't exist, a syntax error, a "
    "fixture error, or an assertion about behaviour the issue never mentions. Always "
    "respond by calling the judge_reproduction tool."
)


def call_repro_judge(issue: dict, test_code: str, test_output: str) -> dict:
    client = get_client()
    response = _create_with_retry(
        client,
        role="judge_test",
        model=EVAL_MODEL,
        messages=[
            {"role": "system", "content": _JUDGE_TEST_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"issue": issue, "test_code": test_code, "test_output": test_output[-6000:]}, indent=2
                ),
            },
        ],
        tools=[_JUDGE_TEST_TOOL],
        tool_choice={"type": "function", "function": {"name": "judge_reproduction"}},
    )
    return _extract_tool_call_args(response, "judge_reproduction")
