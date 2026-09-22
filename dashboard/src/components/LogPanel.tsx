import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { LogEntry } from '@/state/dashboardReducer'

export function LogPanel({ logs }: { logs: LogEntry[] }) {
  const reducedMotion = usePrefersReducedMotion()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: reducedMotion ? 'auto' : 'smooth' })
  }, [logs.length, reducedMotion])

  return (
    <div className="h-full overflow-y-auto px-4 py-2 font-mono text-[12.5px] leading-relaxed text-[var(--color-fg-muted)]">
      {logs.length === 0 && <p className="text-[var(--color-fg-muted)]/60">Waiting for the run to start…</p>}
      <AnimatePresence initial={false}>
        {logs.map((log) => (
          <motion.div
            key={log.id}
            initial={reducedMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reducedMotion ? { duration: 0 } : { duration: 0.22, ease: 'easeOut' }}
            className="whitespace-pre-wrap"
          >
            <span className="mr-2 select-none text-[var(--color-border)]">&gt;</span>
            {log.text}
          </motion.div>
        ))}
      </AnimatePresence>
      <div ref={bottomRef} />
    </div>
  )
}
