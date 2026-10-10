"""Cost accounting: every Nemotron call is metered, priced per tier, and
attributed to the issue it was for."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from greenlit import llm_client, usage


def _response(tool: str, args: dict, prompt_tokens: int, completion_tokens: int, model: str):
    call = SimpleNamespace(function=SimpleNamespace(name=tool, arguments=json.dumps(args)))
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None), finish_reason="tool_calls")],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


class FakeClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response))


@pytest.fixture(autouse=True)
def fixed_prices(monkeypatch):
    monkeypatch.setenv("GREENLIT_PRICE_ULTRA", "1.0,3.0")
    monkeypatch.setenv("GREENLIT_PRICE_NANO", "0.06,0.24")


def test_planner_call_is_metered_as_ultra_and_tagged_with_the_issue():
    response = _response(
        "propose_fix", {"diff": "d", "rationale": "r", "unfamiliar_api": False, "unfamiliar_api_query": None},
        2_000_000, 1_000_000, usage.ULTRA_MODEL,
    )
    calls = []
    with patch.object(llm_client, "get_client", lambda: FakeClient(response)), usage.track(calls.append):
        with usage.for_issue("test:t.py::test_x"):
            llm_client.call_planner({"stack_trace": "x"})

    (call,) = calls
    assert (call.role, call.tier, call.key) == ("plan", "ultra", "test:t.py::test_x")
    assert call.cost_usd == pytest.approx(2 * 1.0 + 1 * 3.0)


def test_evaluator_call_is_metered_as_nano_with_its_ultra_counterfactual():
    response = _response("classify_result", {"status": "PASS", "error_summary": ""}, 1_000_000, 1_000_000, usage.NANO_MODEL)
    calls = []
    with patch.object(llm_client, "get_client", lambda: FakeClient(response)), usage.track(calls.append):
        llm_client.call_evaluator("", "", 0, None)

    (call,) = calls
    assert call.tier == "nano" and call.role == "evaluate"
    assert call.cost_usd == pytest.approx(0.30) and call.ultra_cost_usd == pytest.approx(4.0)


def test_summary_reports_savings_versus_ultra_only():
    tally = usage.Tally()
    with usage.track(tally):
        usage.record("plan", usage.ULTRA_MODEL, 1_000_000, 0, 10)  # $1.00
        for _ in range(9):
            usage.record("evaluate", usage.NANO_MODEL, 1_000_000, 0, 10)  # $0.06 each, $1.00 on Ultra
    summary = tally.summary()
    assert summary["ultra"]["calls"] == 1 and summary["nano"]["calls"] == 9
    assert summary["total_usd"] == pytest.approx(1.54)
    assert summary["ultra_only_usd"] == pytest.approx(10.0)
    assert summary["savings_pct"] == pytest.approx(84.6)


def test_nothing_is_recorded_without_a_listener_and_listeners_dont_leak_across_threads():
    usage.record("plan", usage.ULTRA_MODEL, 1, 1, 1)  # no listener: no error, nowhere to go
    seen = []
    with usage.track(seen.append):
        thread = threading.Thread(target=lambda: usage.record("plan", usage.ULTRA_MODEL, 1, 1, 1))
        thread.start()
        thread.join()
    assert seen == []  # a plain thread doesn't inherit the run's context (greenlit.parallel copies it explicitly)


def test_price_override_is_validated(monkeypatch):
    monkeypatch.setenv("GREENLIT_PRICE_ULTRA", "not,numbers")
    assert usage.prices("ultra") == (1.00, 3.00)
