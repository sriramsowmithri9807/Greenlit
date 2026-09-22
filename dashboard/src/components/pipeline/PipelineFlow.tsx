import { useMemo } from 'react'
import ReactFlow, { Background, BackgroundVariant, MarkerType, type Edge, type Node } from 'reactflow'
import 'reactflow/dist/style.css'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { DashboardState, PipelineNodeId } from '@/state/dashboardReducer'
import { StageNode, type StageNodeData } from './StageNode'

const nodeTypes = { stage: StageNode }

const LABELS: Record<PipelineNodeId, string> = {
  perceive: 'Perceive',
  plan: 'Plan',
  research: 'Research',
  act: 'Act',
  evaluate: 'Evaluate',
  loop: 'Loop',
}

const POSITIONS: Record<PipelineNodeId, { x: number; y: number }> = {
  perceive: { x: 0, y: 70 },
  plan: { x: 210, y: 70 },
  research: { x: 420, y: 70 },
  act: { x: 630, y: 70 },
  evaluate: { x: 840, y: 70 },
  loop: { x: 1050, y: 70 },
}

const CHAIN: [PipelineNodeId, PipelineNodeId][] = [
  ['perceive', 'plan'],
  ['plan', 'research'],
  ['research', 'act'],
  ['act', 'evaluate'],
  ['evaluate', 'loop'],
]

const DIM = 'var(--color-border)'
const LIT = 'var(--color-done)'
const FLOWING = 'var(--color-amber)'

export function PipelineFlow({ state }: { state: DashboardState }) {
  const reducedMotion = usePrefersReducedMotion()

  const nodes = useMemo<Node<StageNodeData>[]>(
    () =>
      (Object.keys(LABELS) as PipelineNodeId[]).map((kind) => ({
        id: kind,
        type: 'stage',
        position: POSITIONS[kind],
        draggable: false,
        selectable: false,
        data: {
          label: LABELS[kind],
          kind,
          status: state.nodeStatus[kind],
          runStatus: state.status,
        },
      })),
    [state.nodeStatus, state.status],
  )

  const edges = useMemo<Edge[]>(() => {
    const chainEdges: Edge[] = CHAIN.map(([source, target]) => {
      const id = `${source}-${target}`
      const isFlowing = state.flowingEdge === id && !reducedMotion
      const isSkipped =
        state.nodeStatus.research === 'skipped' && (source === 'research' || target === 'research')
      const isLit = !isSkipped && state.nodeStatus[source] !== 'idle'
      const color = isFlowing ? FLOWING : isLit ? LIT : DIM

      return {
        id,
        source,
        target,
        sourceHandle: 'out',
        targetHandle: 'in',
        type: 'smoothstep',
        animated: isFlowing,
        style: {
          stroke: color,
          strokeWidth: isFlowing ? 2.5 : 1.5,
          strokeDasharray: isSkipped ? '4 4' : undefined,
          opacity: isSkipped ? 0.4 : 1,
          transition: 'stroke 0.3s ease',
        },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      }
    })

    const loopBackFlowing = state.flowingEdge === 'loop-plan' && !reducedMotion
    const loopBackEdge: Edge = {
      id: 'loop-plan',
      source: 'loop',
      target: 'plan',
      sourceHandle: 'loop-out',
      targetHandle: 'loop-in',
      type: 'default',
      animated: loopBackFlowing,
      style: {
        stroke: loopBackFlowing ? FLOWING : DIM,
        strokeWidth: loopBackFlowing ? 2.5 : 1.5,
        opacity: loopBackFlowing ? 1 : 0.5,
        transition: 'stroke 0.3s ease',
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: loopBackFlowing ? FLOWING : DIM,
        width: 16,
        height: 16,
      },
    }

    return [...chainEdges, loopBackEdge]
  }, [state.nodeStatus, state.flowingEdge, reducedMotion])

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.25, maxZoom: 1.4 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        panOnScroll={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--color-border)" />
      </ReactFlow>
    </div>
  )
}
