import { motion, type Variants } from 'framer-motion'
import { ArrowRight, Box, Brain, Cpu, KeyRound, LoaderCircle, TriangleAlert } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { BenchmarkCard } from '@/components/BenchmarkCard'
import { FlowStrip } from '@/components/fx/FlowStrip'
import { Wordmark } from '@/components/fx/Logo'
import { TerminalDemo } from '@/components/fx/TerminalDemo'
import type { Health, StartInput } from '@/hooks/useRun'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

interface StartFormProps {
  onStart: (input: StartInput) => void
  starting: boolean
  error: string | null
  health: Health | null
  mock: boolean
}

const STACK = [
  { icon: Brain, label: 'Nemotron 3 Ultra', detail: 'review + plan' },
  { icon: Cpu, label: 'Nemotron 3 Nano', detail: 'evaluate' },
  { icon: Box, label: 'Nebius sandboxes', detail: 'every test run' },
]

const rise: Variants = {
  hidden: { opacity: 0, y: 16, filter: 'blur(6px)' },
  show: (i: number) => ({ opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.6, delay: 0.08 * i, ease: [0.22, 1, 0.36, 1] } }),
}

function Banner({ health, mock }: { health: Health | null; mock: boolean }) {
  let text: string | null = null
  let tone = 'border-[var(--color-amber)]/40 bg-[var(--color-amber)]/10 text-[var(--color-amber)]'
  if (mock) {
    text = 'Demo mode: this plays a scripted run. Nothing is sent to GitHub or Nebius.'
    tone = 'border-[var(--color-done)]/40 bg-[var(--color-done)]/10 text-[var(--color-done)]'
  } else if (health && !health.reachable) {
    text = "Can't reach the Greenlit server. Start it with `python -m greenlit.server`, or add ?mock=1 to the URL for a scripted demo."
  } else if (health?.reachable && !health.nebius_configured) {
    text = 'This server has no Nebius credentials yet. Set NEBIUS_API_KEY and NEBIUS_AI_PROJECT in .env and restart it.'
  }
  if (!text) return null
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${tone}`}>
      <TriangleAlert size={14} className="mt-0.5 shrink-0" />
      <span>{text}</span>
    </div>
  )
}

export function StartForm({ onStart, starting, error, health, mock }: StartFormProps) {
  const reducedMotion = usePrefersReducedMotion()
  const [repoUrl, setRepoUrl] = useState('')
  const [token, setToken] = useState('')
  const [includeReview, setIncludeReview] = useState(true)
  const [parallel, setParallel] = useState(true)

  const serverBlocked = !mock && health !== null && (!health.reachable || !health.nebius_configured)
  const canSubmit = repoUrl.trim() !== '' && !starting && !serverBlocked
  const live = token.trim() !== ''
  const anim = (i: number) =>
    reducedMotion ? {} : { variants: rise, initial: 'hidden' as const, animate: 'show' as const, custom: i }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (canSubmit) onStart({ repoUrl, token, includeReview, parallel })
  }

  const inputClass =
    'w-full rounded-lg border border-[var(--color-border)] bg-black/40 px-3 py-2.5 font-mono text-sm outline-none transition-all duration-300 placeholder:text-[var(--color-fg-muted)]/50 focus:border-[var(--color-pass)] focus:shadow-[0_0_0_3px_rgba(34,197,94,0.15),0_0_24px_-4px_rgba(34,197,94,0.5)]'

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-12 px-4 py-8 sm:px-6 sm:py-12">
      <motion.div {...anim(0)} className="flex items-center justify-between">
        <Wordmark className="text-2xl" cycle />
        <span className="hidden items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/30 px-3 py-1 font-mono text-[11px] text-[var(--color-fg-muted)] sm:flex">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-pass)]" />
          NVIDIA Nemotron × Nebius Token Factory
        </span>
      </motion.div>

      <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-[1.05fr_1fr]">
        <div className="flex flex-col gap-6">
          <motion.h1 {...anim(1)} className="font-[family-name:var(--font-display)] text-5xl leading-[1.02] font-bold tracking-tight sm:text-6xl">
            Red tests in.
            <br />
            <span className="text-signal">Green PRs out.</span>
          </motion.h1>
          <motion.p {...anim(2)} className="max-w-xl text-base leading-relaxed text-[var(--color-fg-muted)]">
            Point Greenlit at a GitHub repo. It finds the bugs, fixes them, proves every fix with your own tests in an
            isolated sandbox, shows you exactly what changed, and raises the pull request once you approve.
          </motion.p>

          <motion.div {...anim(3)}>
            <Banner health={health} mock={mock} />
          </motion.div>

          <motion.form
            {...anim(4)}
            onSubmit={submit}
            className="hud flex flex-col gap-5 rounded-xl border border-[var(--color-border)] p-5 shadow-2xl shadow-black/40"
          >
            <label className="flex flex-col gap-1.5">
              <span className="font-mono text-[11px] font-semibold tracking-widest text-[var(--color-fg-muted)] uppercase">
                <span className="text-[var(--color-pass)]">01</span> GitHub repository
              </span>
              <input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                autoFocus
                spellCheck={false}
                className={inputClass}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="flex items-center gap-1.5 font-mono text-[11px] font-semibold tracking-widest text-[var(--color-fg-muted)] uppercase">
                <span className="text-[var(--color-pass)]">02</span> <KeyRound size={12} /> Access token{' '}
                <span className="font-normal normal-case tracking-normal">(optional)</span>
              </span>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="github_pat_…"
                autoComplete="off"
                spellCheck={false}
                className={inputClass}
              />
              <span className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
                Leave empty for a read-only dry run. To raise issues and a pull request, use a{' '}
                <a
                  href="https://github.com/settings/personal-access-tokens/new"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[var(--color-done)] underline-offset-2 hover:underline"
                >
                  fine-grained token
                </a>{' '}
                with Contents, Issues and Pull requests set to Read and write. Nothing is published until you approve.
              </span>
            </label>

            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                checked={includeReview}
                onChange={(e) => setIncludeReview(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[var(--color-pass)]"
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-sm">AI code review</span>
                <span className="text-xs text-[var(--color-fg-muted)]">
                  Also hunt for bugs no test catches (NVIDIA Nemotron 3 Ultra). Each one must be proven with a failing test
                  before it's fixed or raised.
                </span>
              </span>
            </label>

            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                checked={parallel}
                onChange={(e) => setParallel(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-[var(--color-pass)]"
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-sm">Parallel sandboxes</span>
                <span className="text-xs text-[var(--color-fg-muted)]">
                  Fix every issue at once, one Nebius sandbox each, then merge and re-verify the whole suite.
                </span>
              </span>
            </label>

            <motion.button
              type="submit"
              disabled={!canSubmit}
              whileHover={canSubmit && !reducedMotion ? { scale: 1.015 } : undefined}
              whileTap={canSubmit && !reducedMotion ? { scale: 0.985 } : undefined}
              className="sheen flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[var(--color-pass)] to-[#4ade80] px-4 py-3 font-[family-name:var(--font-display)] text-sm font-bold text-[#052e14] shadow-[0_0_30px_-6px_rgba(34,197,94,0.7)] transition-opacity disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              {starting && <LoaderCircle size={16} className="animate-spin" />}
              {starting ? 'Starting…' : live ? 'Scan, fix and open a PR' : 'Start dry run'}
              {!starting && <ArrowRight size={16} />}
            </motion.button>

            {error && (
              <p role="alert" className="text-sm text-[var(--color-fail)]">
                {error}
              </p>
            )}
          </motion.form>
        </div>

        <motion.div {...anim(3)} className="flex flex-col gap-4 lg:sticky lg:top-8">
          <TerminalDemo />
          <BenchmarkCard enabled={!mock} />
          <div className="grid grid-cols-3 gap-2">
            {STACK.map(({ icon: Icon, label, detail }, i) => (
              <motion.div
                key={label}
                {...anim(5 + i)}
                className="hud flex flex-col gap-1 rounded-lg border border-[var(--color-border)] px-3 py-2.5"
                style={{ ['--hud-accent' as string]: 'var(--color-done)' }}
              >
                <Icon size={14} className="text-[var(--color-done)]" />
                <span className="text-xs font-semibold">{label}</span>
                <span className="font-mono text-[10px] text-[var(--color-fg-muted)]">{detail}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

      <motion.div {...anim(8)}>
        <FlowStrip />
      </motion.div>

      <motion.p {...anim(9)} className="mx-auto max-w-3xl text-center text-xs leading-relaxed text-[var(--color-fg-muted)]/80">
        Your code is analysed by NVIDIA Nemotron on Nebius Token Factory and only ever runs inside Nebius sandboxes. Fixes
        always go to a new branch and pull request, never straight to your default branch. The token is used for this run
        only and isn't saved.
      </motion.p>
    </div>
  )
}
