"""HTTP API: validation, SSE streaming, resume, and that the token never
comes back out."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from greenlit import server

TOKEN = "github_pat_SERVERSECRET"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("NEBIUS_AI_PROJECT", "p")
    server._runs.clear()
    return TestClient(server.app)


def _sse(response) -> list[tuple[str | None, str, dict]]:
    events, event_id, event_type, data = [], None, None, None
    for line in response.iter_lines():
        if line.startswith("id: "):
            event_id = line[4:]
        elif line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
        elif line == "" and event_type:
            events.append((event_id, event_type, data))
            event_id = event_type = data = None
    return events


def _wait_done(run_id: str) -> None:
    for _ in range(100):
        if server._runs[run_id].done:
            return
        time.sleep(0.02)
    raise AssertionError("run never finished")


def test_health_reports_configuration(client, monkeypatch):
    assert client.get("/api/health").json() == {"nebius_configured": True, "tavily_configured": False}
    monkeypatch.delenv("NEBIUS_API_KEY")
    assert client.get("/api/health").json()["nebius_configured"] is False


def test_start_refuses_without_nebius_credentials(client, monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY")
    response = client.post("/api/runs", json={"repo_url": "octo/calc"})
    assert response.status_code == 503 and "NEBIUS_API_KEY" in response.json()["detail"]


@pytest.mark.parametrize("url", ["https://gitlab.com/a/b", "/etc", "../../x", ""])
def test_start_rejects_non_github_urls_including_local_paths(client, url):
    assert client.post("/api/runs", json={"repo_url": url}).status_code == 400


def test_events_stream_in_order_and_end(client, monkeypatch):
    seen_args = {}

    def fake_agent(repo_url, token, *, include_review, emit):
        seen_args.update(repo_url=repo_url, token=token, include_review=include_review)
        emit("phase", {"value": "clone"})
        emit("log_line", {"text": "hello"})
        emit("status", {"value": "clean"})

    monkeypatch.setattr(server.agent, "run_agent", fake_agent)
    run_id = client.post(
        "/api/runs", json={"repo_url": "https://github.com/octo/calc", "token": TOKEN, "include_review": False}
    ).json()["run_id"]
    _wait_done(run_id)

    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _sse(response)

    assert [(i, t) for i, t, _ in events] == [("0", "phase"), ("1", "log_line"), ("2", "status"), (None, "end")]
    assert seen_args == {"repo_url": "https://github.com/octo/calc", "token": TOKEN, "include_review": False}
    assert TOKEN not in json.dumps([p for _, _, p in events])
    assert not hasattr(server._runs[run_id], "token")


def test_reconnect_resumes_after_last_event_id(client, monkeypatch):
    def fake_agent(repo_url, token, *, include_review, emit):
        for i in range(5):
            emit("log_line", {"text": f"line {i}"})

    monkeypatch.setattr(server.agent, "run_agent", fake_agent)
    run_id = client.post("/api/runs", json={"repo_url": "octo/calc"}).json()["run_id"]
    _wait_done(run_id)

    with client.stream("GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "2"}) as response:
        events = _sse(response)
    assert [p["text"] for _, t, p in events if t == "log_line"] == ["line 3", "line 4"]


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope/events").status_code == 404


def test_concurrent_run_limit(client, monkeypatch):
    import threading

    release = threading.Event()
    monkeypatch.setattr(server.agent, "run_agent", lambda *a, **k: release.wait(5))
    try:
        for _ in range(server.MAX_ACTIVE_RUNS):
            assert client.post("/api/runs", json={"repo_url": "octo/calc"}).status_code == 200
        assert client.post("/api/runs", json={"repo_url": "octo/calc"}).status_code == 429
    finally:
        release.set()
