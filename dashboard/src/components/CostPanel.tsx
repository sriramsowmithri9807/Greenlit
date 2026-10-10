import { animate, motion } from 'framer-motion'
import { Brain, Cpu, TrendingDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { CostState, TierCost } from '@/state/dashboardReducer'

const ULTRA = '#a78bfa'
const NANO = 'var(--color-done)'

function money(usd: number): string {
  if (usd === 0) return '$0.00'
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`
}

function tokens(n: number): string {
  return n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

/** A number that counts up to its new value. */
function Ticker({ value, format }: { value: number; format: (n: number) => string }) {
  const reducedMotion = usePrefersReducedMotion()
  const [shown, setShown] = useState(value)
  const from = useRef(value)

  useEffect(() => {
    if (reducedMotion) {
      from.current = value
      return
    }
    const controls = animate(from.current, value, {
      duration: 0.6,
      ease: 'easeOut',
      onUpdate: (v) => setShown(v),
    })
    from.current = value
    return () => controls.stop()
  }, [value, reducedMotion])

  return <span className="tabular-nums">{format(reducedMotion ? value : shown)}</span>
}

function SplitBar({ label, ultra, nano }: { label: string; ultra: number; nano: number }) {
  const total = ultra + nano
  const ultraPct = total ? (ultra / total) * 100 : 50
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between font-mono text-[10px] tracking-wider text-[var(--color-fg-muted)] uppercase">
        <span>{label}</span>
        <span>
          <span style={{ color: ULTRA }}>{total ? Math.round(ultraPct) : 0}%</span> /{' '}
          <span style={{ color: NANO }}>{total ? Math.round(100 - ultraPct) : 0}%</span>
        </span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-black/40">
        <motion.div className="h-full" style={{ background: ULTRA }} animate={{ width: `${total ? ultraPct : 0}%` }} transition={{ duration: 0.5 }} />
        <motion.div className="h-full" style={{ background: NANO }} animate={{ width: `${total ? 100 - ultraPct : 0}%` }} transition={{ duration: 0.5 }} />
      </div>
    </div>
  )
}

function TierRow({ name, detail, color, icon: Icon, cost, flash }: {
  name: string
  detail: string
  color: string
  icon: typeof Brain
  cost: TierCost
  flash: number
}) {
  return (
    <motion.div
      key={flash}
      className="flex items-center gap-2.5 rounded-lg border border-[var(--color-border)] bg-black/20 px-2.5 py-1.5"
      initial={flash ? { boxShadow: `0 0 0 1px ${color}, 0 0 16px -2px ${color}` } : false}
      animate={{ boxShadow: '0 0 0 0px rgba(0,0,0,0)' }}
      transition={{ duration: 0.9 }}
    >
      <Icon size={15} style={{ color }} className="shrink-0" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-xs font-semibold" style={{ color }}>
          {name}
        </span>
        <span className="truncate text-[10px] text-[var(--color-fg-muted)]">{detail}</span>
      </span>
      <span className="flex flex-col items-end font-mono text-[10.5px] leading-tight">
        <span className="text-[var(--color-fg)]">
          <Ticker value={cost.usd} format={money} />
        </span>
        <span className="text-[var(--color-fg-muted)]">
          {cost.calls} call{cost.calls === 1 ? '' : 's'} · {tokens(cost.tokens)} tok
        </span>
      </span>
    </motion.div>
  )
}

/** Live model spend, split by tier, with what tiering saved. */
export function CostPanel({ cost }: { cost: CostState }) {
  const total = cost.ultra.usd + cost.nano.usd
  const savings = cost.ultraOnlyUsd > 0 ? (1 - total / cost.ultraOnlyUsd) * 100 : 0
  const calls = cost.ultra.calls + cost.nano.calls

  return (
    <Card className="shrink-0 overflow-hidden" style={{ ['--hud-accent' as string]: ULTRA }}>
      <CardHeader>
        <CardTitle>Model spend</CardTitle>
        <span className="rounded border border-[var(--color-border)] px-1.5 font-mono text-[9.5px] tracking-wider text-[var(--color-fg-muted)] uppercase" title="Estimated from public Token Factory per-token prices">
          est.
        </span>
      </CardHeader>
      <div className="flex flex-col gap-2.5 p-3">
        <div className="flex items-baseline justify-between">
          <span className="font-[family-name:var(--font-display)] text-2xl font-bold">
            <Ticker value={total} format={money} />
          </span>
          <span className="font-mono text-[10.5px] text-[var(--color-fg-muted)]">{calls} Nemotron calls</span>
        </div>
        <TierRow name="Nemotron 3 Ultra" detail="review · plan · write tests" color={ULTRA} icon={Brain} cost={cost.ultra} flash={cost.lastTier === 'ultra' ? cost.pulse : 0} />
        <TierRow name="Nemotron 3 Nano" detail="evaluate · judge tests" color={NANO} icon={Cpu} cost={cost.nano} flash={cost.lastTier === 'nano' ? cost.pulse : 0} />
        {calls > 0 && (
          <>
            <SplitBar label="Calls" ultra={cost.ultra.calls} nano={cost.nano.calls} />
            <SplitBar label="Spend" ultra={cost.ultra.usd} nano={cost.nano.usd} />
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 rounded-lg border border-[var(--color-pass)]/30 bg-[var(--color-pass)]/[0.07] px-2.5 py-1.5 text-xs"
            >
              <TrendingDown size={14} className="shrink-0 text-[var(--color-pass)]" />
              <span>
                Routing to Nano saved{' '}
                <span className="font-bold text-[var(--color-pass)]">
                  <Ticker value={savings} format={(n) => `${Math.round(n)}%`} />
                </span>{' '}
                vs Ultra-only <span className="font-mono text-[var(--color-fg-muted)]">({money(cost.ultraOnlyUsd)})</span>
                {cost.nano.calls > 0 && (
                  <span className="block text-[11px] text-[var(--color-fg-muted)]">
                    Nano handled {Math.round((cost.nano.calls / calls) * 100)}% of calls for {total ? Math.max(1, Math.round((cost.nano.usd / total) * 100)) : 0}% of
                    the spend
                  </span>
                )}
              </span>
            </motion.div>
          </>
        )}
      </div>
    </Card>
  )
}
