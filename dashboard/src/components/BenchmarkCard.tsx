import { motion } from 'framer-motion'
import { Trophy } from 'lucide-react'
import { useEffect, useState } from 'react'

interface Summary {
  tasks: number
  resolved: number
  resolve_rate: number
  claimed: number
  false_fix_rate: number
  reproduced: number
  avg_seconds: number
  avg_cost_usd: number
  savings_pct: number
}

/** The latest scripts/benchmark.py result, if one has been run. Shows
 * nothing at all otherwise (and never in demo mode): no made-up numbers. */
export function BenchmarkCard({ enabled }: { enabled: boolean }) {
  const [report, setReport] = useState<{ benchmark: string; finished_at: string; summary: Summary } | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    fetch('/api/benchmark')
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => !cancelled && body?.summary?.tasks && setReport(body))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [enabled])

  if (!report) return null
  const s = report.summary
  const stats = [
    { label: 'resolved', value: `${s.resolved}/${s.tasks}`, sub: `${Math.round(s.resolve_rate * 100)}%` },
    { label: 'false fixes', value: `${Math.round(s.false_fix_rate * 100)}%`, sub: `of ${s.claimed} claimed` },
    { label: 'per task', value: `$${s.avg_cost_usd.toFixed(3)}`, sub: `${Math.round(s.avg_seconds)}s avg` },
    { label: 'tiering saved', value: `${Math.round(s.savings_pct)}%`, sub: 'vs Ultra-only' },
  ]
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="hud rounded-xl border border-[var(--color-border)] p-3"
      style={{ ['--hud-accent' as string]: 'var(--color-amber)' }}
    >
      <div className="mb-2 flex items-center gap-2 text-xs">
        <Trophy size={14} className="text-[var(--color-amber)]" />
        <span className="font-[family-name:var(--font-display)] font-semibold">{report.benchmark}</span>
        <span className="ml-auto font-mono text-[10px] text-[var(--color-fg-muted)]">{report.finished_at.slice(0, 10)}</span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col">
            <span className="font-[family-name:var(--font-display)] text-lg font-bold text-[var(--color-fg)]">{stat.value}</span>
            <span className="font-mono text-[10px] text-[var(--color-fg-muted)] uppercase">{stat.label}</span>
            <span className="font-mono text-[10px] text-[var(--color-fg-muted)]/70">{stat.sub}</span>
          </div>
        ))}
      </div>
    </motion.div>
  )
}
