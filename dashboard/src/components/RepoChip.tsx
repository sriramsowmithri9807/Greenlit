import { FolderGit2 } from 'lucide-react'
import type { DashboardState } from '@/state/dashboardReducer'

export function RepoChip({ repo }: { repo: DashboardState['repo'] }) {
  if (!repo) return null
  const name = (
    <span className="flex items-center gap-1.5 font-mono text-sm text-[var(--color-fg)]">
      <FolderGit2 size={15} className="text-[var(--color-fg-muted)]" />
      {repo.full_name}
    </span>
  )
  return (
    <span className="flex min-w-0 items-center gap-2">
      {repo.url ? (
        <a href={repo.url} target="_blank" rel="noreferrer" className="truncate hover:underline">
          {name}
        </a>
      ) : (
        name
      )}
      <span
        className={
          repo.mode === 'live'
            ? 'rounded-full border border-[var(--color-pass)]/40 px-2 py-0.5 text-[10px] font-semibold tracking-widest text-[var(--color-pass)] uppercase'
            : 'rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] font-semibold tracking-widest text-[var(--color-fg-muted)] uppercase'
        }
      >
        {repo.mode === 'live' ? 'Live' : 'Dry run'}
      </span>
    </span>
  )
}
