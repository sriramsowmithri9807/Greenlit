import type { GreenlitEvent, LaneEventType, Stage, StageResult, Tier, UsageEvent } from '@/types/events'
import { summarize } from './changes'

/** A scripted run (?mock=1 in the URL) that exercises every event type the
 * real backend emits, for building/recording the UI without credentials.
 * It is labelled as a scripted demo in the UI; nothing is sent anywhere.
 * Token counts are illustrative; costs use the same per-token prices as
 * greenlit/usage.py. */

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
@@ -9,2 +9,2 @@
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

@@ -9,2 +12,2 @@
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

const DIVIDE_TEST = `--- /dev/null
+++ b/test_greenlit_review_1.py
@@ -0,0 +1,8 @@
+import pytest
+
+from calculator import divide
+
+
+def test_divide_by_zero_raises_value_error():
+    with pytest.raises(ValueError):
+        divide(1, 0)
`
const DIVIDE_TEST_CODE = DIVIDE_TEST.split('\n')
  .filter((l) => l.startsWith('+') && !l.startsWith('+++'))
  .map((l) => l.slice(1))
  .join('\n')

const ISSUES = [
  { key: 'test:test_calculator.py::test_add', kind: 'test' as const, title: 'test_add fails: assert -1 == 5', location: 'test_calculator.py::test_add', severity: null },
  { key: 'test:test_calculator.py::test_average', kind: 'test' as const, title: 'test_average fails: assert 3.0 == 2', location: 'test_calculator.py::test_average', severity: null },
  { key: 'review:1', kind: 'review' as const, title: 'divide() crashes with ZeroDivisionError when b is 0', location: 'calculator.py:6', severity: 'medium' },
  { key: 'review:2', kind: 'review' as const, title: 'add() loses precision for large integers', location: 'calculator.py:2', severity: 'medium' },
]
const BRANCH = 'greenlit/fix-20261008-101500'
const PRICES: Record<Tier, [number, number]> = { ultra: [1.0, 3.0], nano: [0.06, 0.24] }

function usageEvent(role: UsageEvent['role'], tier: Tier, prompt: number, completion: number, key: string | null): GreenlitEvent {
  const price = (t: Tier) => (prompt * PRICES[t][0] + completion * PRICES[t][1]) / 1_000_000
  return {
    type: 'usage',
    role,
    tier,
    model: tier === 'ultra' ? 'nvidia/Nemotron-3-Ultra-550b-a55b' : 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
    prompt_tokens: prompt,
    completion_tokens: completion,
    latency_ms: tier === 'ultra' ? 4200 : 600,
    cost_usd: price(tier),
    ultra_cost_usd: price('ultra'),
    key,
  }
}

function mockChanges(partial: boolean) {
  const fixes = [
    { ...ISSUES[0], diff: ADD_DIFF },
    { ...ISSUES[1], diff: AVG_FIX },
    ...(partial ? [] : [{ ...ISSUES[2], diff: DIVIDE_FIX + DIVIDE_TEST }]),
  ]
  return summarize(fixes.map(({ key, title, location, diff }) => ({ key, title, location, diff })))
}

/** Events on an absolute timeline (ms), so parallel lanes can interleave. */
class Timeline {
  private items: { t: number; n: number; event: GreenlitEvent }[] = []
  private n = 0
  at(t: number, event: GreenlitEvent) {
    this.items.push({ t, n: this.n++, event })
  }
  end(): number {
    return this.items.reduce((max, item) => Math.max(max, item.t), 0)
  }
  toTimed(): TimedEvent[] {
    let last = 0
    return [...this.items]
      .sort((a, b) => a.t - b.t || a.n - b.n)
      .map(({ t, event }) => {
        const delay = t - last
        last = t
        return { delay, event }
      })
  }
}

