export type Stage = 'perceive' | 'plan' | 'research' | 'act' | 'evaluate'

export type RunStatus = 'failing' | 'testing' | 'fixed' | 'unresolved'

export interface StageResult {
  unfamiliar_api?: boolean
  [key: string]: unknown
}

export interface StageStartEvent {
  stage: Stage
}

export interface StageEndEvent {
  stage: Stage
  result?: StageResult
}

export interface LogLineEvent {
  text: string
}

export interface DiffReadyEvent {
  diff: string
}

export interface IterationEvent {
  count: number
}

export interface StatusEvent {
  value: RunStatus
}

/** A repo-wide run works one failing test at a time; these two events
 * bracket the fix loop for a single issue so multi-issue runs (see
 * greenlit/orchestrator.py's outer loop) are distinguishable from a
 * single-issue run's own retries. */
export interface IssueStartEvent {
  issue: string
  remaining: number
}

export interface IssueEndEvent {
  issue: string
  status: 'fixed' | 'unresolved'
}

export interface GreenlitEventMap {
  stage_start: StageStartEvent
  stage_end: StageEndEvent
  log_line: LogLineEvent
  diff_ready: DiffReadyEvent
  iteration: IterationEvent
  status: StatusEvent
  issue_start: IssueStartEvent
  issue_end: IssueEndEvent
}

export type GreenlitEventType = keyof GreenlitEventMap

export type GreenlitEvent = {
  [K in GreenlitEventType]: { type: K } & GreenlitEventMap[K]
}[GreenlitEventType]

export const EVENT_TYPES: GreenlitEventType[] = [
  'stage_start',
  'stage_end',
  'log_line',
  'diff_ready',
  'iteration',
  'status',
  'issue_start',
  'issue_end',
]
