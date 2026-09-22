import { motion } from 'framer-motion'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

export function IterationCounter({ count }: { count: number }) {
  const reducedMotion = usePrefersReducedMotion()

  return (
    <div className="flex items-center gap-2 text-sm text-[var(--color-fg-muted)]">
      <span className="tracking-wide uppercase">Iteration</span>
      <motion.span
        key={count}
        className="inline-flex min-w-[1.5ch] justify-center rounded-md bg-[var(--color-surface-raised)] px-2 py-0.5 font-mono text-base font-semibold text-[var(--color-fg)] tabular-nums"
        initial={reducedMotion ? false : { scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={reducedMotion ? { duration: 0 } : { type: 'spring', stiffness: 480, damping: 16 }}
      >
        {count}
      </motion.span>
    </div>
  )
}