/** Script one sandbox lane: every call advances its own clock. */
function lane(tl: Timeline, issue: (typeof ISSUES)[number], start: number) {
  let t = start
  const short = issue.title.length > 40 ? `${issue.title.slice(0, 37)}...` : issue.title
  const ev = (dt: number, event: LaneEventType, data: Record<string, unknown>) => {
    t += dt
    tl.at(t, { type: 'lane', key: issue.key, event, data })
  }
  return {
    get t() {
      return t
    },
    stage(dt: number, stage: Stage, result?: StageResult) {
      ev(dt, result === undefined ? 'stage_start' : 'stage_end', result === undefined ? { stage } : { stage, result })
    },
    end(dt: number, stage: Stage, result: StageResult = {}) {
      ev(dt, 'stage_end', { stage, result })
    },
    iteration(dt: number, count: number) {
      ev(dt, 'iteration', { count })
    },
    diff(dt: number, diff: string) {
      ev(dt, 'diff_ready', { diff })
    },
    log(dt: number, text: string) {
      ev(dt, 'log_line', { text })
      tl.at(t, { type: 'log_line', text: `[${short}] ${text}` })
    },
    usage(role: UsageEvent['role'], tier: Tier, prompt: number, completion: number) {
      tl.at(t, usageEvent(role, tier, prompt, completion, issue.key))
    },
    raw(dt: number, event: GreenlitEvent) {
      t += dt
      tl.at(t, event)
    },
  }
}

