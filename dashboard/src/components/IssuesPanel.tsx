import { AnimatePresence, motion } from 'framer-motion'
import { CircleCheck, CircleDot, CircleX, ExternalLink, FlaskConical, GitCommitHorizontal, LoaderCircle, ScanSearch } from 'lucide-react'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import { cn } from '@/lib/utils'
import type { IssueStatus, UiIssue } from '@/state/dashboardReducer'
import type { Phase, RunStatus } from '@/types/events'

const STATUS_META: Record<IssueStatus, { label: string; color: string }> = {
  open: { label: 'Open', color: 'var(--color-fg-muted)' },
  fixing: { label: 'Fixing', color: 'var(--color-amber)' },
  fixed: { label: 'Fixed', color: 'var(--color-pass)' },
  unresolved: { label: 'Not fixed', color: 'var(--color-fail)' },
}

function StatusIcon({ status, reducedMotion }: { status: IssueStatus; reducedMotion: boolean }) {
  const color = STATUS_META[status].color
  if (status === 'fixing') {
    return <LoaderCircle size={16} style={{ color }} className={reducedMotion ? '' : 'animate-spin'} />
  }
  const Icon = status === 'fixed' ? CircleCheck : status === 'unresolved' ? CircleX : CircleDot
  return <Icon size={16} style={{ color }} />
}

function IssueRow({ issue, active, reducedMotion }: { issue: UiIssue; active: boolean; reducedMotion: boolean }) {
  const KindIcon = issue.kind === 'test' ? FlaskConical : ScanSearch
  return (
    <motion.li
      layout={!reducedMotion}
      initial={reducedMotion ? false : { opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.3, ease: 'easeOut' }}
      className={cn(
        'relative flex gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-300',
        active
          ? 'border-[var(--color-amber)]/60 bg-[var(--color-amber)]/[0.06]'
          : 'border-[var(--color-border)] bg-[var(--color-surface)]',
      )}
    >
      <span className="mt-0.5 shrink-0">
        <StatusIcon status={issue.status} reducedMotion={reducedMotion} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex items-center gap-2 text-[10px] font-semibold tracking-widest text-[var(--color-fg-muted)] uppercase">
          <span className="flex items-center gap-1">
            <KindIcon size={11} /> {issue.kind === 'test' ? 'Failing test' : 'Code review'}
          </span>
          {issue.severity && <span className="text-[var(--color-amber)]/80">{issue.severity}</span>}
          <span className="ml-auto" style={{ color: STATUS_META[issue.status].color }}>
            {STATUS_META[issue.status].label}
          </span>
        </span>
        <span className="line-clamp-2 text-sm leading-snug">{issue.title}</span>
        {issue.location && <span className="truncate font-mono text-[11px] text-[var(--color-fg-muted)]">{issue.location}</span>}
        {(issue.url || issue.commit) && (
          <span className="flex flex-wrap items-center gap-3 pt-0.5 text-[11px]">
            {issue.url && (
              <a href={issue.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[var(--color-done)] hover:underline">
                #{issue.number} <ExternalLink size={10} />
              </a>
            )}
            {issue.commit && (
              <a
                href={issue.commit.url ?? undefined}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 font-mono text-[var(--color-pass)] hover:underline"
              >
                <GitCommitHorizontal size={12} /> {issue.commit.sha.slice(0, 7)}
              </a>
            )}
          </span>
        )}
      </span>
    </motion.li>
  )
}

function EmptyState({ phase, status }: { phase: Phase | null; status: RunStatus }) {
  if (status === 'clean') {
    return <p className="px-4 py-6 text-sm text-[var(--color-pass)]">No issues found. Every test passes and review came back clean.</p>
  }
  if (status === 'error') {
    return <p className="px-4 py-6 text-sm text-[var(--color-fg-muted)]">The run stopped before any issues were found.</p>
  }
  return (
    <div className="flex flex-col gap-2 px-4 py-4" aria-live="polite">
      <p className="text-sm text-[var(--color-fg-muted)]">{phase === 'clone' ? 'Cloning the repo…' : 'Scanning for issues…'}</p>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-16 animate-pulse rounded-lg bg-[var(--color-surface-raised)]" style={{ animationDelay: `${i * 150}ms` }} />
      ))}
    </div>
  )
}

export function IssuesPanel({
  issues,
  currentKey,
  phase,
  status,
}: {
  issues: UiIssue[]
  currentKey: string | null
  phase: Phase | null
  status: RunStatus
}) {
  const reducedMotion = usePrefersReducedMotion()
  const fixed = issues.filter((i) => i.status === 'fixed').length
  const unresolved = issues.filter((i) => i.status === 'unresolved').length

  return (
    <Card className="flex min-h-0 flex-col overflow-hidden">
      <CardHeader>
        <CardTitle>Issues</CardTitle>
        {issues.length > 0 && (
          <span className="text-xs text-[var(--color-fg-muted)] tabular-nums">
            {issues.length} found · <span className="text-[var(--color-pass)]">{fixed} fixed</span>
            {unresolved > 0 && <span className="text-[var(--color-fail)]"> · {unresolved} not fixed</span>}
          </span>
        )}
      </CardHeader>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {issues.length === 0 ? (
          <EmptyState phase={phase} status={status} />
        ) : (
          <ul className="flex flex-col gap-2">
            <AnimatePresence initial={false}>
              {issues.map((issue) => (
                <IssueRow key={issue.key} issue={issue} active={issue.key === currentKey && issue.status === 'fixing'} reducedMotion={reducedMotion} />
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </Card>
  )
}
