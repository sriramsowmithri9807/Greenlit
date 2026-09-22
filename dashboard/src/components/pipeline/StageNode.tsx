import {
  Brain,
  CheckCircle2,
  Eye,
  Hammer,
  ListChecks,
  RotateCw,
  Search,
  XCircle,
} from 'lucide-react'
import { Handle, Position, type NodeProps } from 'reactflow'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import { cn } from '@/lib/utils'
import type { NodeVisualStatus, PipelineNodeId } from '@/state/dashboardReducer'
import type { RunStatus } from '@/types/events'

export interface StageNodeData {
  label: string
  kind: PipelineNodeId
  status: NodeVisualStatus
  runStatus: RunStatus
}

const ICONS: Record<PipelineNodeId, typeof Eye> = {
  perceive: Eye,
  plan: Brain,
  research: Search,
  act: Hammer,
  evaluate: ListChecks,
  loop: RotateCw,
}

function toneFor(kind: PipelineNodeId, status: NodeVisualStatus, runStatus: RunStatus) {
  if (kind === 'loop' && status === 'done') {
    return runStatus === 'fixed'
      ? { border: 'var(--color-pass)', fg: 'var(--color-pass)', bg: 'var(--color-pass-dim)' }
      : { border: 'var(--color-border)', fg: 'var(--color-fg-muted)', bg: 'var(--color-surface-raised)' }
  }
  switch (status) {
    case 'active':
      return { border: 'var(--color-amber)', fg: 'var(--color-amber)', bg: 'color-mix(in oklab, var(--color-amber) 10%, var(--color-surface))' }
    case 'done':
      return { border: 'var(--color-done)', fg: 'var(--color-done)', bg: 'color-mix(in oklab, var(--color-done) 8%, var(--color-surface))' }
    case 'skipped':
      return { border: 'var(--color-border)', fg: 'var(--color-fg-muted)', bg: 'var(--color-surface)' }
    default:
      return { border: 'var(--color-border)', fg: 'var(--color-fg-muted)', bg: 'var(--color-surface)' }
  }
}

export function StageNode({ data }: NodeProps<StageNodeData>) {
  const { label, kind, status, runStatus } = data
  const reducedMotion = usePrefersReducedMotion()
  const tone = toneFor(kind, status, runStatus)
  const isLoopDone = kind === 'loop' && status === 'done'
  const Icon = isLoopDone ? (runStatus === 'fixed' ? CheckCircle2 : XCircle) : ICONS[kind]

  return (
    <div
      className={cn(
        'flex w-[152px] flex-col items-center gap-2 rounded-xl border-2 px-4 py-4 transition-colors duration-300',
        status === 'skipped' && 'border-dashed opacity-50',
        status === 'active' && !reducedMotion && 'animate-pulse-glow',
      )}
      style={{
        borderColor: tone.border,
        backgroundColor: tone.bg,
        ['--glow-color' as string]: tone.border,
      }}
    >
      <Handle type="target" position={Position.Left} id="in" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} id="out" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Bottom} id="loop-in" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} id="loop-out" style={{ opacity: 0 }} />

      <Icon size={24} style={{ color: tone.fg }} strokeWidth={2.25} />
      <span className="text-xs font-semibold tracking-wide uppercase" style={{ color: tone.fg }}>
        {label}
      </span>
    </div>
  )
}
