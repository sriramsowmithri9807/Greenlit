/** Mirrors what greenlit/agent.py and greenlit/orchestrator.py emit. */

export type Stage = 'perceive' | 'plan' | 'research' | 'act' | 'evaluate'

export type RunStatus =
  | 'idle'
  | 'scanning'
  | 'testing'
  | 'clean'
  | 'fixed'
  | 'partial'
  | 'unresolved'
  | 'error'

export type Phase = 'clone' | 'scan' | 'raise' | 'fix' | 'publish' | 'done'

export type IssueKind = 'test' | 'review'

export interface StageResult {
  unfamiliar_api?: boolean
  status?: string
  [key: string]: unknown
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
  'commit',
  'pr_opened',
  'run_error',
] as const satisfies readonly GreenlitEventType[]
