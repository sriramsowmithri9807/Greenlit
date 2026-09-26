import type { GreenlitEvent } from '@/types/events'
import { buildMockRun, type MockOptions } from './scenarios'

/** Fires a scripted run's events on a timer. Returns a cancel function. */
export function playMockRun(options: MockOptions, dispatch: (event: GreenlitEvent) => void): () => void {
  const timeouts: ReturnType<typeof setTimeout>[] = []
  let elapsed = 0
  for (const { event, delay } of buildMockRun(options)) {
    elapsed += delay
    timeouts.push(setTimeout(() => dispatch(event), elapsed))
  }
  return () => timeouts.forEach(clearTimeout)
}
