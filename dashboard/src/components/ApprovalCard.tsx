import { motion } from 'framer-motion'
import { GitPullRequest, LoaderCircle, ShieldQuestion, X } from 'lucide-react'
import { useState } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { PublishRequest } from '@/types/events'

/** The run is paused: nothing has been written to GitHub yet. */
export function ApprovalCard({
  request,
  onAnswer,
}: {
  request: PublishRequest
  onAnswer: (approve: boolean) => Promise<string | null>
}) {
  const reducedMotion = usePrefersReducedMotion()
  const [sending, setSending] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { totals } = request.changes

  async function answer(approve: boolean) {
    setSending(approve)
    setError(null)
    const failure = await onAnswer(approve)
    if (failure) {
      setError(failure)
      setSending(null)
    }
  }

  return (
    <motion.div
      role="alertdialog"
      aria-labelledby="approval-title"
      className="mx-6 mb-4 rounded-xl border border-[var(--color-amber)]/60 bg-[var(--color-amber)]/[0.07] px-4 py-3"
      initial={reducedMotion ? false : { opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="flex flex-wrap items-start gap-4">
        <ShieldQuestion size={20} className="mt-0.5 shrink-0 text-[var(--color-amber)]" />
        <div className="min-w-0 flex-1 space-y-1.5">
          <p id="approval-title" className="text-sm font-semibold text-[var(--color-amber)]">
            {request.commits
              ? `Raise a pull request on ${request.repo}?`
              : `Raise ${request.issues} issue${request.issues === 1 ? '' : 's'} on ${request.repo}?`}
          </p>
          <p className="text-sm text-[var(--color-fg-muted)]">
            {request.fixed} of {request.issues} fixes verified: {totals.files} file{totals.files === 1 ? '' : 's'} changed,{' '}
            <span className="font-mono text-[var(--color-pass)]">+{totals.added}</span>{' '}
            <span className="font-mono text-[var(--color-fail)]">-{totals.removed}</span>. Review the changes below. Nothing has been
            written to GitHub yet. Publishing will:
          </p>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-[var(--color-fg)]">
            {request.actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
          {error && <p className="text-sm text-[var(--color-fail)]">{error}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2 self-center">
          <button
            type="button"
            disabled={sending !== null}
            onClick={() => answer(false)}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm font-semibold text-[var(--color-fg-muted)] hover:bg-white/5 disabled:opacity-50"
          >
            {sending === false ? <LoaderCircle size={14} className="animate-spin" /> : <X size={14} />} Don't publish
          </button>
          <button
            type="button"
            disabled={sending !== null}
            onClick={() => answer(true)}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--color-pass)] px-3 py-2 text-sm font-semibold text-[#052e14] hover:opacity-90 disabled:opacity-50"
          >
            {sending === true ? <LoaderCircle size={14} className="animate-spin" /> : <GitPullRequest size={14} />}
            {request.commits ? 'Raise pull request' : 'Raise issues'}
          </button>
        </div>
      </div>
    </motion.div>
  )
}
