import type { ScenarioName } from '@/mock/replayer'

/**
 * Dev-only control for driving the mock event replayer. Rendered only when
 * VITE_SSE_URL is unset (see useGreenlitStream) — never shown against a real
 * backend, so it doesn't violate the one-page/no-settings constraint for the
 * actual demo surface.
 */
export function ScenarioControls({ onReplay }: { onReplay: (scenario: ScenarioName) => void }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-[var(--color-fg-muted)]">Mock replay:</span>
      <button
        type="button"
        onClick={() => onReplay('success')}
        className="rounded-md border border-[var(--color-border)] px-2.5 py-1 text-[var(--color-fg-muted)] transition-colors hover:border-[var(--color-pass)] hover:text-[var(--color-pass)]"
      >
        Success run
      </button>
      <button
        type="button"
        onClick={() => onReplay('unresolved')}
        className="rounded-md border border-[var(--color-border)] px-2.5 py-1 text-[var(--color-fg-muted)] transition-colors hover:border-[var(--color-fail)] hover:text-[var(--color-fail)]"
      >
        Unresolved run
      </button>
    </div>
  )
}
