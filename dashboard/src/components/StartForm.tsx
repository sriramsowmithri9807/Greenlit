import { motion } from 'framer-motion'
import { ArrowRight, FlaskConical, GitPullRequest, KeyRound, ScanSearch, TriangleAlert, Wrench } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Card } from '@/components/ui/card'
import type { Health, StartInput } from '@/hooks/useRun'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

interface StartFormProps {
  onStart: (input: StartInput) => void
  starting: boolean
  error: string | null
  health: Health | null
  mock: boolean
}

const STEPS = [
  { icon: FlaskConical, title: 'Scan', body: 'Runs your test suite in a Nebius sandbox and has Nemotron review the code.' },
  { icon: ScanSearch, title: 'Raise', body: 'Files each bug it finds as a GitHub issue.' },
  { icon: Wrench, title: 'Fix', body: 'Writes a fix and keeps it only if the tests prove it works.' },
  { icon: GitPullRequest, title: 'PR', body: 'Opens one pull request that closes the issues it fixed.' },
]

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

  const serverBlocked = !mock && health !== null && (!health.reachable || !health.nebius_configured)
  const canSubmit = repoUrl.trim() !== '' && !starting && !serverBlocked
  const live = token.trim() !== ''

  function submit(e: FormEvent) {
    e.preventDefault()
    if (canSubmit) onStart({ repoUrl, token, includeReview })
  }

  return (
    <motion.div
      className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-10 sm:py-16"
      initial={reducedMotion ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.5, ease: 'easeOut' }}
    >
      <div className="flex flex-col gap-2">
        <h1 className="text-4xl font-bold tracking-tight">
          Green<span className="text-[var(--color-pass)]">lit</span>
        </h1>
        <p className="text-base text-[var(--color-fg-muted)]">
          Point it at a GitHub repo. It finds the bugs, files them as issues, fixes them, proves each fix with your
          tests, and opens a pull request.
        </p>
      </div>

      <Banner health={health} mock={mock} />

      <Card className="p-5">
        <form onSubmit={submit} className="flex flex-col gap-5">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold tracking-widest text-[var(--color-fg-muted)] uppercase">
              GitHub repository
            </span>
            <input
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              autoFocus
              spellCheck={false}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2.5 font-mono text-sm outline-none transition-colors placeholder:text-[var(--color-fg-muted)]/50 focus:border-[var(--color-pass)]"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 text-xs font-semibold tracking-widest text-[var(--color-fg-muted)] uppercase">
              <KeyRound size={12} /> Access token <span className="font-normal normal-case tracking-normal">(optional)</span>
            </span>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="github_pat_…"
              autoComplete="off"
              spellCheck={false}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2.5 font-mono text-sm outline-none transition-colors placeholder:text-[var(--color-fg-muted)]/50 focus:border-[var(--color-pass)]"
            />
            <span className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
              Leave empty for a read-only dry run. To raise issues and open a pull request, use a{' '}
              <a
                href="https://github.com/settings/personal-access-tokens/new"
                target="_blank"
                rel="noreferrer"
                className="text-[var(--color-done)] underline-offset-2 hover:underline"
              >
                fine-grained token
              </a>{' '}
              for this repo with Contents, Issues and Pull requests set to Read and write.
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
                Also look for bugs no test catches (NVIDIA Nemotron 3 Ultra).
              </span>
            </span>
          </label>

          <button
            type="submit"
            disabled={!canSubmit}
            className="flex items-center justify-center gap-2 rounded-lg bg-[var(--color-pass)] px-4 py-2.5 text-sm font-semibold text-[#052e14] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {starting ? 'Starting…' : live ? 'Scan, fix and open a PR' : 'Start dry run'}
            {!starting && <ArrowRight size={16} />}
          </button>

          {error && (
            <p role="alert" className="text-sm text-[var(--color-fail)]">
              {error}
            </p>
          )}
        </form>
      </Card>

      <ol className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        {STEPS.map(({ icon: Icon, title, body }) => (
          <li key={title} className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 text-xs font-semibold tracking-widest text-[var(--color-fg)] uppercase">
              <Icon size={14} className="text-[var(--color-pass)]" /> {title}
            </span>
            <span className="text-xs leading-relaxed text-[var(--color-fg-muted)]">{body}</span>
          </li>
        ))}
      </ol>

      <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]/80">
        Your code is analysed by NVIDIA Nemotron on Nebius Token Factory and only ever runs inside Nebius sandboxes.
        Fixes always go to a new branch and pull request, never straight to your default branch. The token is used for
        this run only and isn't saved.
      </p>
    </motion.div>
  )
}
