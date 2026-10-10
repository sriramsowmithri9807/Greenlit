/** Mirrors what greenlit/agent.py and greenlit/orchestrator.py emit. */

export type Stage = 'perceive' | 'reproduce' | 'plan' | 'research' | 'act' | 'evaluate'

export type RunStatus =
  | 'idle'
  | 'scanning'
  | 'testing'
  | 'awaiting_approval'
  | 'publishing'
  | 'clean'
  | 'fixed'
  | 'partial'
  | 'unresolved'
  | 'error'

export type Phase = 'clone' | 'scan' | 'issues' | 'fix' | 'review' | 'publish' | 'done'

export type IssueKind = 'test' | 'review' | 'report'

export interface StageResult {
  unfamiliar_api?: boolean
  status?: string
  [key: string]: unknown
}

/** One changed line. `old`/`new` are line numbers before/after the change. */
export interface ChangeLine {
  kind: 'add' | 'del' | 'ctx'
  old: number | null
  new: number | null
  text: string
}

export interface ChangedFile {
  path: string
  status: 'modified' | 'added' | 'deleted'
  added: number
  removed: number
  /** Changed line numbers in the new file, e.g. "2, 30-34". */
  lines_changed: string
  hunks: { header: string; lines: ChangeLine[] }[]
}

/** Every verified fix and what it changed (greenlit/changes.py). */
export interface Changes {
  fixes: { key: string; title: string; location: string | null; files: ChangedFile[] }[]
  totals: { fixes: number; files: number; added: number; removed: number }
}

/** What publishing would write to GitHub; the run waits for a yes/no. */
export interface PublishRequest {
  repo: string
  branch: string
  base: string
  issues: number
  fixed: number
  unresolved: number
  commits: number
  actions: string[]
  changes: Changes
}

/** Whether a code-review finding was proven by a failing test. */
export interface Proof {
  key: string
  status: 'reproduced' | 'not_reproduced' | 'unproven'
  test_path: string | null
  test_code: string | null
  output: string
  reason: string
}

export type Tier = 'ultra' | 'nano'

/** One Nemotron call (greenlit/usage.py). */
export interface UsageEvent {
  role: 'plan' | 'review' | 'evaluate' | 'write_test' | 'judge_test'
  model: string
  tier: Tier
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number
  cost_usd: number
  ultra_cost_usd: number
  key: string | null
}

export interface TierTotals {
  calls: number
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
}

export type LaneEventType = 'stage_start' | 'stage_end' | 'iteration' | 'diff_ready' | 'log_line' | 'proof'

export interface GreenlitEventMap {
  status: { value: RunStatus }
  phase: { value: Phase }
  repo: { full_name: string; url: string | null; default_branch: string | null; mode: 'live' | 'dry_run' }
  issue_raised: {
    key: string
    kind: IssueKind
    title: string
    location: string | null
    severity: string | null
    number: number | null
    url: string | null
  }
  issue_start: { key: string; remaining: number }
  issue_end: { key: string; status: 'fixed' | 'unresolved' | 'dismissed' }
  stage_start: { stage: Stage }
  stage_end: { stage: Stage; result?: StageResult }
  iteration: { count: number }
  log_line: { text: string }
  diff_ready: { diff: string }
  changes_ready: Changes
  approval_required: PublishRequest
  approval: { approved: boolean }
  issue_published: { key: string; number: number; url: string }
  commit: { key: string; sha: string; message: string; url: string | null }
  pr_opened: { number: number; url: string }
  run_error: { message: string }
  proof: Proof
  usage: UsageEvent
  cost_summary: { ultra: TierTotals; nano: TierTotals; total_usd: number; ultra_only_usd: number; savings_pct: number }
  race_start: { sandboxes: number; lanes: { key: string; title: string; sandbox: number }[] }
  lane: { key: string; event: LaneEventType; data: Record<string, unknown> }
  lane_end: { key: string; status: 'fixed' | 'unresolved' | 'dismissed'; seconds: number; iterations: number }
  race_end: { sandboxes: number; seconds: number; sequential_seconds: number }
  merge_start: { fixes: number }
  merge_end: { clean: boolean }
}

export type GreenlitEventType = keyof GreenlitEventMap

export type GreenlitEvent = {
  [K in GreenlitEventType]: { type: K } & GreenlitEventMap[K]
}[GreenlitEventType]

export const EVENT_TYPES = [
  'status',
  'phase',
  'repo',
  'issue_raised',
  'issue_start',
  'issue_end',
  'stage_start',
  'stage_end',
  'iteration',
  'log_line',
  'diff_ready',
  'changes_ready',
  'approval_required',
  'approval',
  'issue_published',
  'commit',
  'pr_opened',
  'run_error',
  'proof',
  'usage',
  'cost_summary',
  'race_start',
  'lane',
  'lane_end',
  'race_end',
  'merge_start',
  'merge_end',
] as const satisfies readonly GreenlitEventType[]
