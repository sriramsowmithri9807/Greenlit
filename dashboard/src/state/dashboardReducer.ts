import type { GreenlitEvent, RunStatus, Stage } from '@/types/events'

export type PipelineNodeId = Stage | 'loop'

export type NodeVisualStatus = 'idle' | 'active' | 'done' | 'skipped'

export const PIPELINE_ORDER: PipelineNodeId[] = [
  'perceive',
  'plan',
  'research',
  'act',
  'evaluate',
  'loop',
]

export interface LogEntry {
  id: number
  text: string
}

export interface DashboardState {
  nodeStatus: Record<PipelineNodeId, NodeVisualStatus>
  /** Edge currently animating a "flow" pulse, keyed as `${from}-${to}`. */
  flowingEdge: string | null
  logs: LogEntry[]
  diff: string
  diffRevision: number
  iteration: number
  status: RunStatus
  /** Which failing test the agent is currently working, for a repo-wide
   * (multi-issue) run. Null for a single-issue run/demo that never emits
   * issue_start — the UI hides the tracker entirely in that case. */
  currentIssue: { id: string; remaining: number } | null
  fixedIssues: string[]
  unresolvedIssues: string[]
}

const idleStages: Record<PipelineNodeId, NodeVisualStatus> = {
  perceive: 'idle',
  plan: 'idle',
  research: 'idle',
  act: 'idle',
  evaluate: 'idle',
  loop: 'idle',
}

export const initialDashboardState: DashboardState = {
  nodeStatus: { ...idleStages },
  flowingEdge: null,
  logs: [],
  diff: '',
  diffRevision: 0,
  iteration: 0,
  status: 'failing',
  currentIssue: null,
  fixedIssues: [],
  unresolvedIssues: [],
}

let logIdCounter = 0

const NEXT_STAGE: Record<Stage, PipelineNodeId> = {
  perceive: 'plan',
  plan: 'research',
  research: 'act',
  act: 'evaluate',
  evaluate: 'loop',
}

export type DashboardAction = GreenlitEvent | { type: 'reset' }

export function dashboardReducer(state: DashboardState, event: DashboardAction): DashboardState {
  switch (event.type) {
    case 'reset':
      return { ...initialDashboardState, nodeStatus: { ...idleStages }, logs: [] }

    case 'stage_start': {
      const { stage } = event
      let nodeStatus = state.nodeStatus

      if (stage === 'perceive') {
        // Fresh run: everything resets.
        nodeStatus = { ...idleStages, perceive: 'active' }
      } else if (stage === 'plan') {
        // Either the first plan, or a loop-back from evaluate — either way
        // downstream stages for this pass start clean.
        nodeStatus = {
          ...state.nodeStatus,
          plan: 'active',
          research: 'idle',
          act: 'idle',
          evaluate: 'idle',
          loop: 'idle',
        }
      } else {
        nodeStatus = { ...state.nodeStatus, [stage]: 'active' }
      }

      return {
        ...state,
        nodeStatus,
        flowingEdge: null,
      }
    }

    case 'stage_end': {
      const { stage, result } = event
      const nodeStatus: Record<PipelineNodeId, NodeVisualStatus> = {
        ...state.nodeStatus,
        [stage]: 'done',
      }

      if (stage === 'plan' && result && result.unfamiliar_api === false) {
        nodeStatus.research = 'skipped'
      }

      const next = NEXT_STAGE[stage]
      return {
        ...state,
        nodeStatus,
        flowingEdge: `${stage}-${next}`,
      }
    }

    case 'log_line': {
      logIdCounter += 1
      const logs = [...state.logs, { id: logIdCounter, text: event.text }]
      // Cap history so a long run doesn't grow the DOM unbounded.
      if (logs.length > 300) logs.splice(0, logs.length - 300)
      return { ...state, logs }
    }

    case 'diff_ready':
      return { ...state, diff: event.diff, diffRevision: state.diffRevision + 1 }

    case 'iteration':
      return {
        ...state,
        iteration: event.count,
        nodeStatus: { ...state.nodeStatus, loop: 'idle' },
        flowingEdge: 'loop-plan',
      }

    case 'status':
      return {
        ...state,
        status: event.value,
        nodeStatus:
          event.value === 'fixed' || event.value === 'unresolved'
            ? { ...state.nodeStatus, loop: 'done' }
            : state.nodeStatus,
      }

    case 'issue_start':
      return {
        ...state,
        currentIssue: { id: event.issue, remaining: event.remaining },
      }

    case 'issue_end':
      return {
        ...state,
        fixedIssues:
          event.status === 'fixed' ? [...state.fixedIssues, event.issue] : state.fixedIssues,
        unresolvedIssues:
          event.status === 'unresolved'
            ? [...state.unresolvedIssues, event.issue]
            : state.unresolvedIssues,
      }

    default:
      return state
  }
}
