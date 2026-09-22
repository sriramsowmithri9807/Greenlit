import { useEffect, useReducer, useRef, useState } from 'react'
import { playScenario, type ScenarioName } from '@/mock/replayer'
import { dashboardReducer, initialDashboardState } from '@/state/dashboardReducer'
import { EVENT_TYPES, type GreenlitEvent } from '@/types/events'

// One-line swap to point at a real backend: set VITE_SSE_URL and this hook
// switches from the mock replayer to a live EventSource automatically.
const SSE_URL = import.meta.env.VITE_SSE_URL

export function useGreenlitStream() {
  const [state, dispatch] = useReducer(dashboardReducer, initialDashboardState)
  const [connected, setConnected] = useState(!SSE_URL)
  const cancelReplay = useRef<() => void>(() => {})

  useEffect(() => {
    if (!SSE_URL) return

    const source = new EventSource(SSE_URL)
    const listeners = EVENT_TYPES.map((type) => {
      const handler = (e: MessageEvent) => {
        const payload = JSON.parse(e.data) as Record<string, unknown>
        dispatch({ type, ...payload } as GreenlitEvent)
      }
      source.addEventListener(type, handler as EventListener)
      return { type, handler }
    })
    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)

    return () => {
      for (const { type, handler } of listeners) {
        source.removeEventListener(type, handler as EventListener)
      }
      source.close()
    }
  }, [])

  function replay(scenario: ScenarioName) {
    cancelReplay.current()
    dispatch({ type: 'reset' })
    cancelReplay.current = playScenario(scenario, dispatch)
  }

  return { state, isMock: !SSE_URL, connected, replay }
}
