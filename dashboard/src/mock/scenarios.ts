import type { GreenlitEvent, Stage, StageResult } from '@/types/events'

/** A scripted run (?mock=1 in the URL) that exercises every event type the
 * real backend emits, for building/recording the UI without credentials.
 * It is labelled as a scripted demo in the UI; nothing is sent anywhere. */

export interface TimedEvent {
  event: GreenlitEvent
  /** Delay in ms before this event fires, relative to the previous one. */
  delay: number
}

export interface MockOptions {
  repoFullName: string
  live: boolean
  /** Leave the code-review issue unfixed, to exercise the partial path. */
  partial: boolean
}

const ADD_DIFF = `--- a/calculator.py
+++ b/calculator.py
@@ -1,5 +1,5 @@
 def add(a, b):
-    return a - b
+    return a + b


 def divide(a, b):
`

const AVG_ATTEMPT_1 = `--- a/calculator.py
+++ b/calculator.py
@@ -8,2 +8,2 @@
 def average(numbers):
-    return sum(numbers) / len(numbers) + 1
+    return round(sum(numbers) / len(numbers) + 1)
`

const AVG_FIX = `--- a/calculator.py
+++ b/calculator.py
@@ -1,3 +1,6 @@
+import statistics
+
+
 def add(a, b):
     return a + b

@@ -8,2 +11,2 @@
 def average(numbers):
-    return sum(numbers) / len(numbers) + 1
+    return statistics.fmean(numbers)
`

const DIVIDE_FIX = `--- a/calculator.py
+++ b/calculator.py
@@ -7,3 +7,5 @@

 def divide(a, b):
+    if b == 0:
+        raise ValueError("cannot divide by zero")
     return a / b
`

const COMBINED_ALL = `--- a/calculator.py
+++ b/calculator.py
@@ -1,9 +1,14 @@
+import statistics
+
+
 def add(a, b):
-    return a - b
+    return a + b
 
 
 def divide(a, b):
+    if b == 0:
+        raise ValueError("cannot divide by zero")
     return a / b
 
 
 def average(numbers):
-    return sum(numbers) / len(numbers) + 1
+    return statistics.fmean(numbers)
`

/** Only the two fixes that passed verification in the partial run. */
const COMBINED_PARTIAL = `--- a/calculator.py
+++ b/calculator.py
@@ -1,9 +1,12 @@
+import statistics
+
+
 def add(a, b):
-    return a - b
+    return a + b
 
 
 def divide(a, b):
     return a / b
 
 
 def average(numbers):
-    return sum(numbers) / len(numbers) + 1
+    return statistics.fmean(numbers)
`

