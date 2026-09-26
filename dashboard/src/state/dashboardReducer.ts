import type { GreenlitEvent, GreenlitEventMap, IssueKind, Phase, RunStatus, Stage } from '@/types/events'

export type PipelineNodeId = Stage | 'loop'

export type NodeVisualStatus = 'idle' | 'active' | 'done' | 'skipped'

export type IssueStatus = 'open' | 'fixing' | 'fixed' | 'unresolved'

export interface UiIssue {
  key: string
  kind: IssueKind
  title: string
  location: string | null
  severity: string | null
  number: number | null
  url: string | null
  status: IssueStatus
  commit: { sha: string; url: string | null } | null
}

export interface LogEntry {
  id: number
  text: string
}

export interface DashboardState {
  repo: GreenlitEventMap['repo'] | null
  phase: Phase | null
  status: RunStatus
  issues: UiIssue[]
  currentIssueKey: string | null
  nodeStatus: Record<PipelineNodeId, NodeVisualStatus>
  /** Edge currently animating a "flow" pulse, keyed as `${from}-${to}`. */
  flowingEdge: string | null
  iteration: number
  diff: string
  diffRevision: number
  logs: LogEntry[]
  pr: GreenlitEventMap['pr_opened'] | null
  error: string | null
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
  repo: null,
  phase: null,
  status: 'idle',
  issues: [],
  currentIssueKey: null,
  nodeStatus: { ...idleStages },
  flowingEdge: null,
  iteration: 0,
  diff: '',
  diffRevision: 0,
  logs: [],
  pr: null,
  error: null,
}

const NEXT_STAGE: Record<Stage, PipelineNodeId> = {
  perceive: 'plan',
  plan: 'research',
  research: 'act',
  act: 'evaluate',
  evaluate: 'loop',
}

const MAX_LOG_LINES = 400
let logIdCounter = 0

export type DashboardAction = GreenlitEvent | { type: 'reset' }

function updateIssue(state: DashboardState, key: string, patch: Partial<UiIssue>): UiIssue[] {
  return state.issues.map((issue) => (issue.key === key ? { ...issue, ...patch } : issue))
}

function appendLog(state: DashboardState, text: string): LogEntry[] {
  logIdCounter += 1
  const logs = [...state.logs, { id: logIdCounter, text }]
  return logs.length > MAX_LOG_LINES ? logs.slice(-MAX_LOG_LINES) : logs
}

export function dashboardReducer(state: DashboardState, event: DashboardAction): DashboardState {
  switch (event.type) {
    case 'reset':
      return { ...initialDashboardState, nodeStatus: { ...idleStages } }

    case 'status':
      return {
        ...state,
        status: event.value,
        nodeStatus:
          event.value === 'fixed' || event.value === 'partial' || event.value === 'unresolved'
            ? { ...state.nodeStatus, loop: 'done' }
            : state.nodeStatus,
      }

    case 'phase':
      return { ...state, phase: event.value, currentIssueKey: event.value === 'fix' ? state.currentIssueKey : null }

    case 'repo':
      return { ...state, repo: { full_name: event.full_name, url: event.url, default_branch: event.default_branch, mode: event.mode } }

    case 'issue_raised':
      return {
        ...state,
        issues: [
          ...state.issues,
          {
            key: event.key,
            kind: event.kind,
            title: event.title,
            location: event.location,
            severity: event.severity,
            number: event.number,
            url: event.url,
            status: 'open',
            commit: null,
          },
        ],
      }

    case 'issue_start':
      return {
        ...state,
        currentIssueKey: event.key,
        issues: updateIssue(state, event.key, { status: 'fixing' }),
        nodeStatus: { ...idleStages },
        flowingEdge: null,
        iteration: 0,
        diff: '',
      }

    case 'issue_end':
      return {
        ...state,
        issues: updateIssue(state, event.key, { status: event.status }),
        nodeStatus: { ...state.nodeStatus, loop: 'done' },
      }

    case 'stage_start': {
      const { stage } = event
      let nodeStatus: Record<PipelineNodeId, NodeVisualStatus>
      if (stage === 'perceive') {
        nodeStatus = { ...idleStages, perceive: 'active' }
      } else if (stage === 'plan') {
        // First plan, a retry looping back from evaluate, or a re-plan after
        // research: downstream stages for this pass start clean either way.
        nodeStatus = { ...state.nodeStatus, plan: 'active', research: state.nodeStatus.research === 'done' ? 'done' : 'idle', act: 'idle', evaluate: 'idle', loop: 'idle' }
      } else {
        nodeStatus = { ...state.nodeStatus, [stage]: 'active' }
      }
      return { ...state, nodeStatus, flowingEdge: null }
    }

    case 'stage_end': {
      const { stage, result } = event
      const nodeStatus = { ...state.nodeStatus, [stage]: 'done' as NodeVisualStatus }
      if (stage === 'plan' && result?.unfamiliar_api === false && nodeStatus.research !== 'done') {
        nodeStatus.research = 'skipped'
      }
      return { ...state, nodeStatus, flowingEdge: `${stage}-${NEXT_STAGE[stage]}` }
    }

    case 'iteration':
      return {
        ...state,
        iteration: event.count,
        // Attempt 1 arrives straight from perceive; later attempts loop back.
        flowingEdge: event.count > 1 ? 'loop-plan' : state.flowingEdge,
        nodeStatus: event.count > 1 ? { ...state.nodeStatus, loop: 'active' } : state.nodeStatus,
      }

    case 'log_line':
      return { ...state, logs: appendLog(state, event.text) }

    case 'diff_ready':
      return { ...state, diff: event.diff, diffRevision: state.diffRevision + 1 }

    case 'commit':
      return { ...state, issues: updateIssue(state, event.key, { commit: { sha: event.sha, url: event.url } }) }

    case 'pr_opened':
      return { ...state, pr: { number: event.number, url: event.url } }

    case 'run_error':
      return { ...state, error: event.message, logs: appendLog(state, `ERROR: ${event.message}`) }

    default:
      return state
  }
}
