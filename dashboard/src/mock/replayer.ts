import type { GreenlitEvent } from '@/types/events'
import { buildMockPublish, buildMockRun, type MockOptions, type TimedEvent } from './scenarios'

export interface MockRun {
  cancel: () => void
  /** Answers the scripted run's publish question and plays the rest. */
  answer: (approve: boolean) => void
}

/** Fires a scripted run's events on a timer. A live run pauses at the
 * publish question until `answer` is called, like the real backend. */
export function playMockRun(options: MockOptions, dispatch: (event: GreenlitEvent) => void): MockRun {
  const timeouts: ReturnType<typeof setTimeout>[] = []
  let answered = false

  const play = (events: TimedEvent[]) => {
    let elapsed = 0
    for (const { event, delay } of events) {
      elapsed += delay
      timeouts.push(setTimeout(() => dispatch(event), elapsed))
    }
  }

  play(buildMockRun(options))
  return {
    cancel: () => timeouts.forEach(clearTimeout),
    answer: (approve) => {
      if (answered) return
      answered = true
      play(buildMockPublish(options, approve))
    },
  }
}
