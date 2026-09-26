import { RotateCcw } from 'lucide-react'
import type { ReactNode } from 'react'

export function Header({ children, onNewScan }: { children?: ReactNode; onNewScan: () => void }) {
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 px-6 pt-5 pb-4">
      <button type="button" onClick={onNewScan} className="text-xl font-bold tracking-tight" aria-label="Greenlit, start a new scan">
        Green<span className="text-[var(--color-pass)]">lit</span>
      </button>
      {children}
      <button
        type="button"
        onClick={onNewScan}
        className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-fg-muted)] transition-colors hover:border-[var(--color-fg-muted)] hover:text-[var(--color-fg)]"
      >
        <RotateCcw size={12} /> New scan
      </button>
    </header>
  )
}
