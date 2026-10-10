import confetti from 'canvas-confetti'
import { motion } from 'framer-motion'
import { type ReactNode, useEffect, useRef } from 'react'
import { ApprovalCard } from '@/components/ApprovalCard'
import { ChangesPanel } from '@/components/ChangesPanel'
import { CostPanel } from '@/components/CostPanel'
import { DiffViewer } from '@/components/DiffViewer'
import { Backdrop, type BackdropMood } from '@/components/fx/Backdrop'
import type { Light } from '@/components/fx/Logo'
import { Header } from '@/components/Header'
import { IssuesPanel } from '@/components/IssuesPanel'
import { IterationCounter } from '@/components/IterationCounter'
import { LogPanel } from '@/components/LogPanel'
import { PhaseStepper } from '@/components/PhaseStepper'
import { PipelineFlow } from '@/components/pipeline/PipelineFlow'
import { RaceView } from '@/components/RaceView'
import { RepoChip } from '@/components/RepoChip'
import { ResultBanner } from '@/components/ResultBanner'
import { StartForm } from '@/components/StartForm'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { MOCK_MODE, useRun } from '@/hooks/useRun'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { RunStatus } from '@/types/events'

const MOOD: Record<RunStatus, BackdropMood> = {
  idle: 'idle',
  scanning: 'scanning',
  testing: 'working',
  awaiting_approval: 'review',
  publishing: 'success',
  clean: 'success',
  fixed: 'success',
  partial: 'review',
  unresolved: 'idle',
  error: 'error',
}

const LIGHT: Record<RunStatus, Light> = {
  idle: 'off',
  scanning: 'amber',
  testing: 'amber',
  awaiting_approval: 'amber',
  publishing: 'green',
  clean: 'green',
  fixed: 'green',
  partial: 'amber',
  unresolved: 'red',
  error: 'red',
}

/** Panels slide up one after another when the run view opens. */
function Enter({ i, className, children }: { i: number; className?: string; children: ReactNode }) {
  const reducedMotion = usePrefersReducedMotion()
  return (
    <motion.div
      className={className}
      initial={reducedMotion ? false : { opacity: 0, y: 18, filter: 'blur(4px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ duration: 0.55, delay: 0.1 + i * 0.09, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

function App() {
  const { state, view, start, reset, health, starting, startError, answerApproval } = useRun()
  const reducedMotion = usePrefersReducedMotion()
  const celebrated = useRef(false)

  useEffect(() => {
    if (state.status === 'fixed' && !celebrated.current) {
      celebrated.current = true
      if (!reducedMotion) {
        confetti({ particleCount: 130, spread: 75, origin: { y: 0.6 }, colors: ['#22c55e', '#4ade80', '#86efac', '#facc15'] })
      }
    }
    if (state.status !== 'fixed') celebrated.current = false
  }, [state.status, reducedMotion])

  if (view === 'form') {
    return (
      <div className="min-h-screen overflow-y-auto">
        <Backdrop mood="idle" />
        <StartForm onStart={start} starting={starting} error={startError} health={health} mock={MOCK_MODE} />
      </div>
    )
  }

  const current = state.issues.find((issue) => issue.key === state.currentIssueKey)
  const pipelineTitle = current ? `Fixing ${current.number ? `#${current.number} · ` : ''}${current.title}` : 'Pipeline'
  const awaitingApproval = state.approval !== null && state.approval.answer === null && state.status !== 'error'

  return (
    <motion.div
      className="flex h-screen flex-col overflow-hidden"
      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.4, ease: 'easeOut' }}
    >
      <Backdrop mood={MOOD[state.status]} />
      <Header onNewScan={reset} light={LIGHT[state.status]} running={state.phase !== 'done' && state.status !== 'error'}>
        <RepoChip repo={state.repo} />
        <div className="ml-auto flex items-center gap-5">
          {state.race ? <IterationCounter count={state.race.sandboxes} label="Sandboxes" /> : <IterationCounter count={state.iteration} />}
          <StatusBadge status={state.status} />
        </div>
      </Header>

      <PhaseStepper phase={state.phase} status={state.status} dryRun={state.repo?.mode === 'dry_run'} />
      {awaitingApproval && state.approval && <ApprovalCard request={state.approval.request} onAnswer={answerApproval} />}
      <ResultBanner state={state} onRestart={reset} />

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 px-6 pb-6 lg:grid-cols-[minmax(300px,360px)_1fr]">
        <Enter i={0} className="flex min-h-0 flex-col gap-4">
          <div className="flex min-h-0 flex-1 flex-col [&>*]:flex-1">
            <IssuesPanel issues={state.issues} currentKey={state.currentIssueKey} phase={state.phase} status={state.status} />
          </div>
          <CostPanel cost={state.cost} />
        </Enter>

        <div className="flex min-h-0 flex-col gap-4">
          <Enter i={1} className="shrink-0">
          <Card className={`${state.race ? 'h-[340px]' : 'h-[200px]'} shrink-0 overflow-hidden transition-[height] duration-500`}>
            <CardHeader>
              <CardTitle className="normal-case tracking-normal">{state.race ? 'Parallel fix race' : pipelineTitle}</CardTitle>
            </CardHeader>
            <div className="h-[calc(100%-2.75rem)]">
              {state.race ? <RaceView race={state.race} /> : <PipelineFlow state={state} />}
            </div>
          </Card>
          </Enter>

          <Enter
            i={2}
            className={`grid min-h-0 flex-1 grid-cols-1 gap-4 ${state.changes ? 'xl:grid-cols-[3fr_2fr]' : 'xl:grid-cols-2'}`}
          >
            <Card className="flex min-h-[220px] flex-col overflow-hidden">
              <CardHeader>
                <CardTitle>{state.changes ? 'Verified changes' : 'Proposed fix'}</CardTitle>
                {state.changes && (
                  <span className="font-mono text-xs text-[var(--color-fg-muted)]">
                    {state.changes.totals.files} file{state.changes.totals.files === 1 ? '' : 's'}{' '}
                    <span className="text-[var(--color-pass)]">+{state.changes.totals.added}</span>{' '}
                    <span className="text-[var(--color-fail)]">-{state.changes.totals.removed}</span>
                  </span>
                )}
              </CardHeader>
              <div className="min-h-0 flex-1">
                {state.changes ? <ChangesPanel changes={state.changes} /> : <DiffViewer diff={state.diff} revision={state.diffRevision} />}
              </div>
            </Card>
            <Card className="flex min-h-[220px] flex-col overflow-hidden">
              <CardHeader>
                <CardTitle>Log</CardTitle>
              </CardHeader>
              <div className="min-h-0 flex-1">
                <LogPanel logs={state.logs} running={state.phase !== 'done' && state.status !== 'error'} />
              </div>
            </Card>
          </Enter>
        </div>
      </main>
    </motion.div>
  )
}

export default App
