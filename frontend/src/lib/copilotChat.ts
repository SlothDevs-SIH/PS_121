import { useCallback, useEffect, useRef, useState } from 'react'

import {
  applyEvent,
  newTurn,
  retryAfterSeconds,
  streamCopilot,
  type CopilotContext,
  type Turn,
} from './copilot'

export interface CopilotChat {
  turns: Turn[]
  /** True while an answer is streaming. */
  busy: boolean
  /** Seconds left before the rate limit allows another question (0 when it does). */
  retryIn: number
  /** Ask a question; a different question replaces one still streaming. False if ignored. */
  ask: (question: string, context: CopilotContext) => boolean
  /** Stop the streaming answer, keeping what has arrived. */
  stop: () => void
  clear: () => void
}

/**
 * A copilot conversation: each question streams into its own turn. One answer streams at a
 * time; the stream is aborted by `stop()`, by a new question, and when the owner unmounts.
 * The backend keeps no history, so each question is answered on its own.
 */
export function useCopilotChat(): CopilotChat {
  const [turns, setTurns] = useState<Turn[]>([])
  // The rate limit's end and the clock, ticking while it runs (a 429 sets it).
  const [limit, setLimit] = useState<{ until: number; now: number } | null>(null)
  const retryIn = limit ? Math.max(0, Math.ceil((limit.until - limit.now) / 1000)) : 0
  const current = useRef<{ controller: AbortController; id: number; question: string } | null>(null)
  const nextId = useRef(1)

  useEffect(() => () => current.current?.controller.abort(), [])

  const until = limit?.until ?? null
  useEffect(() => {
    if (until === null) return
    const id = window.setInterval(() => {
      const now = Date.now()
      setLimit(now >= until ? null : { until, now })
    }, 250)
    return () => window.clearInterval(id)
  }, [until])

  const update = useCallback((id: number, fn: (t: Turn) => Turn) => {
    setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)))
  }, [])

  const stop = useCallback(() => {
    const c = current.current
    if (!c) return
    current.current = null
    c.controller.abort()
    update(c.id, (t) => (t.status === 'streaming' ? { ...t, status: 'stopped' } : t))
  }, [update])

  const ask = useCallback(
    (question: string, context: CopilotContext) => {
      const q = question.trim()
      // Double submit (a second Enter or click before the first lands) asks nothing new.
      if (!q || current.current?.question === q) return false
      if (limit && Date.now() < limit.until) return false
      stop()
      const id = nextId.current++
      const controller = new AbortController()
      current.current = { controller, id, question: q }
      setTurns((ts) => [...ts, newTurn(id, q, context)])
      streamCopilot(q, context, (ev) => update(id, (t) => applyEvent(t, ev)), controller.signal)
        .catch((err: unknown) => {
          if (controller.signal.aborted) return
          const wait = retryAfterSeconds(err)
          if (wait !== null) {
            const now = Date.now()
            setLimit({ until: now + wait * 1000, now })
          }
          update(id, (t) => ({ ...t, status: 'error', error: err }))
        })
        .finally(() => {
          if (current.current?.id === id) current.current = null
        })
      return true
    },
    [limit, stop, update],
  )

  const clear = useCallback(() => {
    stop()
    setTurns([])
  }, [stop])

  return {
    turns,
    busy: turns.some((t) => t.status === 'streaming'),
    retryIn,
    ask,
    stop,
    clear,
  }
}
