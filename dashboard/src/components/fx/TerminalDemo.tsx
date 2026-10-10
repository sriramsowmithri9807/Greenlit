import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

type Kind = 'cmd' | 'out' | 'fail' | 'pass' | 'ai' | 'ask' | 'ok' | 'diff-del' | 'diff-add'

/** An illustrative run, typed out on a loop on the start screen. */
const SCRIPT: { kind: Kind; text: string; pause?: number }[] = [
  { kind: 'cmd', text: 'greenlit scan github.com/octo/calculator --live' },
  { kind: 'out', text: 'cloned octo/calculator (main) → nebius sandbox' },
  { kind: 'fail', text: 'test_add ......... FAILED  assert -1 == 5' },
  { kind: 'fail', text: 'test_average ..... FAILED  assert 3.0 == 2' },
  { kind: 'ai', text: 'nemotron-ultra › review: divide() crashes when b == 0' },
  { kind: 'ai', text: 'nemotron-ultra › plan: add() subtracts instead of adding' },
  { kind: 'diff-del', text: '  2  -     return a - b' },
  { kind: 'diff-add', text: '  2  +     return a + b' },
  { kind: 'pass', text: 'test_add ......... PASSED  (nano: PASS, suite clean)' },
  { kind: 'pass', text: 'test_average ..... PASSED  (nano: PASS, suite clean)' },
  { kind: 'pass', text: 'divide guard ..... VERIFIED  no regressions' },
  { kind: 'ask', text: 'Raise the pull request on octo/calculator? [y/N] y', pause: 900 },
  { kind: 'ok', text: '✓ PR #15 opened · closes #12 #13 #14', pause: 2600 },
]

const STYLE: Record<Kind, string> = {
  cmd: 'text-[var(--color-fg)]',
  out: 'text-[var(--color-fg-muted)]',
  fail: 'text-[var(--color-fail)]',
  pass: 'text-[var(--color-pass)]',
  ai: 'text-[var(--color-done)]',
  ask: 'text-[var(--color-amber)]',
  ok: 'text-[var(--color-pass)] font-bold',
  'diff-del': 'bg-[var(--color-fail)]/10 text-[#fbc4c4]',
  'diff-add': 'bg-[var(--color-pass)]/10 text-[#b7f5c8]',
}

export function TerminalDemo() {
  const reducedMotion = usePrefersReducedMotion()
  const [step, setLine] = useState(0)
  const line = reducedMotion ? SCRIPT.length : step
  const [chars, setChars] = useState(0)
  const [run, setRun] = useState(0)

  useEffect(() => {
    if (reducedMotion) return
    if (line >= SCRIPT.length) {
      const id = setTimeout(() => {
        setLine(0)
        setChars(0)
        setRun((r) => r + 1)
      }, 1200)
      return () => clearTimeout(id)
    }
    const current = SCRIPT[line]
    // Commands are typed; output lines arrive whole, like a real terminal.
    if (current.kind === 'cmd' && chars < current.text.length) {
      const id = setTimeout(() => setChars((c) => c + 1), 28 + Math.random() * 40)
      return () => clearTimeout(id)
    }
    const id = setTimeout(
      () => {
        setLine((l) => l + 1)
        setChars(0)
      },
      current.pause ?? (current.kind === 'cmd' ? 500 : 380 + Math.random() * 380),
    )
    return () => clearTimeout(id)
  }, [line, chars, reducedMotion])

  const visible = SCRIPT.slice(0, Math.min(line + 1, SCRIPT.length))

  return (
    <div className="hud signal-border overflow-hidden rounded-xl border border-[var(--color-border)] shadow-2xl shadow-black/50">
      <div className="flex items-center gap-2 border-b border-[var(--color-border)] bg-black/30 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-fail)]/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-amber)]/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-pass)]/80" />
        <span className="ml-3 font-mono text-[11px] text-[var(--color-fg-muted)]">greenlit — sandbox://nebius</span>
        <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] tracking-widest text-[var(--color-pass)] uppercase">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-pass)]" /> live
        </span>
      </div>
      <div className="h-[340px] overflow-hidden px-4 py-3 font-mono text-[12.5px] leading-[1.75]">
        <AnimatePresence mode="popLayout">
          {visible.map((entry, i) => {
            const typing = i === line && entry.kind === 'cmd'
            const text = typing ? entry.text.slice(0, chars) : entry.text
            return (
              <motion.div
                key={`${run}-${i}`}
                initial={reducedMotion ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className={`whitespace-pre rounded px-1 ${STYLE[entry.kind]}`}
              >
                {entry.kind === 'cmd' && <span className="text-[var(--color-pass)]">$ </span>}
                {text}
                {(typing || (i === visible.length - 1 && line >= SCRIPT.length - 1)) && (
                  <span className="ml-0.5 inline-block h-[1.05em] w-[0.55em] translate-y-[3px] animate-blink bg-[var(--color-pass)]" />
                )}
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
