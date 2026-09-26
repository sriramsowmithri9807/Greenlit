import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { playMockRun } from '@/mock/replayer'
import { dashboardReducer, initialDashboardState } from '@/state/dashboardReducer'
import { EVENT_TYPES, type GreenlitEvent } from '@/types/events'

/** `?mock` (or `?mock=partial`) replays a scripted run instead of calling the
 * backend, for recording demos and building the UI without credentials. */
const mockParam = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search).get('mock')
export const MOCK_MODE = mockParam !== null

export interface StartInput {
  repoUrl: string
  token: string
  includeReview: boolean
}

export type Health =
  | { reachable: true; nebius_configured: boolean; tavily_configured: boolean }
  | { reachable: false }

function repoNameFromUrl(url: string): string {
  const match = url.trim().match(/github\.com[/:]([^/\s]+)\/([^/\s#?]+?)(?:\.git)?(?:[/#?].*)?$/) ?? url.trim().match(/^([^/\s]+)\/([^/\s]+)$/)
  return match ? `${match[1]}/${match[2]}` : 'octo/calculator'
}

export function useRun() {
  const [state, dispatch] = useReducer(dashboardReducer, initialDashboardState)
  const [view, setView] = useState<'form' | 'run'>('form')
  const [health, setHealth] = useState<Health | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const sourceRef = useRef<EventSource | null>(null)
  const cancelMockRef = useRef<() => void>(() => {})

  useEffect(() => {
    if (MOCK_MODE) return
    let cancelled = false
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => !cancelled && setHealth({ reachable: true, ...body }))
      .catch(() => !cancelled && setHealth({ reachable: false }))
    return () => {
      cancelled = true
    }
  }, [])

  const stopStreams = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
    cancelMockRef.current()
    cancelMockRef.current = () => {}
  }, [])

  useEffect(() => stopStreams, [stopStreams])

  const start = useCallback(
    async ({ repoUrl, token, includeReview }: StartInput) => {
      stopStreams()
      setStartError(null)
      dispatch({ type: 'reset' })

      if (MOCK_MODE) {
        setView('run')
        cancelMockRef.current = playMockRun(
          { repoFullName: repoNameFromUrl(repoUrl), live: token.trim() !== '', partial: mockParam === 'partial' },
          dispatch,
        )
        return
      }

      setStarting(true)
      try {
        const response = await fetch('/api/runs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo_url: repoUrl, token: token.trim() || null, include_review: includeReview }),
        })
        const body = await response.json().catch(() => ({}))
        if (!response.ok) {
          const detail = typeof body.detail === 'string' ? body.detail : `The server returned ${response.status}.`
          setStartError(detail)
          return
        }

        const source = new EventSource(`/api/runs/${body.run_id}/events`)
        sourceRef.current = source
        for (const type of EVENT_TYPES) {
          source.addEventListener(type, (e) => {
            dispatch({ type, ...JSON.parse((e as MessageEvent).data) } as GreenlitEvent)
          })
        }
        source.addEventListener('end', () => {
          source.close()
          sourceRef.current = null
        })
        source.onerror = () => {
          // EventSource retries on its own (resuming via Last-Event-ID); only a
          // closed source means the connection is gone for good.
          if (source.readyState === EventSource.CLOSED) {
            dispatch({ type: 'run_error', message: 'Lost the connection to the Greenlit server.' })
            dispatch({ type: 'status', value: 'error' })
          }
        }
        setView('run')
      } catch {
        setStartError("Couldn't reach the Greenlit server. Is it running? Start it with: python -m greenlit.server")
      } finally {
        setStarting(false)
      }
    },
    [stopStreams],
  )

  const reset = useCallback(() => {
    stopStreams()
    dispatch({ type: 'reset' })
    setView('form')
  }, [stopStreams])

  return { state, view, start, reset, health, starting, startError }
}
