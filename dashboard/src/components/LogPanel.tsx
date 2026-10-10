import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { LogEntry } from '@/state/dashboardReducer'

/** Stage prefixes the agent writes ("PLAN (Nemotron Ultra): …"), each with
 * its own colour so the log reads like a trace. */
const TAGS: [RegExp, string][] = [
  [/^PERCEIVE\b/, 'var(--color-done)'],
  [/^PLAN\b/, '#a78bfa'],
  [/^RESEARCH\b/, '#f472b6'],
  [/^ACT\b/, 'var(--color-amber)'],
  [/^EVALUATE\b/, 'var(--color-pass)'],
  [/^ERROR\b/, 'var(--color-fail)'],
]

function Line({ text }: { text: string }) {
  if (text.startsWith('Changed ')) return <span className="text-[var(--color-pass)]/90">{text}</span>
  const tag = TAGS.find(([pattern]) => pattern.test(text))
  const colon = text.indexOf(':')
  if (!tag || colon < 0 || colon > 40) return <span>{text}</span>
  return (
    <span>
      <span
        className="mr-1 rounded px-1 py-px text-[11px] font-bold"
        style={{ color: tag[1], backgroundColor: `color-mix(in oklab, ${tag[1]} 14%, transparent)` }}
      >
        {text.slice(0, colon)}
      </span>
      <span className="text-[var(--color-fg)]/85">{text.slice(colon + 1)}</span>
    </span>
  )
}

export function LogPanel({ logs, running = false }: { logs: LogEntry[]; running?: boolean }) {
  const reducedMotion = usePrefersReducedMotion()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: reducedMotion ? 'auto' : 'smooth' })
  }, [logs.length, reducedMotion])

  return (
    <div className="h-full overflow-y-auto bg-black/20 px-4 py-2 font-mono text-[12.5px] leading-relaxed text-[var(--color-fg-muted)]">
      {logs.length === 0 && <p className="text-[var(--color-fg-muted)]/60">Waiting for the run to start…</p>}
      <AnimatePresence initial={false}>
        {logs.map((log, i) => (
          <motion.div
            key={log.id}
            initial={reducedMotion ? false : { opacity: 0, x: -10, filter: 'blur(3px)' }}
            animate={{ opacity: i === logs.length - 1 ? 1 : 0.8, x: 0, filter: 'blur(0px)' }}
            transition={reducedMotion ? { duration: 0 } : { duration: 0.28, ease: 'easeOut' }}
            className="flex gap-2 whitespace-pre-wrap"
          >
            <span className="shrink-0 text-[var(--color-pass)]/50 select-none">›</span>
            <span className="min-w-0">
              <Line text={log.text} />
            </span>
          </motion.div>
        ))}
      </AnimatePresence>
      {running && (
        <div aria-hidden>
          <span className="mr-2 text-[var(--color-pass)]/50 select-none">›</span>
          <span className="inline-block h-[1em] w-[0.55em] translate-y-[2px] animate-blink bg-[var(--color-pass)]/80" />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
