"""HTTP server: start agent runs, stream their events, serve the dashboard.

    POST /api/runs               {repo_url, token?, include_review?} -> {run_id}
    GET  /api/runs/{id}/events   Server-Sent Events, resumable via Last-Event-ID
    GET  /api/health             which credentials the server has configured
    GET  /                       the built dashboard (dashboard/dist), if present

The user's GitHub token is handed straight to the run's worker thread. It
isn't stored on the Run, logged, or echoed back in any event.

Run with: python -m greenlit.server  (binds 127.0.0.1:8000 by default)
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from greenlit import agent
from greenlit.github import parse_repo_url

MAX_ACTIVE_RUNS = 2
MAX_KEPT_RUNS = 20
_POLL_SECONDS = 0.15
_HEARTBEAT_SECONDS = 15
DASHBOARD_DIST = Path(__file__).resolve().parent.parent / "dashboard" / "dist"


class Run:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.events: list[tuple[str, dict]] = []
        self.done = False
        self._lock = threading.Lock()

    def emit(self, event_type: str, payload: dict) -> None:
        with self._lock:
            self.events.append((event_type, payload))

    def snapshot_from(self, index: int) -> list[tuple[int, str, dict]]:
        with self._lock:
            return [(i, *self.events[i]) for i in range(index, len(self.events))]


class RunRequest(BaseModel):
    repo_url: str
    token: str | None = None
    include_review: bool = True


app = FastAPI(title="Greenlit")
_runs: dict[str, Run] = {}


def _nebius_configured() -> bool:
    return bool(os.environ.get("NEBIUS_API_KEY") and os.environ.get("NEBIUS_AI_PROJECT"))


@app.get("/api/health")
def health() -> dict:
    return {
        "nebius_configured": _nebius_configured(),
        "tavily_configured": bool(os.environ.get("TAVILY_API_KEY")),
    }


@app.post("/api/runs")
def start_run(request: RunRequest) -> dict:
    if not _nebius_configured():
        raise HTTPException(
            status_code=503,
            detail="This Greenlit server has no Nebius credentials. Set NEBIUS_API_KEY and "
            "NEBIUS_AI_PROJECT in its .env and restart it.",
        )
    try:
        parse_repo_url(request.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if sum(not r.done for r in _runs.values()) >= MAX_ACTIVE_RUNS:
        raise HTTPException(status_code=429, detail="Greenlit is busy with other runs. Try again in a few minutes.")

    run = Run()
    _runs[run.id] = run
    for stale_id in [rid for rid, r in _runs.items() if r.done][: max(0, len(_runs) - MAX_KEPT_RUNS)]:
        del _runs[stale_id]

    repo_url, token, include_review = request.repo_url, request.token, request.include_review

    def work() -> None:
        try:
            agent.run_agent(repo_url, token, include_review=include_review, emit=run.emit)
        finally:
            run.done = True

    threading.Thread(target=work, name=f"greenlit-run-{run.id}", daemon=True).start()
    return {"run_id": run.id}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")

    last_event_id = request.headers.get("last-event-id")
    start = int(last_event_id) + 1 if last_event_id and last_event_id.isdigit() else 0

    async def stream():
        index = start
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            batch = run.snapshot_from(index)
            for event_id, event_type, payload in batch:
                yield f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(payload)}\n\n"
            index += len(batch)
            if batch:
                idle = 0.0
            if run.done and not run.snapshot_from(index):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(_POLL_SECONDS)
            idle += _POLL_SECONDS
            if idle >= _HEARTBEAT_SECONDS:
                yield ": keepalive\n\n"
                idle = 0.0

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if DASHBOARD_DIST.is_dir():
    app.mount("/", StaticFiles(directory=DASHBOARD_DIST, html=True), name="dashboard")


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("GREENLIT_HOST", "127.0.0.1"),
        port=int(os.environ.get("GREENLIT_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
