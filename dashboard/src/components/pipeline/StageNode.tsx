import {
  Brain,
  CheckCircle2,
  Eye,
  FlaskConical,
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

export interface StageNodeData {
  label: string
  kind: PipelineNodeId
  status: NodeVisualStatus
  /** How the current issue ended, which colours the Loop node once it's done. */
  outcome: 'fixed' | 'unresolved' | null
}

const ICONS: Record<PipelineNodeId, typeof Eye> = {
  perceive: Eye,
  reproduce: FlaskConical,
  plan: Brain,
  research: Search,
  act: Hammer,
  evaluate: ListChecks,
  loop: RotateCw,
}

function toneFor(kind: PipelineNodeId, status: NodeVisualStatus, outcome: StageNodeData['outcome']) {
  if (kind === 'loop' && status === 'done' && outcome) {
    return outcome === 'fixed'
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
  const { label, kind, status, outcome } = data
  const reducedMotion = usePrefersReducedMotion()
  const tone = toneFor(kind, status, outcome)
  const isLoopDone = kind === 'loop' && status === 'done' && outcome !== null
  const Icon = isLoopDone ? (outcome === 'fixed' ? CheckCircle2 : XCircle) : ICONS[kind]

  return (
    <div
      className={cn(
        'relative flex w-[152px] flex-col items-center gap-2 rounded-xl border-2 px-4 py-4 transition-all duration-300',
        status === 'skipped' && 'border-dashed opacity-50',
        status === 'active' && !reducedMotion && 'signal-border animate-pulse-glow -translate-y-0.5',
      )}
      style={{
        borderColor: tone.border,
        backgroundColor: tone.bg,
        ['--glow-color' as string]: tone.border,
        ['--signal-color' as string]: 'var(--color-amber)',
        ['--signal-color-2' as string]: 'var(--color-done)',
        boxShadow: status === 'done' ? `0 0 18px -6px ${tone.border}` : undefined,
      }}
    >
      <Handle type="target" position={Position.Left} id="in" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} id="out" style={{ opacity: 0 }} />
      <Handle type="target" position={Position.Bottom} id="loop-in" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} id="loop-out" style={{ opacity: 0 }} />

      <Icon
        size={24}
        style={{ color: tone.fg }}
        strokeWidth={2.25}
        className={cn(status === 'active' && !reducedMotion && (kind === 'loop' ? 'animate-spin-slow' : 'animate-pulse'))}
      />
      <span className="font-[family-name:var(--font-display)] text-xs font-semibold tracking-wider uppercase" style={{ color: tone.fg }}>
        {label}
      </span>
    </div>
  )
}
