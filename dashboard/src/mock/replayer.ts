import type { GreenlitEvent } from '@/types/events'
import { SUCCESS_SCENARIO, UNRESOLVED_SCENARIO, type TimedEvent } from './scenarios'

export type ScenarioName = 'success' | 'unresolved'

const SCENARIOS: Record<ScenarioName, TimedEvent[]> = {
  success: SUCCESS_SCENARIO,
  unresolved: UNRESOLVED_SCENARIO,
}

/**
 * Fires a scenario's events on a timer via `dispatch`. Returns a cancel
 * function; safe to call after the scenario has already finished.
 */
export function playScenario(name: ScenarioName, dispatch: (event: GreenlitEvent) => void): () => void {
  const timeouts: ReturnType<typeof setTimeout>[] = []
  let elapsed = 0

  for (const { event, delay } of SCENARIOS[name]) {
    elapsed += delay
    timeouts.push(setTimeout(() => dispatch(event), elapsed))
  }

  return () => {
    for (const t of timeouts) clearTimeout(t)
  }
}
