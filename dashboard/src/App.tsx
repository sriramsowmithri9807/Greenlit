import confetti from 'canvas-confetti'
import { motion } from 'framer-motion'
import { useEffect, useRef } from 'react'
import { DiffViewer } from '@/components/DiffViewer'
import { Header } from '@/components/Header'
import { IterationCounter } from '@/components/IterationCounter'
import { PipelineFlow } from '@/components/pipeline/PipelineFlow'
import { LogPanel } from '@/components/LogPanel'
import { ScenarioControls } from '@/components/ScenarioControls'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { useGreenlitStream } from '@/hooks/useGreenlitStream'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

function App() {
  const { state, isMock, replay } = useGreenlitStream()
  const reducedMotion = usePrefersReducedMotion()
  const wasFixed = useRef(false)

  useEffect(() => {
    if (state.status === 'fixed' && !wasFixed.current) {
      wasFixed.current = true
      if (!reducedMotion) {
        confetti({
          particleCount: 130,
          spread: 75,
          origin: { y: 0.6 },
          colors: ['#22c55e', '#4ade80', '#86efac', '#facc15'],
        })
      }
    }
    if (state.status !== 'fixed') {
      wasFixed.current = false
    }
  }, [state.status, reducedMotion])

  return (
    <motion.div
      className="flex h-screen flex-col overflow-hidden"
      initial={reducedMotion ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.5, ease: 'easeOut' }}
    >
      <div className="flex items-center justify-between px-6">
        <Header />
        <div className="flex items-center gap-5">
          {isMock && <ScenarioControls onReplay={replay} />}
          <IterationCounter count={state.iteration} />
          <StatusBadge status={state.status} />
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 px-6 pb-4 lg:grid-cols-[3fr_2fr]">
        <Card className="min-h-0 overflow-hidden">
          <CardHeader>
            <CardTitle>Pipeline</CardTitle>
          </CardHeader>
          <div className="h-[calc(100%-2.75rem)]">
            <PipelineFlow state={state} />
          </div>
        </Card>

        <Card className="min-h-0 overflow-hidden">
          <CardHeader>
            <CardTitle>Proposed fix</CardTitle>
          </CardHeader>
          <div className="h-[calc(100%-2.75rem)]">
            <DiffViewer diff={state.diff} revision={state.diffRevision} />
          </div>
        </Card>
      </div>

      <div className="px-6 pb-6">
        <Card className="h-48 overflow-hidden">
          <CardHeader>
            <CardTitle>Log</CardTitle>
          </CardHeader>
          <div className="h-[calc(100%-2.75rem)]">
            <LogPanel logs={state.logs} />
          </div>
        </Card>
      </div>
    </motion.div>
  )
}

export default App
