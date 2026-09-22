import { motion } from 'framer-motion'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { RunStatus } from '@/types/events'

const STATUS_CONFIG: Record<
  RunStatus,
  { label: string; bg: string; fg: string; border: string; pulsing: boolean }
> = {
  failing: {
    label: 'Failing',
    bg: 'color-mix(in oklab, var(--color-fail) 16%, transparent)',
    fg: 'var(--color-fail)',
    border: 'var(--color-fail)',
    pulsing: false,
  },
  testing: {
    label: 'Testing',
    bg: 'color-mix(in oklab, var(--color-amber) 14%, transparent)',
    fg: 'var(--color-amber)',
    border: 'var(--color-amber)',
    pulsing: true,
  },
  fixed: {
    label: 'Fixed',
    bg: 'color-mix(in oklab, var(--color-pass) 18%, transparent)',
    fg: 'var(--color-pass)',
    border: 'var(--color-pass)',
    pulsing: false,
  },
  unresolved: {
    label: 'Unresolved',
    bg: 'var(--color-surface-raised)',
    fg: 'var(--color-fg-muted)',
    border: 'var(--color-border)',
    pulsing: false,
  },
}

export function StatusBadge({ status }: { status: RunStatus }) {
  const reducedMotion = usePrefersReducedMotion()
  const config = STATUS_CONFIG[status]

  return (
    <motion.div
      className="flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-semibold"
      animate={{
        backgroundColor: config.bg,
        color: config.fg,
        borderColor: config.border,
        scale: status === 'fixed' ? [1, 1.18, 0.98, 1] : 1,
      }}
      transition={
        reducedMotion
          ? { duration: 0 }
          : {
              backgroundColor: { duration: 0.45, ease: 'easeInOut' },
              color: { duration: 0.45, ease: 'easeInOut' },
              borderColor: { duration: 0.45, ease: 'easeInOut' },
              scale: { duration: 0.55, times: [0, 0.4, 0.7, 1], ease: 'easeOut' },
            }
      }
    >
      <span className="relative flex h-2 w-2">
        {config.pulsing && !reducedMotion && (
          <motion.span
            className="absolute inline-flex h-full w-full rounded-full"
            style={{ backgroundColor: config.fg }}
            animate={{ scale: [1, 2.2], opacity: [0.6, 0] }}
            transition={{ duration: 1.2, repeat: Infinity, ease: 'easeOut' }}
          />
        )}
        <span
          className="relative inline-flex h-2 w-2 rounded-full"
          style={{ backgroundColor: config.fg }}
        />
      </span>
      {config.label}
    </motion.div>
  )
}
