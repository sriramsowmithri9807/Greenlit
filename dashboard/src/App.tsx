import confetti from 'canvas-confetti'
import { motion } from 'framer-motion'
import { useEffect, useRef } from 'react'
import { DiffViewer } from '@/components/DiffViewer'
import { Header } from '@/components/Header'
import { IssuesPanel } from '@/components/IssuesPanel'
import { IterationCounter } from '@/components/IterationCounter'
import { LogPanel } from '@/components/LogPanel'
import { PhaseStepper } from '@/components/PhaseStepper'
import { PipelineFlow } from '@/components/pipeline/PipelineFlow'
import { RepoChip } from '@/components/RepoChip'
import { ResultBanner } from '@/components/ResultBanner'
import { StartForm } from '@/components/StartForm'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { MOCK_MODE, useRun } from '@/hooks/useRun'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

function App() {
  const { state, view, start, reset, health, starting, startError } = useRun()
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
        <StartForm onStart={start} starting={starting} error={startError} health={health} mock={MOCK_MODE} />
      </div>
    )
  }

  const current = state.issues.find((issue) => issue.key === state.currentIssueKey)
  const pipelineTitle = current ? `Fixing ${current.number ? `#${current.number} · ` : ''}${current.title}` : 'Pipeline'
  const showFinalDiffLabel = state.phase === 'done' && state.repo?.mode === 'dry_run'

  return (
    <motion.div
      className="flex h-screen flex-col overflow-hidden"
      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.4, ease: 'easeOut' }}
    >
      <Header onNewScan={reset}>
        <RepoChip repo={state.repo} />
        <div className="ml-auto flex items-center gap-5">
          <IterationCounter count={state.iteration} />
          <StatusBadge status={state.status} />
        </div>
      </Header>

      <PhaseStepper phase={state.phase} status={state.status} dryRun={state.repo?.mode === 'dry_run'} />
      <ResultBanner state={state} onRestart={reset} />

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 px-6 pb-6 lg:grid-cols-[minmax(300px,360px)_1fr]">
        <IssuesPanel issues={state.issues} currentKey={state.currentIssueKey} phase={state.phase} status={state.status} />

        <div className="flex min-h-0 flex-col gap-4">
          <Card className="h-[200px] shrink-0 overflow-hidden">
            <CardHeader>
              <CardTitle className="truncate normal-case tracking-normal">{pipelineTitle}</CardTitle>
            </CardHeader>
            <div className="h-[calc(100%-2.75rem)]">
              <PipelineFlow state={state} />
            </div>
          </Card>

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-2">
            <Card className="flex min-h-[220px] flex-col overflow-hidden">
              <CardHeader>
                <CardTitle>{showFinalDiffLabel ? 'All verified changes' : 'Proposed fix'}</CardTitle>
              </CardHeader>
              <div className="min-h-0 flex-1">
                <DiffViewer diff={state.diff} revision={state.diffRevision} />
              </div>
            </Card>
            <Card className="flex min-h-[220px] flex-col overflow-hidden">
              <CardHeader>
                <CardTitle>Log</CardTitle>
              </CardHeader>
              <div className="min-h-0 flex-1">
                <LogPanel logs={state.logs} />
              </div>
            </Card>
          </div>
        </div>
      </main>
    </motion.div>
  )
}

export default App
