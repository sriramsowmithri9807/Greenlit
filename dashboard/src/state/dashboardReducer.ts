import type { Changes, GreenlitEvent, GreenlitEventMap, IssueKind, Phase, Proof, PublishRequest, RunStatus, Stage, Tier } from '@/types/events'

export type PipelineNodeId = Stage | 'loop'

export type NodeVisualStatus = 'idle' | 'active' | 'done' | 'skipped'

export type IssueStatus = 'open' | 'fixing' | 'fixed' | 'unresolved' | 'dismissed'

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
  proof: Proof | null
}

export interface TierCost {
  calls: number
  tokens: number
  usd: number
}

/** Live model spend, built from `usage` events. */
export interface CostState {
  ultra: TierCost
  nano: TierCost
  /** What the same calls would have cost with every step on Ultra. */
  ultraOnlyUsd: number
  byIssue: Record<string, number>
  /** Bumps on every call, to animate the panel. */
  pulse: number
  lastTier: Tier | null
}

export type LaneStatus = 'running' | 'fixed' | 'unresolved' | 'dismissed'

/** One sandbox lane in a parallel race. */
export interface Lane {
  key: string
  title: string
  sandbox: number
  stage: Stage | null
  done: Stage[]
  iteration: number
  lastLog: string
  status: LaneStatus
  seconds: number | null
  proof: Proof['status'] | null
}

export interface RaceState {
  sandboxes: number
  order: string[]
  lanes: Record<string, Lane>
  startedAt: number
  seconds: number | null
  sequentialSeconds: number | null
  merge: 'pending' | 'running' | 'clean' | 'reworked'
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
  changes: Changes | null
  /** The publish question: asked (answer null), then answered. */
  approval: { request: PublishRequest; answer: 'approved' | 'declined' | null } | null
  cost: CostState
  race: RaceState | null
}

const idleStages: Record<PipelineNodeId, NodeVisualStatus> = {
  perceive: 'idle',
  reproduce: 'idle',
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
  changes: null,
  approval: null,
  cost: emptyCost(),
  race: null,
}

function emptyCost(): CostState {
  return {
    ultra: { calls: 0, tokens: 0, usd: 0 },
    nano: { calls: 0, tokens: 0, usd: 0 },
    ultraOnlyUsd: 0,
    byIssue: {},
    pulse: 0,
    lastTier: null,
  }
}

const NEXT_STAGE: Record<Stage, PipelineNodeId> = {
  perceive: 'reproduce',
  reproduce: 'plan',
  plan: 'research',
  research: 'act',
  act: 'evaluate',
  evaluate: 'loop',
}

const MAX_LOG_LINES = 400
let logIdCounter = 0

export type DashboardAction = GreenlitEvent | { type: 'reset' }

function updateLane(state: DashboardState, key: string, update: (lane: Lane) => Lane): DashboardState {
  const lane = state.race?.lanes[key]
  if (!state.race || !lane) return state
  return { ...state, race: { ...state.race, lanes: { ...state.race.lanes, [key]: update(lane) } } }
}

function laneEvent(state: DashboardState, event: GreenlitEventMap['lane']): DashboardState {
  const data = event.data
  switch (event.event) {
    case 'stage_start':
      return updateLane(state, event.key, (lane) => ({ ...lane, stage: data.stage as Stage }))
    case 'stage_end':
      return updateLane(state, event.key, (lane) => ({
        ...lane,
        stage: lane.stage === data.stage ? null : lane.stage,
        done: lane.done.includes(data.stage as Stage) ? lane.done : [...lane.done, data.stage as Stage],
      }))
    case 'iteration':
      return updateLane(state, event.key, (lane) => ({ ...lane, iteration: Number(data.count) }))
    case 'log_line':
      return updateLane(state, event.key, (lane) => ({ ...lane, lastLog: String(data.text) }))
    case 'diff_ready':
      // Show the most recent proposal from any lane in the diff panel.
      return { ...state, diff: String(data.diff), diffRevision: state.diffRevision + 1 }
    default:
      return state
  }
}

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
      return { ...initialDashboardState, nodeStatus: { ...idleStages }, cost: emptyCost() }

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
            proof: null,
          },
        ],
      }

    case 'issue_start':
      if (state.race) return { ...state, issues: updateIssue(state, event.key, { status: 'fixing' }) }
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
        nodeStatus: state.race ? state.nodeStatus : { ...state.nodeStatus, loop: 'done' },
      }

    case 'proof': {
      const { type: _type, ...proof } = event
      const next = { ...state, issues: updateIssue(state, event.key, { proof }) }
      return updateLane(next, event.key, (lane) => ({ ...lane, proof: proof.status }))
    }

    case 'usage': {
      const tier = state.cost[event.tier]
      return {
        ...state,
        cost: {
          ...state.cost,
          [event.tier]: {
            calls: tier.calls + 1,
            tokens: tier.tokens + event.prompt_tokens + event.completion_tokens,
            usd: tier.usd + event.cost_usd,
          },
          ultraOnlyUsd: state.cost.ultraOnlyUsd + event.ultra_cost_usd,
          byIssue: event.key ? { ...state.cost.byIssue, [event.key]: (state.cost.byIssue[event.key] ?? 0) + event.cost_usd } : state.cost.byIssue,
          pulse: state.cost.pulse + 1,
          lastTier: event.tier,
        },
      }
    }

    case 'race_start':
      return {
        ...state,
        race: {
          sandboxes: event.sandboxes,
          order: event.lanes.map((l) => l.key),
          lanes: Object.fromEntries(
            event.lanes.map((l) => [
              l.key,
              { key: l.key, title: l.title, sandbox: l.sandbox, stage: null, done: [], iteration: 0, lastLog: '', status: 'running', seconds: null, proof: null },
            ]),
          ),
          startedAt: Date.now(),
          seconds: null,
          sequentialSeconds: null,
          merge: 'pending',
        },
      }

    case 'lane':
      return laneEvent(state, event)

    case 'lane_end':
      return updateLane(state, event.key, (lane) => ({ ...lane, status: event.status, seconds: event.seconds, stage: null }))

    case 'race_end':
      return state.race ? { ...state, race: { ...state.race, seconds: event.seconds, sequentialSeconds: event.sequential_seconds } } : state

    case 'merge_start':
      return state.race ? { ...state, race: { ...state.race, merge: 'running' } } : state

    case 'merge_end':
      return state.race ? { ...state, race: { ...state.race, merge: event.clean ? 'clean' : 'reworked' } } : state

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

    case 'changes_ready':
      return { ...state, changes: { fixes: event.fixes, totals: event.totals } }

    case 'approval_required': {
      const { type: _type, ...request } = event
      return { ...state, approval: { request, answer: null } }
    }

    case 'approval':
      return state.approval
        ? { ...state, approval: { ...state.approval, answer: event.approved ? 'approved' : 'declined' } }
        : state

    case 'issue_published':
      return { ...state, issues: updateIssue(state, event.key, { number: event.number, url: event.url }) }

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
