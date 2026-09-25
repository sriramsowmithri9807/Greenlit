import { motion } from 'framer-motion'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

interface IssueTrackerProps {
  currentIssue: { id: string; remaining: number } | null
  fixedCount: number
  unresolvedCount: number
}

/**
 * Only renders once a backend actually emits issue_start/issue_end — the
 * mock replayer's single-issue scenarios never do, so this stays hidden
 * for the demo-fixture flow and only appears for a real repo-wide run.
 */
export function IssueTracker({ currentIssue, fixedCount, unresolvedCount }: IssueTrackerProps) {
  const reducedMotion = usePrefersReducedMotion()

  if (!currentIssue && fixedCount === 0 && unresolvedCount === 0) return null

  return (
    <motion.div
      className="flex items-center gap-3 px-6 pb-3 font-mono text-xs text-[var(--color-fg-muted)]"
      initial={reducedMotion ? false : { opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.3 }}
    >
      {currentIssue && (
        <span>
          Working: <span className="text-[var(--color-fg)]">{currentIssue.id}</span>{' '}
          <span className="text-[var(--color-fg-muted)]">({currentIssue.remaining} remaining)</span>
        </span>
      )}
      <span className="text-[var(--color-pass)]">{fixedCount} fixed</span>
      {unresolvedCount > 0 && <span className="text-[var(--color-fail)]">{unresolvedCount} unresolved</span>}
    </motion.div>
  )
}
