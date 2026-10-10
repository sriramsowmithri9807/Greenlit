import { RotateCcw, Timer } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { type Light, Wordmark } from '@/components/fx/Logo'

/** mm:ss since the run view opened; freezes when the run stops. */
function RunClock({ running }: { running: boolean }) {
  const [started] = useState(() => Date.now())
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [running])

  const seconds = Math.floor((now - started) / 1000)
  return (
    <span className="flex items-center gap-1.5 font-mono text-xs text-[var(--color-fg-muted)] tabular-nums" title="Run time">
      <Timer size={13} className={running ? 'text-[var(--color-done)]' : ''} />
      {String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}
    </span>
  )
}

export function Header({
  children,
  onNewScan,
  light,
  running,
}: {
  children?: ReactNode
  onNewScan: () => void
  light: Light
  running: boolean
}) {
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 px-6 pt-5 pb-4">
      <button type="button" onClick={onNewScan} className="text-xl" aria-label="Greenlit, start a new scan">
        <Wordmark light={light} />
      </button>
      {children}
      <RunClock running={running} />
      <button
        type="button"
        onClick={onNewScan}
        className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-black/30 px-3 py-1.5 text-xs text-[var(--color-fg-muted)] transition-colors hover:border-[var(--color-pass)]/60 hover:text-[var(--color-fg)]"
      >
        <RotateCcw size={12} /> New scan
      </button>
    </header>
  )
}
