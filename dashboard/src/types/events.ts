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

export interface GreenlitEventMap {
  stage_start: StageStartEvent
  stage_end: StageEndEvent
  log_line: LogLineEvent
  diff_ready: DiffReadyEvent
  iteration: IterationEvent
  status: StatusEvent
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
]
