import type { GreenlitEvent } from '@/types/events'

export interface TimedEvent {
  event: GreenlitEvent
  /** Delay in ms before this event fires, relative to the previous one. */
  delay: number
}

const DIFF_1 = `--- a/app.py
+++ b/app.py
@@ -1,4 +1,5 @@
+greeting = "Hello, Greenlit"
 def main():
     print(greeting)

 main()
`

const DIFF_2 = `--- a/app.py
+++ b/app.py
@@ -1,6 +1,6 @@
-def main():
-    print(greeting)
+def main():
+    greeting = build_greeting()
+    print(greeting)

 main()
`

function ev(event: GreenlitEvent, delay: number): TimedEvent {
  return { event, delay }
}

export const SUCCESS_SCENARIO: TimedEvent[] = [
  ev({ type: 'status', value: 'failing' }, 0),
  ev({ type: 'iteration', count: 1 }, 400),

  ev({ type: 'stage_start', stage: 'perceive' }, 500),
  ev({ type: 'log_line', text: '$ pytest -q' }, 300),
  ev({ type: 'log_line', text: 'FAILED test_app.py::test_greeting - NameError' }, 350),
  ev({ type: 'log_line', text: 'Captured stack trace + app.py (3 lines touched)' }, 400),
  ev({ type: 'stage_end', stage: 'perceive' }, 500),

  ev({ type: 'status', value: 'testing' }, 200),
  ev({ type: 'stage_start', stage: 'plan' }, 400),
  ev({ type: 'log_line', text: 'PLAN (Nemotron Ultra): reasoning about root cause…' }, 500),
  ev({ type: 'log_line', text: "root cause: `greeting` referenced before assignment" }, 700),
  ev({ type: 'stage_end', stage: 'plan', result: { unfamiliar_api: false } }, 500),

  ev({ type: 'stage_start', stage: 'act' }, 400),
  ev({ type: 'diff_ready', diff: DIFF_1 }, 300),
  ev({ type: 'log_line', text: 'ACT: staging throwaway copy into Sandbox' }, 400),
  ev({ type: 'log_line', text: 'ACT: running `pytest -q` inside sandbox' }, 600),
  ev({ type: 'stage_end', stage: 'act' }, 500),

  ev({ type: 'stage_start', stage: 'evaluate' }, 400),
  ev({ type: 'log_line', text: 'EVALUATE (Nemotron Nano): classifying sandbox result…' }, 500),
  ev(
    { type: 'stage_end', stage: 'evaluate', result: { status: 'FAIL_SAME_ERROR' } },
    500,
  ),
  ev({ type: 'log_line', text: 'FAIL_SAME_ERROR: NameError persists on app.py:3' }, 400),

  ev({ type: 'iteration', count: 2 }, 700),

  ev({ type: 'stage_start', stage: 'plan' }, 500),
  ev(
    { type: 'log_line', text: "PLAN: prior diff didn't address it, reconsidering approach" },
    500,
  ),
  ev(
    { type: 'stage_end', stage: 'plan', result: { unfamiliar_api: true } },
    500,
  ),

  ev({ type: 'stage_start', stage: 'research' }, 400),
  ev(
    { type: 'log_line', text: 'RESEARCH (Tavily): querying "build_greeting helper changelog"' },
    600,
  ),
  ev({ type: 'log_line', text: 'Found doc reference, feeding context back into PLAN' }, 500),
  ev({ type: 'stage_end', stage: 'research' }, 400),

  ev({ type: 'stage_start', stage: 'act' }, 400),
  ev({ type: 'diff_ready', diff: DIFF_2 }, 300),
  ev({ type: 'log_line', text: 'ACT: applying revised diff, running sandboxed pytest' }, 600),
  ev({ type: 'stage_end', stage: 'act' }, 500),

  ev({ type: 'stage_start', stage: 'evaluate' }, 400),
  ev({ type: 'log_line', text: 'EVALUATE (Nemotron Nano): classifying sandbox result…' }, 500),
  ev({ type: 'stage_end', stage: 'evaluate', result: { status: 'PASS' } }, 500),
  ev({ type: 'log_line', text: 'PASS: 3 passed in 0.09s' }, 400),
  ev({ type: 'status', value: 'fixed' }, 500),
]

const DIFF_ATTEMPT = (n: number) => `--- a/app.py
+++ b/app.py
@@ -1,3 +1,3 @@
-def main():
-    print(greeting)
+def main():
+    print(greeting)  # attempt ${n}, still wrong
`

function unresolvedAttempt(n: number, isLast: boolean): TimedEvent[] {
  return [
    ev({ type: 'stage_start', stage: 'plan' }, n === 1 ? 400 : 500),
    ev({ type: 'log_line', text: `PLAN (Nemotron Ultra): attempt ${n}, revising hypothesis` }, 500),
    ev({ type: 'stage_end', stage: 'plan', result: { unfamiliar_api: false } }, 500),

    ev({ type: 'stage_start', stage: 'act' }, 400),
    ev({ type: 'diff_ready', diff: DIFF_ATTEMPT(n) }, 300),
    ev({ type: 'log_line', text: 'ACT: running sandboxed pytest' }, 600),
    ev({ type: 'stage_end', stage: 'act' }, 500),

    ev({ type: 'stage_start', stage: 'evaluate' }, 400),
    ev(
      {
        type: 'stage_end',
        stage: 'evaluate',
        result: { status: n === 1 ? 'FAIL_NEW_ERROR' : 'FAIL_SAME_ERROR' },
      },
      500,
    ),
    ev({ type: 'log_line', text: `FAIL: attempt ${n} did not fix the test` }, 400),
    ...(isLast ? [] : [ev({ type: 'iteration', count: n + 1 } as GreenlitEvent, 700)]),
  ]
}

export const UNRESOLVED_SCENARIO: TimedEvent[] = [
  ev({ type: 'status', value: 'failing' }, 0),
  ev({ type: 'iteration', count: 1 }, 400),

  ev({ type: 'stage_start', stage: 'perceive' }, 500),
  ev({ type: 'log_line', text: '$ pytest -q' }, 300),
  ev({ type: 'log_line', text: 'FAILED test_parser.py::test_parse_edge_case' }, 350),
  ev({ type: 'stage_end', stage: 'perceive' }, 500),
  ev({ type: 'status', value: 'testing' }, 200),

  ...unresolvedAttempt(1, false),
  ...unresolvedAttempt(2, false),
  ...unresolvedAttempt(3, true),

  ev({ type: 'log_line', text: 'Max iterations (3) reached without a passing run' }, 500),
  ev({ type: 'status', value: 'unresolved' }, 400),
]
