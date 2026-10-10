import { motion } from 'framer-motion'
import { Ban, Box, CircleCheck, CircleX, Flag, GitMerge, LoaderCircle, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import { cn } from '@/lib/utils'
import type { Lane, RaceState } from '@/state/dashboardReducer'
import type { Stage } from '@/types/events'

const TRACK: { stage: Stage; label: string }[] = [
  { stage: 'perceive', label: 'Perceive' },
  { stage: 'reproduce', label: 'Prove' },
  { stage: 'plan', label: 'Plan' },
  { stage: 'act', label: 'Act' },
  { stage: 'evaluate', label: 'Verify' },
]

const STATUS = {
  running: { color: 'var(--color-amber)', label: 'racing' },
  fixed: { color: 'var(--color-pass)', label: 'verified' },
  unresolved: { color: 'var(--color-fail)', label: 'not fixed' },
  dismissed: { color: 'var(--color-fg-muted)', label: 'not reproduced' },
} as const

function useClock(running: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(id)
  }, [running])
  return now
}

function seconds(s: number) {
  return s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`
}

function LaneRow({ lane, index, elapsed }: { lane: Lane; index: number; elapsed: number }) {
  const reducedMotion = usePrefersReducedMotion()
  const meta = STATUS[lane.status]
  const reached = lane.stage ? TRACK.findIndex((t) => t.stage === lane.stage) : -1
  const doneCount = TRACK.filter((t) => lane.done.includes(t.stage)).length
  const progress = lane.status !== 'running' ? 1 : Math.max(doneCount, reached + 0.5) / TRACK.length
  const Icon = lane.status === 'fixed' ? CircleCheck : lane.status === 'unresolved' ? CircleX : lane.status === 'dismissed' ? Ban : LoaderCircle

  return (
    <motion.div
      initial={reducedMotion ? false : { opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.07 }}
      className="relative grid shrink-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 overflow-hidden rounded-lg border border-[var(--color-border)] bg-black/25 px-3 py-1.5"
    >
      {/* Lane fill: how far this sandbox has got through the pipeline. */}
      <motion.span
        aria-hidden
        className="absolute inset-y-0 left-0"
        style={{ background: `linear-gradient(90deg, transparent, color-mix(in oklab, ${meta.color} 14%, transparent))` }}
        animate={{ width: `${progress * 100}%` }}
        transition={{ duration: reducedMotion ? 0 : 0.6, ease: 'easeOut' }}
      />
      {lane.status === 'running' && !reducedMotion && (
        <span aria-hidden className="pointer-events-none absolute inset-y-0 left-0 w-1/4 animate-beam bg-gradient-to-r from-transparent via-[var(--color-amber)]/10 to-transparent" />
      )}

      <span className="relative flex items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-black/40 px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-done)]">
        <Box size={11} /> SBX-{lane.sandbox}
      </span>

      <span className="relative flex min-w-0 flex-col gap-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-[13px] font-medium">{lane.title}</span>
          {lane.iteration > 1 && <span className="shrink-0 font-mono text-[10px] text-[var(--color-amber)]">try {lane.iteration}</span>}
          {lane.proof === 'reproduced' && <span className="shrink-0 font-mono text-[10px] text-[var(--color-done)]">proven</span>}
        </span>
        <span className="flex items-center gap-1">
          {TRACK.map((t) => {
            const done = lane.done.includes(t.stage)
            const active = lane.stage === t.stage
            return (
              <span key={t.stage} className="flex items-center gap-1">
                <motion.span
                  className={cn('h-1.5 w-1.5 rounded-full', active && !reducedMotion && 'animate-pulse')}
                  animate={{ backgroundColor: done ? 'var(--color-pass)' : active ? 'var(--color-amber)' : 'rgba(139,152,165,0.25)' }}
                  title={t.label}
                />
                <span className={cn('font-mono text-[9.5px] uppercase', active ? 'text-[var(--color-amber)]' : done ? 'text-[var(--color-fg-muted)]' : 'text-[var(--color-fg-muted)]/40')}>
                  {t.label}
                </span>
              </span>
            )
          })}
        </span>
        {lane.lastLog && lane.status === 'running' && (
          <span className="truncate font-mono text-[10.5px] text-[var(--color-fg-muted)]/80">{lane.lastLog}</span>
        )}
      </span>

      <span className="relative flex flex-col items-end gap-0.5">
        <span className="flex items-center gap-1 text-[11px] font-semibold" style={{ color: meta.color }}>
          <Icon size={13} className={lane.status === 'running' && !reducedMotion ? 'animate-spin' : ''} /> {meta.label}
        </span>
        <span className="font-mono text-[10.5px] text-[var(--color-fg-muted)] tabular-nums">{seconds(lane.seconds ?? elapsed)}</span>
      </span>
    </motion.div>
  )
}

/** Parallel fixing: one lane per issue, each in its own Nebius sandbox. */
export function RaceView({ race }: { race: RaceState }) {
  const finished = race.seconds !== null
  const now = useClock(!finished)
  const elapsed = finished ? (race.seconds ?? 0) : (now - race.startedAt) / 1000
  const speedup = finished && race.seconds && race.sequentialSeconds ? race.sequentialSeconds / race.seconds : null

  return (
    <div className="flex h-full flex-col gap-2 overflow-hidden px-3 pt-2 pb-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="flex items-center gap-1.5 font-[family-name:var(--font-display)] text-sm font-bold">
          <Zap size={15} className="text-[var(--color-amber)]" />
          {race.sandboxes} Nebius sandboxes in parallel
        </span>
        <span className="font-mono text-sm text-[var(--color-fg)] tabular-nums">{seconds(elapsed)}</span>
        {speedup && (
          <motion.span
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-1.5 rounded-full border border-[var(--color-pass)]/40 bg-[var(--color-pass)]/10 px-2.5 py-0.5 text-xs text-[var(--color-pass)]"
          >
            <Flag size={12} /> {speedup.toFixed(1)}× faster than one at a time (~{seconds(race.sequentialSeconds ?? 0)})
          </motion.span>
        )}
        <span className="ml-auto flex items-center gap-1.5 font-mono text-[11px] text-[var(--color-fg-muted)]">
          <GitMerge size={13} className={race.merge === 'clean' ? 'text-[var(--color-pass)]' : race.merge === 'running' ? 'text-[var(--color-amber)]' : ''} />
          {race.merge === 'pending' && 'merge pending'}
          {race.merge === 'running' && 'merging + re-verifying…'}
          {race.merge === 'clean' && 'merged cleanly, suite re-verified'}
          {race.merge === 'reworked' && 'merged one by one, re-verified'}
        </span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto">
        {race.order.map((key, i) => (
          <LaneRow key={key} lane={race.lanes[key]} index={i} elapsed={elapsed} />
        ))}
      </div>
    </div>
  )
}