/** Everything up to the publish question (live), or the whole run (dry run). */
export function buildMockRun({ repoFullName, live, partial }: MockOptions): TimedEvent[] {
  const url = `https://github.com/${repoFullName}`
  const tl = new Timeline()
  let t = 0
  const at = (dt: number, event: GreenlitEvent) => {
    t += dt
    tl.at(t, event)
  }
  const log = (dt: number, text: string) => at(dt, { type: 'log_line', text })

  // clone + scan
  at(0, { type: 'status', value: 'scanning' })
  at(200, { type: 'phase', value: 'clone' })
  at(300, { type: 'repo', full_name: repoFullName, url, default_branch: 'main', mode: live ? 'live' : 'dry_run' })
  log(800, `Cloned ${repoFullName} (main)`)
  at(400, { type: 'phase', value: 'scan' })
  log(300, 'Running the test suite in a Nebius Token Factory sandbox')
  log(1500, 'Test suite: 2 failing')
  log(300, 'Code review (Nemotron Ultra) over 1 file(s)')
  at(1800, usageEvent('review', 'ultra', 6200, 940, null))
  log(0, 'Code review: 2 credible bug(s), 1 low-confidence finding(s) dropped')

  // issues
  at(500, { type: 'phase', value: 'issues' })
  ISSUES.forEach((issue, i) => at(i === 0 ? 300 : 250, { type: 'issue_raised', ...issue, number: null, url: null }))
  log(250, live ? 'Found 4 issue(s). Nothing goes to GitHub until you approve it.' : 'Found 4 issue(s) (dry run)')

  // fix: the race
  at(500, { type: 'phase', value: 'fix' })
  at(100, { type: 'status', value: 'testing' })
  at(200, { type: 'race_start', sandboxes: 4, lanes: ISSUES.map((issue, i) => ({ key: issue.key, title: issue.title, sandbox: i + 1 })) })
  log(0, 'Racing 4 fixes across 4 Nebius sandboxes in parallel')
  const go = t + 300
  ISSUES.forEach((issue, i) => tl.at(go + i * 60, { type: 'issue_start', key: issue.key, remaining: 4 }))

  const verify = (l: ReturnType<typeof lane>, target: string, ok = true) => {
    l.stage(250, 'act')
    l.log(350, 'ACT: patched calculator.py, running it in the sandbox')
    l.end(1100, 'act')
    l.stage(150, 'evaluate')
    l.usage('evaluate', 'nano', 1900, 70)
    if (ok) {
      l.log(500, `EVALUATE (Nemotron Nano): ${target} passes, checking the full suite`)
      l.end(800, 'evaluate', { status: 'PASS' })
    }
  }

  // lane 1: test_add, first try
  const a = lane(tl, ISSUES[0], go)
  a.stage(100, 'perceive')
  a.log(600, 'PERCEIVE: reproduced test_calculator.py::test_add in the sandbox')
  a.end(250, 'perceive')
  a.stage(50, 'reproduce')
  a.end(150, 'reproduce', { status: 'EXISTING_TEST' })
  a.iteration(100, 1)
  a.stage(100, 'plan')
  a.usage('plan', 'ultra', 3400, 610)
  a.log(1500, 'PLAN (Nemotron Ultra): add() subtracts b instead of adding it; the test expects add(2, 3) == 5.')
  a.end(200, 'plan', { unfamiliar_api: false })
  a.diff(150, ADD_DIFF)
  verify(a, 'test_calculator.py::test_add')
  a.raw(250, { type: 'lane_end', key: ISSUES[0].key, status: 'fixed', seconds: Math.round((a.t - go) / 100) / 10, iterations: 1 })

  // lane 2: test_average, wrong first try, research, then fixed
  const b = lane(tl, ISSUES[1], go + 60)
  b.stage(100, 'perceive')
  b.log(700, 'PERCEIVE: reproduced test_calculator.py::test_average in the sandbox')
  b.end(250, 'perceive')
  b.stage(50, 'reproduce')
  b.end(150, 'reproduce', { status: 'EXISTING_TEST' })
  b.iteration(100, 1)
  b.stage(100, 'plan')
  b.usage('plan', 'ultra', 3600, 580)
  b.log(1600, 'PLAN (Nemotron Ultra): average() looks off by a rounding issue; round the result.')
  b.end(200, 'plan', { unfamiliar_api: false })
  b.diff(150, AVG_ATTEMPT_1)
  b.stage(250, 'act')
  b.log(350, 'ACT: patched calculator.py, running it in the sandbox')
  b.end(1100, 'act')
  b.stage(150, 'evaluate')
  b.usage('evaluate', 'nano', 2100, 80)
  b.log(500, 'EVALUATE (Nemotron Nano): FAIL_SAME_ERROR, assert 3 == 2 (the +1 is still there)')
  b.end(400, 'evaluate', { status: 'FAIL_SAME_ERROR' })
  b.iteration(300, 2)
  b.stage(150, 'plan')
  b.usage('plan', 'ultra', 4300, 520)
  b.log(1300, 'PLAN (Nemotron Ultra): the +1 is the bug; checking whether statistics.fmean is safe on 3.9+.')
  b.end(200, 'plan', { unfamiliar_api: true })
  b.stage(150, 'research')
  b.log(200, 'RESEARCH (Tavily): "python statistics.fmean availability and behaviour"')
  b.log(1100, 'Found relevant docs, feeding them back into PLAN')
  b.end(200, 'research')
  b.stage(150, 'plan')
  b.usage('plan', 'ultra', 5200, 560)
  b.log(1200, 'PLAN (Nemotron Ultra, with docs): drop the stray +1 and use statistics.fmean (3.8+).')
  b.end(200, 'plan', { unfamiliar_api: false })
  b.diff(150, AVG_FIX)
  verify(b, 'test_calculator.py::test_average')
  b.raw(250, { type: 'lane_end', key: ISSUES[1].key, status: 'fixed', seconds: Math.round((b.t - go) / 100) / 10, iterations: 2 })

  // lane 3: code-review bug, proven by a failing test first
  const c = lane(tl, ISSUES[2], go + 120)
  c.stage(100, 'perceive')
  c.log(400, 'PERCEIVE: loaded calculator.py:6 for the reported bug')
  c.end(200, 'perceive')
  c.stage(100, 'reproduce')
  c.usage('write_test', 'ultra', 2700, 330)
  c.log(1400, 'REPRODUCE (Nemotron Ultra): wrote test_greenlit_review_1.py, running it on the current code')
  c.usage('judge_test', 'nano', 1500, 45)
  c.log(1100, 'REPRODUCE (Nemotron Nano): proven, test_greenlit_review_1.py fails on the current code: raises ZeroDivisionError, not ValueError')
  const proof: GreenlitEvent = {
    type: 'proof',
    key: ISSUES[2].key,
    status: 'reproduced',
    test_path: 'test_greenlit_review_1.py',
    test_code: DIVIDE_TEST_CODE,
    output: 'E       ZeroDivisionError: division by zero',
    reason: 'raises ZeroDivisionError, not ValueError',
  }
  c.raw(0, proof)
  c.raw(0, { type: 'lane', key: ISSUES[2].key, event: 'proof', data: proof as unknown as Record<string, unknown> })
  c.end(150, 'reproduce', { status: 'REPRODUCED' })
  const attempts = partial ? 3 : 1
  for (let n = 1; n <= attempts; n += 1) {
    c.iteration(n === 1 ? 100 : 300, n)
    c.stage(100, 'plan')
    c.usage('plan', 'ultra', 3900, 540)
    c.log(1300, 'PLAN (Nemotron Ultra): guard b == 0 and raise a ValueError with a clear message.')
    c.end(200, 'plan', { unfamiliar_api: false })
    c.diff(150, DIVIDE_FIX)
    if (partial) {
      verify(c, 'test_greenlit_review_1.py', false)
      c.log(500, 'EVALUATE: rejected, it made previously-passing tests fail: test_calculator.py::test_divide_by_zero_returns_inf')
      c.end(300, 'evaluate', { status: 'REGRESSION' })
    } else {
      verify(c, 'test_greenlit_review_1.py')
    }
  }
  c.raw(250, { type: 'lane_end', key: ISSUES[2].key, status: partial ? 'unresolved' : 'fixed', seconds: Math.round((c.t - go) / 100) / 10, iterations: attempts })

  // lane 4: code-review finding that isn't real: dismissed
  const d = lane(tl, ISSUES[3], go + 180)
  d.stage(100, 'perceive')
  d.log(400, 'PERCEIVE: loaded calculator.py:2 for the reported bug')
  d.end(200, 'perceive')
  d.stage(100, 'reproduce')
  d.usage('write_test', 'ultra', 2600, 300)
  d.log(1500, 'REPRODUCE: test passed on the current code, bug not shown (add(10**20, 1) == 10**20 + 1)')
  d.usage('write_test', 'ultra', 2900, 320)
  d.log(1500, 'REPRODUCE: test passed on the current code, bug not shown (Python ints are arbitrary precision)')
  const dismissed: GreenlitEvent = {
    type: 'proof',
    key: ISSUES[3].key,
    status: 'not_reproduced',
    test_path: 'test_greenlit_review_2.py',
    test_code: null,
    output: '',
    reason: '2 reproduction tests all passed on the current code',
  }
  d.raw(0, dismissed)
  d.raw(0, { type: 'lane', key: ISSUES[3].key, event: 'proof', data: dismissed as unknown as Record<string, unknown> })
  d.end(150, 'reproduce', { status: 'NOT_REPRODUCED' })
  d.log(100, "Dismissed review:2: Greenlit couldn't prove it's a real bug, so it won't be raised")
  d.raw(200, { type: 'lane_end', key: ISSUES[3].key, status: 'dismissed', seconds: Math.round((d.t - go) / 100) / 10, iterations: 0 })

  // race over: merge + re-verify
  const lanes = [a, b, c, d]
  const raceEnd = Math.max(...lanes.map((l) => l.t)) + 300
  const sequential = lanes.reduce((sum, l) => sum + (l.t - go), 0) / 1000
  t = raceEnd
  at(0, { type: 'race_end', sandboxes: 4, seconds: Math.round((raceEnd - go) / 100) / 10, sequential_seconds: Math.round(sequential * 10) / 10 })
  log(0, `Race finished in ${((raceEnd - go) / 1000).toFixed(1)}s on 4 sandboxes (one at a time would take ~${sequential.toFixed(1)}s)`)
  const fixedCount = partial ? 2 : 3
  at(300, { type: 'merge_start', fixes: fixedCount })
  log(1400, `MERGE: all ${fixedCount} fixes combine cleanly, full suite re-verified in the sandbox`)
  at(100, { type: 'merge_end', clean: true })
  const statuses = ['fixed', 'fixed', partial ? 'unresolved' : 'fixed', 'dismissed'] as const
  ISSUES.forEach((issue, i) => at(80, { type: 'issue_end', key: issue.key, status: statuses[i] }))
  log(100, "Dropped 1 code-review finding(s) Greenlit couldn't reproduce with a test")

  // review: the change report, then (live) the publish question
  const changes = mockChanges(partial)
  at(600, { type: 'phase', value: 'review' })
  at(200, { type: 'changes_ready', ...changes })
  for (const fix of changes.fixes) {
    for (const file of fix.files) {
      log(120, `Changed ${file.path} lines ${file.lines_changed} (+${file.added} -${file.removed}): ${fix.title}`)
    }
  }
  at(200, { type: 'diff_ready', diff: (partial ? COMBINED_PARTIAL : COMBINED_ALL) + (partial ? '' : DIVIDE_TEST) })

  if (live) {
    at(300, { type: 'status', value: 'awaiting_approval' })
    at(100, {
      type: 'approval_required',
      repo: repoFullName,
      branch: BRANCH,
      base: 'main',
      issues: 3,
      fixed: fixedCount,
      unresolved: 3 - fixedCount,
      commits: fixedCount,
      actions: [
        `Raise 3 issue(s) on ${repoFullName}, labelled 'greenlit'`,
        `Push ${fixedCount} commit(s) to a new branch ${BRANCH} (main is not touched)`,
        `Open a pull request ${BRANCH} -> main that closes ${fixedCount} issue(s)`,
        ...(partial ? ['Comment on the 1 unfixed issue(s) with what was tried'] : []),
      ],
      changes,
    })
    return tl.toTimed()
  }

  log(400, `Dry run complete: ${fixedCount} fix(es) verified in the sandbox, nothing pushed. Add a token to raise issues and open a pull request.`)
  at(400, { type: 'status', value: partial ? 'partial' : 'fixed' })
  at(100, { type: 'phase', value: 'done' })
  return tl.toTimed()
}