export function buildMockRun({ repoFullName, live, partial }: MockOptions): TimedEvent[] {
  const url = `https://github.com/${repoFullName}`
  const out: TimedEvent[] = []
  const at = (delay: number, event: GreenlitEvent) => out.push({ delay, event })
  const log = (delay: number, text: string) => at(delay, { type: 'log_line', text })
  const stage = (delay: number, kind: 'stage_start' | 'stage_end', s: Stage, result?: StageResult) =>
    at(delay, kind === 'stage_start' ? { type: 'stage_start', stage: s } : { type: 'stage_end', stage: s, result })

  const issues = [
    { key: 'test:test_calculator.py::test_add', kind: 'test' as const, title: 'test_add fails: assert -1 == 5', location: 'test_calculator.py::test_add', severity: null },
    { key: 'test:test_calculator.py::test_average', kind: 'test' as const, title: 'test_average fails: assert 3.0 == 2', location: 'test_calculator.py::test_average', severity: null },
    { key: 'review:1', kind: 'review' as const, title: 'divide() crashes with ZeroDivisionError when b is 0', location: 'calculator.py:6', severity: 'medium' },
  ]
  const numberOf = (i: number) => (live ? 12 + i : null)
  const ref = (i: number) => (live ? `#${12 + i}` : issues[i].key)

  // clone
  at(0, { type: 'status', value: 'scanning' })
  at(200, { type: 'phase', value: 'clone' })
  at(300, { type: 'repo', full_name: repoFullName, url, default_branch: 'main', mode: live ? 'live' : 'dry_run' })
  log(900, `Cloned ${repoFullName} (main)`)

  // scan
  at(400, { type: 'phase', value: 'scan' })
  log(300, 'Running the test suite in a Nebius Token Factory sandbox')
  log(1600, 'Test suite: 2 failing')
  log(400, 'Code review (Nemotron Ultra) over 1 file(s)')
  log(2000, 'Code review: 1 credible bug(s), 2 low-confidence finding(s) dropped')

  // raise
  at(500, { type: 'phase', value: 'raise' })
  issues.forEach((issue, i) =>
    at(i === 0 ? 400 : 350, {
      type: 'issue_raised',
      ...issue,
      number: numberOf(i),
      url: live ? `${url}/issues/${12 + i}` : null,
    }),
  )
  log(300, live ? `Raised 3 issue(s) on ${repoFullName}` : 'Dry run: not raising issues on GitHub (no token)')

  // fix
  at(600, { type: 'phase', value: 'fix' })
  at(100, { type: 'status', value: 'testing' })

  const commit = (i: number, title: string, sha: string) => {
    if (!live) return
    at(400, { type: 'commit', key: issues[i].key, sha, message: `Fix ${ref(i)}: ${title}`, url: `${url}/commit/${sha}` })
  }

  // issue 1: fixed first try
  at(500, { type: 'issue_start', key: issues[0].key, remaining: 3 })
  stage(300, 'stage_start', 'perceive')
  log(700, 'PERCEIVE: reproduced test_calculator.py::test_add in the sandbox')
  stage(300, 'stage_end', 'perceive')
  at(200, { type: 'iteration', count: 1 })
  stage(200, 'stage_start', 'plan')
  log(1300, 'PLAN (Nemotron Ultra): add() subtracts b instead of adding it; the test expects add(2, 3) == 5.')
  stage(300, 'stage_end', 'plan', { unfamiliar_api: false })
  at(200, { type: 'diff_ready', diff: ADD_DIFF })
  stage(400, 'stage_start', 'act')
  log(500, 'ACT: patched calculator.py, running it in the sandbox')
  stage(1200, 'stage_end', 'act')
  stage(200, 'stage_start', 'evaluate')
  log(700, 'EVALUATE (Nemotron Nano): test_calculator.py::test_add passes, checking the full suite')
  stage(900, 'stage_end', 'evaluate', { status: 'PASS' })
  commit(0, issues[0].title, 'a1f3c9e7b2d4')
  at(300, { type: 'issue_end', key: issues[0].key, status: 'fixed' })

  // issue 2: wrong first attempt, research, then fixed
  at(700, { type: 'issue_start', key: issues[1].key, remaining: 2 })
  stage(300, 'stage_start', 'perceive')
  log(700, 'PERCEIVE: reproduced test_calculator.py::test_average in the sandbox')
  stage(300, 'stage_end', 'perceive')
  at(200, { type: 'iteration', count: 1 })
  stage(200, 'stage_start', 'plan')
  log(1300, 'PLAN (Nemotron Ultra): average() looks off by a rounding issue; round the result.')
  stage(300, 'stage_end', 'plan', { unfamiliar_api: false })
  at(200, { type: 'diff_ready', diff: AVG_ATTEMPT_1 })
  stage(400, 'stage_start', 'act')
  log(500, 'ACT: patched calculator.py, running it in the sandbox')
  stage(1200, 'stage_end', 'act')
  stage(200, 'stage_start', 'evaluate')
  log(700, 'EVALUATE (Nemotron Nano): FAIL_SAME_ERROR, assert 3 == 2 (the +1 is still there)')
  stage(500, 'stage_end', 'evaluate', { status: 'FAIL_SAME_ERROR' })
  at(500, { type: 'iteration', count: 2 })
  stage(300, 'stage_start', 'plan')
  log(1200, 'PLAN (Nemotron Ultra): the +1 is the bug; checking whether statistics.fmean is safe on 3.9+.')
  stage(300, 'stage_end', 'plan', { unfamiliar_api: true })
  stage(300, 'stage_start', 'research')
  log(300, 'RESEARCH (Tavily): "python statistics.fmean availability and behaviour"')
  log(1300, 'Found relevant docs, feeding them back into PLAN')
  stage(300, 'stage_end', 'research')
  stage(300, 'stage_start', 'plan')
  log(1100, 'PLAN (Nemotron Ultra, with docs): drop the stray +1 and use statistics.fmean (3.8+).')
  stage(300, 'stage_end', 'plan', { unfamiliar_api: false })
  at(200, { type: 'diff_ready', diff: AVG_FIX })
  stage(400, 'stage_start', 'act')
  log(500, 'ACT: patched calculator.py, running it in the sandbox')
  stage(1200, 'stage_end', 'act')
  stage(200, 'stage_start', 'evaluate')
  log(700, 'EVALUATE (Nemotron Nano): test_calculator.py::test_average passes, checking the full suite')
  stage(900, 'stage_end', 'evaluate', { status: 'PASS' })
  commit(1, issues[1].title, 'c7d20e14f98a')
  at(300, { type: 'issue_end', key: issues[1].key, status: 'fixed' })

  // issue 3: code-review finding
  at(700, { type: 'issue_start', key: issues[2].key, remaining: 1 })
  stage(300, 'stage_start', 'perceive')
  log(500, 'PERCEIVE: loaded calculator.py:6 for the reported bug')
  stage(300, 'stage_end', 'perceive')
  const attempts = partial ? 3 : 1
  for (let n = 1; n <= attempts; n += 1) {
    at(n === 1 ? 200 : 500, { type: 'iteration', count: n })
    stage(200, 'stage_start', 'plan')
    log(1200, 'PLAN (Nemotron Ultra): guard b == 0 and raise a ValueError with a clear message.')
    stage(300, 'stage_end', 'plan', { unfamiliar_api: false })
    at(200, { type: 'diff_ready', diff: DIVIDE_FIX })
    stage(400, 'stage_start', 'act')
    log(500, 'ACT: patched calculator.py, running it in the sandbox')
    stage(1100, 'stage_end', 'act')
    stage(200, 'stage_start', 'evaluate')
    if (partial) {
      log(700, 'EVALUATE: rejected, it made previously-passing tests fail: test_calculator.py::test_divide_by_zero_returns_inf')
      stage(400, 'stage_end', 'evaluate', { status: 'REGRESSION' })
    } else {
      log(700, 'EVALUATE: compiles, and no test that passed before fails now')
      stage(700, 'stage_end', 'evaluate', { status: 'PASS' })
    }
  }
  if (!partial) commit(2, issues[2].title, 'e40b8a61c3f7')
  at(300, { type: 'issue_end', key: issues[2].key, status: partial ? 'unresolved' : 'fixed' })

  // publish
  at(700, { type: 'phase', value: 'publish' })
  if (live) {
    at(1000, { type: 'pr_opened', number: 15, url: `${url}/pull/15` })
  } else {
    at(600, { type: 'diff_ready', diff: partial ? COMBINED_PARTIAL : COMBINED_ALL })
    log(200, `Dry run complete: ${partial ? 2 : 3} fix(es) verified in the sandbox, nothing pushed. Add a token to raise issues and open a pull request.`)
  }
  at(400, { type: 'status', value: partial ? 'partial' : 'fixed' })
  at(100, { type: 'phase', value: 'done' })
  return out
}
