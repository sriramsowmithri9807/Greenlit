"""Token and cost accounting for every Nemotron call.

`llm_client` reports each call here; whoever is running (the agent, the
benchmark) installs a listener for the duration of a run with
`track(listener)`. The issue being worked on is attached via `for_issue`,
so the dashboard can show cost per issue as well as per model.

Prices are USD per 1M tokens. The defaults come from public price listings
for Nebius Token Factory (third-party aggregators, not Nebius's own page),
so they're estimates: confirm them in your Token Factory console and
override with GREENLIT_PRICE_ULTRA / GREENLIT_PRICE_NANO="<in>,<out>".
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass

ULTRA_MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"
NANO_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

_DEFAULT_PRICES = {
    "ultra": (1.00, 3.00),
    "nano": (0.06, 0.24),
}


def tier_of(model: str) -> str:
    return "nano" if model == NANO_MODEL else "ultra"


def prices(tier: str) -> tuple[float, float]:
    raw = os.environ.get(f"GREENLIT_PRICE_{tier.upper()}")
    if raw:
        try:
            price_in, price_out = (float(x) for x in raw.split(","))
            return price_in, price_out
        except ValueError:
            pass
    return _DEFAULT_PRICES[tier]


def cost(tier: str, prompt_tokens: int, completion_tokens: int) -> float:
    price_in, price_out = prices(tier)
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


@dataclass
class Usage:
    role: str  # "plan" | "review" | "evaluate" | "write_test" | "judge_test"
    model: str
    tier: str  # "ultra" | "nano"
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_usd: float
    # What this call would have cost on Ultra: the "no tiering" baseline.
    ultra_cost_usd: float
    key: str | None = None  # issue key, when the call was for one issue

    def to_event(self) -> dict:
        return asdict(self)


Listener = Callable[[Usage], None]

_listener: ContextVar[Listener | None] = ContextVar("greenlit_usage_listener", default=None)
_issue: ContextVar[str | None] = ContextVar("greenlit_usage_issue", default=None)


def install(listener: Listener):
    """Like track(), for code that can't use a with-block. Pass the result
    to uninstall()."""
    return _listener.set(listener)


def uninstall(token) -> None:
    _listener.reset(token)


@contextmanager
def track(listener: Listener) -> Iterator[None]:
    token = _listener.set(listener)
    try:
        yield
    finally:
        _listener.reset(token)


@contextmanager
def for_issue(key: str | None) -> Iterator[None]:
    token = _issue.set(key)
    try:
        yield
    finally:
        _issue.reset(token)


def record(role: str, model: str, prompt_tokens: int, completion_tokens: int, latency_ms: int) -> Usage:
    tier = tier_of(model)
    usage = Usage(
        role=role,
        model=model,
        tier=tier,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        cost_usd=cost(tier, prompt_tokens, completion_tokens),
        ultra_cost_usd=cost("ultra", prompt_tokens, completion_tokens),
        key=_issue.get(),
    )
    listener = _listener.get()
    if listener is not None:
        listener(usage)
    return usage


class Tally:
    """Running totals, for the end-of-run summary and the benchmark."""

    def __init__(self) -> None:
        self.calls: list[Usage] = []

    def __call__(self, usage: Usage) -> None:
        self.calls.append(usage)

    def summary(self) -> dict:
        tiers = {}
        for tier in ("ultra", "nano"):
            calls = [u for u in self.calls if u.tier == tier]
            tiers[tier] = {
                "calls": len(calls),
                "prompt_tokens": sum(u.prompt_tokens for u in calls),
                "completion_tokens": sum(u.completion_tokens for u in calls),
                "cost_usd": sum(u.cost_usd for u in calls),
            }
        total = sum(u.cost_usd for u in self.calls)
        ultra_only = sum(u.ultra_cost_usd for u in self.calls)
        return {
            **tiers,
            "total_usd": total,
            "ultra_only_usd": ultra_only,
            "savings_pct": (1 - total / ultra_only) * 100 if ultra_only else 0.0,
        }
