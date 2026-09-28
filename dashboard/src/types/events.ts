/** Mirrors what greenlit/agent.py and greenlit/orchestrator.py emit. */

export type Stage = 'perceive' | 'plan' | 'research' | 'act' | 'evaluate'

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

export type IssueKind = 'test' | 'review'

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
  issue_end: { key: string; status: 'fixed' | 'unresolved' }
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
] as const satisfies readonly GreenlitEventType[]
