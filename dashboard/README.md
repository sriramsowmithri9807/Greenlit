# Greenlit dashboard

The web UI: a start screen (repo URL + optional token), then a live view of
the run: phase stepper, issues as they're raised and fixed, the per-issue
PERCEIVE → PLAN → RESEARCH → ACT → EVALUATE → LOOP pipeline, the current
diff, the log, and the resulting pull request.

## Development

```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to the backend on :8000
```

Run the backend alongside it with `python -m greenlit.server` from the repo
root. For production, `npm run build` and the backend serves `dist/` itself at
http://127.0.0.1:8000.

## Demo mode

`http://localhost:5173/?mock=1` replays a scripted run, and `?mock=partial`
replays one where an issue can't be fixed. No backend or credentials are
needed. The UI labels it as a scripted demo. Leave the token empty to see the
dry-run flavour, or fill anything in for the live flavour.

## Event contract

[src/types/events.ts](src/types/events.ts) mirrors the events emitted by
`greenlit/agent.py` and `greenlit/orchestrator.py`, delivered over SSE from
`GET /api/runs/{id}/events`. The stream resumes via `Last-Event-ID` and ends
with an `end` event.
