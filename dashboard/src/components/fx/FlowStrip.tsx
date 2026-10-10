import { motion } from 'framer-motion'
import { Eye, FlaskConical, GitPullRequest, ShieldCheck, Wrench } from 'lucide-react'
import { useEffect, useState } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

const STEPS = [
  { icon: FlaskConical, title: 'Scan', body: 'Tests in a Nebius sandbox + Nemotron code review' },
  { icon: Wrench, title: 'Fix', body: 'Nemotron Ultra plans a patch for each bug' },
  { icon: ShieldCheck, title: 'Verify', body: 'Kept only if the tests prove it works' },
  { icon: Eye, title: 'Review', body: 'Every file, line and change shown to you' },
  { icon: GitPullRequest, title: 'Raise PR', body: 'Only after you say yes' },
]

/** The pipeline as a strip of stations with a light travelling through. */
export function FlowStrip() {
  const reducedMotion = usePrefersReducedMotion()
  const [active, setActive] = useState(reducedMotion ? STEPS.length - 1 : 0)

  useEffect(() => {
    if (reducedMotion) return
    const id = setInterval(() => setActive((a) => (a + 1) % (STEPS.length + 1)), 1300)
    return () => clearInterval(id)
  }, [reducedMotion])

  const progress = Math.min(active, STEPS.length - 1) / (STEPS.length - 1)

  return (
    <div className="relative">
      {/* Track, filled up to the station that's lit. */}
      <div className="absolute top-[18px] right-[10%] left-[10%] hidden h-px bg-[var(--color-border)] sm:block">
        <motion.div
          className="h-full bg-gradient-to-r from-[var(--color-done)] to-[var(--color-pass)]"
          animate={{ width: active >= STEPS.length ? '100%' : `${progress * 100}%` }}
          transition={{ duration: reducedMotion ? 0 : 0.9, ease: 'easeInOut' }}
        />
        {!reducedMotion && (
          <motion.span
            className="absolute -top-[3px] h-[7px] w-[7px] rounded-full bg-[var(--color-pass)] shadow-[0_0_12px_4px_rgba(34,197,94,0.6)]"
            animate={{ left: active >= STEPS.length ? '100%' : `${progress * 100}%` }}
            transition={{ duration: 0.9, ease: 'easeInOut' }}
          />
        )}
      </div>
      <ol className="relative grid grid-cols-1 gap-4 sm:grid-cols-5">
        {STEPS.map(({ icon: Icon, title, body }, i) => {
          const lit = i <= active
          return (
            <li key={title} className="flex flex-col items-center gap-2 text-center">
              <motion.span
                className="flex h-9 w-9 items-center justify-center rounded-full border bg-[var(--color-bg)]"
                animate={{
                  borderColor: lit ? 'var(--color-pass)' : 'var(--color-border)',
                  color: lit ? 'var(--color-pass)' : 'var(--color-fg-muted)',
                  boxShadow: i === active ? '0 0 18px 2px rgba(34,197,94,0.45)' : '0 0 0 0 rgba(0,0,0,0)',
                  scale: i === active && !reducedMotion ? 1.12 : 1,
                }}
                transition={{ duration: reducedMotion ? 0 : 0.4 }}
              >
                <Icon size={16} />
              </motion.span>
              <span className="font-[family-name:var(--font-display)] text-xs font-semibold tracking-widest uppercase">{title}</span>
              <span className="max-w-[16ch] text-[11px] leading-snug text-[var(--color-fg-muted)]">{body}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