/** The rest of a live run once the publish question is answered. */
export function buildMockPublish({ repoFullName, partial }: MockOptions, approved: boolean): TimedEvent[] {
  const url = `https://github.com/${repoFullName}`
  const out: TimedEvent[] = []
  const at = (delay: number, event: GreenlitEvent) => out.push({ delay, event })
  const log = (delay: number, text: string) => at(delay, { type: 'log_line', text })
  const fixed = partial ? 2 : 3
  const status = partial ? 'partial' : 'fixed'
  const raised = ISSUES.slice(0, 3)

  at(0, { type: 'approval', approved })
  if (!approved) {
    log(200, 'Publishing declined. Nothing was written to GitHub.')
    at(300, { type: 'status', value: status })
    at(100, { type: 'phase', value: 'done' })
    return out
  }

  at(200, { type: 'phase', value: 'publish' })
  at(0, { type: 'status', value: 'publishing' })
  raised.forEach((issue, i) => at(350, { type: 'issue_published', key: issue.key, number: 12 + i, url: `${url}/issues/${12 + i}` }))
  log(200, `Raised 3 issue(s) on ${repoFullName}`)
  const shas = ['a1f3c9e7b2d4', 'c7d20e14f98a', 'e40b8a61c3f7']
  raised.slice(0, fixed).forEach((issue, i) =>
    at(400, { type: 'commit', key: issue.key, sha: shas[i], message: `Fix #${12 + i}: ${issue.title}`, url: `${url}/commit/${shas[i]}` }),
  )
  log(500, `Pushed ${fixed} commit(s) to ${BRANCH}`)
  at(900, { type: 'pr_opened', number: 15, url: `${url}/pull/15` })
  at(400, { type: 'status', value: status })
  at(100, { type: 'phase', value: 'done' })
  return out
}
