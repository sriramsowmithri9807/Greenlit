import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import { cn } from '@/lib/utils'

export type Light = 'red' | 'amber' | 'green' | 'off'

const CYCLE: Light[] = ['red', 'amber', 'green', 'green', 'green', 'green']

const LAMPS: { light: Exclude<Light, 'off'>; color: string }[] = [
  { light: 'red', color: 'var(--color-fail)' },
  { light: 'amber', color: 'var(--color-amber)' },
  { light: 'green', color: 'var(--color-pass)' },
]

/** A tiny traffic light. `cycle` runs red → amber → green and holds on green,
 * which is what the product does to a repo. */
export function SignalLight({ light, cycle = false, size = 8 }: { light?: Light; cycle?: boolean; size?: number }) {
  const reducedMotion = usePrefersReducedMotion()
  const [tick, setTick] = useState(0)
  const cycling = cycle && !reducedMotion

  useEffect(() => {
    if (!cycling) return
    const id = setInterval(() => setTick((t) => t + 1), 900)
    return () => clearInterval(id)
  }, [cycling])

  const step: Light = cycling ? CYCLE[tick % CYCLE.length] : cycle ? 'green' : (light ?? 'green')

  return (
    <span
      className="inline-flex items-center gap-[3px] rounded-full border border-[var(--color-border)] bg-black/40 px-[5px] py-[4px]"
      aria-hidden
    >
      {LAMPS.map(({ light: lamp, color }) => {
        const on = step === lamp
        return (
          <motion.span
            key={lamp}
            className="rounded-full"
            style={{ width: size, height: size }}
            animate={{
              backgroundColor: on ? color : 'rgba(139,152,165,0.18)',
              boxShadow: on ? `0 0 ${size}px ${size / 3}px color-mix(in oklab, ${color} 70%, transparent)` : '0 0 0 0 transparent',
            }}
            transition={{ duration: reducedMotion ? 0 : 0.35 }}
          />
        )
      })}
    </span>
  )
}

export function Wordmark({ className, light, cycle }: { className?: string; light?: Light; cycle?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5 font-[family-name:var(--font-display)] font-bold tracking-tight', className)}>
      <SignalLight light={light} cycle={cycle} />
      <span>
        Green<span className="text-signal">lit</span>
      </span>
    </span>
  )
}
