# Greenlit Dashboard

The live orchestration UI (build-order step 5). Single page: an animated
React Flow pipeline (Perceive → Plan → Research → Act → Evaluate → Loop),
a syntax-highlighted diff viewer, an auto-scrolling log panel, an iteration
counter, and a status badge.

## Run

```bash
npm install
npm run dev
```

Opens at `http://localhost:5173/`.

## Mock mode vs live backend

By default (`VITE_SSE_URL` unset) the page drives itself off a local mock
event replayer — two dev-only buttons top-right ("Success run" /
"Unresolved run") fire a full scripted event sequence on a timer. This is
how the UI was built and polished before any backend existed.

To point at the real backend once it's ready, set one env var:

```bash
echo "VITE_SSE_URL=http://localhost:8000/events" > .env.local
```

`useGreenlitStream` ([src/hooks/useGreenlitStream.ts](src/hooks/useGreenlitStream.ts))
switches to a real `EventSource` automatically when this is set, and the
mock replay buttons stop rendering (`ScenarioControls` is mock-only, see
its docstring). No other code changes needed.

## Event contract

The backend must emit these six named SSE events (see
[src/types/events.ts](src/types/events.ts) for the exact payload shapes):
`stage_start`, `stage_end`, `log_line`, `diff_ready`, `iteration`, `status`.
