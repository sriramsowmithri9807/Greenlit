import { AnimatePresence, motion } from 'framer-motion'
import { CircleCheck, ExternalLink, GitPullRequest, Info, RotateCcw, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { DashboardState } from '@/state/dashboardReducer'

interface Outcome {
  tone: 'pass' | 'fail' | 'neutral'
  icon: ReactNode
  title: string
  body: string
  action?: { label: string; href?: string; onClick?: () => void }
}

function outcomeFor(state: DashboardState, onRestart: () => void): Outcome | null {
  const total = state.issues.length
  const fixed = state.issues.filter((i) => i.status === 'fixed').length
  const repo = state.repo?.full_name ?? 'this repo'

  if (state.status === 'error') {
    return {
      tone: 'fail',
      icon: <TriangleAlert size={20} />,
      title: 'The run stopped',
      body: state.error ?? 'Something went wrong.',
      action: { label: 'Try again', onClick: onRestart },
    }
  }
  if (state.phase !== 'done') return null
  if (state.status === 'clean') {
    return { tone: 'pass', icon: <CircleCheck size={20} />, title: `No issues found in ${repo}`, body: 'Every test passes and the code review came back clean.' }
  }
  if (state.pr) {
    return {
      tone: 'pass',
      icon: <GitPullRequest size={20} />,
      title: `Pull request #${state.pr.number} is ready for review`,
      body: `${fixed} of ${total} issue${total === 1 ? '' : 's'} fixed, each verified by the test suite in a sandbox.${
        fixed < total ? ' Greenlit commented on the rest with what it tried.' : ''
      }`,
      action: { label: 'Open pull request', href: state.pr.url },
    }
  }
  if (state.repo?.mode === 'dry_run') {
    return {
      tone: 'neutral',
      icon: <Info size={20} />,
      title: `Dry run finished: ${fixed} of ${total} fixes verified`,
      body: 'Nothing was pushed. The combined diff is on the right. Add a token to raise these as issues and open a pull request.',
    }
  }
  return {
    tone: 'neutral',
    icon: <Info size={20} />,
    title: 'No fix passed verification',
    body: 'Nothing was pushed. Greenlit commented on each issue with what it tried.',
  }
}

const TONE_CLASSES: Record<Outcome['tone'], string> = {
  pass: 'border-[var(--color-pass)]/50 bg-[var(--color-pass)]/[0.08] text-[var(--color-pass)]',
  fail: 'border-[var(--color-fail)]/50 bg-[var(--color-fail)]/[0.08] text-[var(--color-fail)]',
  neutral: 'border-[var(--color-border)] bg-[var(--color-surface-raised)] text-[var(--color-fg)]',
}

export function ResultBanner({ state, onRestart }: { state: DashboardState; onRestart: () => void }) {
  const reducedMotion = usePrefersReducedMotion()
  const outcome = outcomeFor(state, onRestart)

  return (
    <AnimatePresence>
      {outcome && (
        <motion.div
          role="status"
          className={`mx-6 mb-4 flex flex-wrap items-center gap-4 rounded-xl border px-4 py-3 ${TONE_CLASSES[outcome.tone]}`}
          initial={reducedMotion ? false : { opacity: 0, y: -8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
          transition={reducedMotion ? { duration: 0 } : { duration: 0.4, ease: 'easeOut' }}
        >
          <span className="shrink-0">{outcome.icon}</span>
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="text-sm font-semibold">{outcome.title}</span>
            <span className="text-sm whitespace-pre-wrap text-[var(--color-fg-muted)]">{outcome.body}</span>
          </span>
          {outcome.action &&
            (outcome.action.href ? (
              <a
                href={outcome.action.href}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 rounded-lg bg-[var(--color-pass)] px-3 py-2 text-sm font-semibold text-[#052e14] hover:opacity-90"
              >
                {outcome.action.label} <ExternalLink size={14} />
              </a>
            ) : (
              <button
                type="button"
                onClick={outcome.action.onClick}
                className="flex items-center gap-1.5 rounded-lg border border-current px-3 py-2 text-sm font-semibold hover:bg-white/5"
              >
                <RotateCcw size={14} /> {outcome.action.label}
              </button>
            ))}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
