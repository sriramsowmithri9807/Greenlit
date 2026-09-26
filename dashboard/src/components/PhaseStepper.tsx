import { motion } from 'framer-motion'
import { Check, X } from 'lucide-react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import { cn } from '@/lib/utils'
import type { Phase, RunStatus } from '@/types/events'

const STEPS: { phase: Exclude<Phase, 'done'>; live: string; dryRun: string }[] = [
  { phase: 'clone', live: 'Clone', dryRun: 'Clone' },
  { phase: 'scan', live: 'Scan', dryRun: 'Scan' },
  { phase: 'raise', live: 'Raise issues', dryRun: 'List issues' },
  { phase: 'fix', live: 'Fix', dryRun: 'Fix' },
  { phase: 'publish', live: 'Open PR', dryRun: 'Show diff' },
]

type StepState = 'pending' | 'active' | 'done' | 'failed'

export function PhaseStepper({ phase, status, dryRun }: { phase: Phase | null; status: RunStatus; dryRun: boolean }) {
  const reducedMotion = usePrefersReducedMotion()
  const clean = status === 'clean'
  const currentIndex = phase === 'done' ? STEPS.length : STEPS.findIndex((s) => s.phase === phase)

  function stateOf(index: number): StepState {
    if (status === 'error' && index === Math.max(currentIndex, 0)) return 'failed'
    if (index < currentIndex) return 'done'
    if (index === currentIndex) return 'active'
    return 'pending'
  }

  return (
    <ol className="flex items-center gap-2 overflow-x-auto px-6 pb-4" aria-label="Run progress">
      {STEPS.map((step, index) => {
        const state = clean && index > 1 ? 'pending' : stateOf(index)
        const color =
          state === 'done'
            ? 'var(--color-pass)'
            : state === 'active'
              ? 'var(--color-amber)'
              : state === 'failed'
                ? 'var(--color-fail)'
                : 'var(--color-border)'
        return (
          <li key={step.phase} className="flex min-w-0 flex-1 items-center gap-2">
            <motion.span
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold',
                state === 'active' && !reducedMotion && 'animate-pulse-glow',
              )}
              style={{ ['--glow-color' as string]: color }}
              animate={{
                borderColor: color,
                backgroundColor: state === 'done' ? color : 'var(--color-surface)',
                color: state === 'done' ? '#052e14' : state === 'pending' ? 'var(--color-fg-muted)' : color,
              }}
              transition={reducedMotion ? { duration: 0 } : { duration: 0.35 }}
            >
              {state === 'done' ? <Check size={13} strokeWidth={3} /> : state === 'failed' ? <X size={13} strokeWidth={3} /> : index + 1}
            </motion.span>
            <span
              className={cn(
                'truncate text-xs font-medium tracking-wide whitespace-nowrap uppercase transition-colors',
                state === 'pending' ? 'text-[var(--color-fg-muted)]' : 'text-[var(--color-fg)]',
              )}
            >
              {dryRun ? step.dryRun : step.live}
            </span>
            {index < STEPS.length - 1 && (
              <span className="relative h-px min-w-4 flex-1 bg-[var(--color-border)]">
                <motion.span
                  className="absolute inset-y-0 left-0 bg-[var(--color-pass)]"
                  initial={false}
                  animate={{ width: state === 'done' ? '100%' : '0%' }}
                  transition={reducedMotion ? { duration: 0 } : { duration: 0.5, ease: 'easeOut' }}
                />
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
