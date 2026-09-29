import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import type { AlertOut } from '../lib/api/client'
import { queryKeys } from '../lib/api/hooks'
import {
  LiveSocket,
  RingBuffer,
  RING_SIZE,
  wsUrl,
  type LiveFrame,
  type ReplayInfo,
  type SocketState,
} from '../lib/live'

export type { LiveFrame, ReplayInfo }

type LiveMsg =
  | { type: 'hello'; well_id: number; wellbore_id: number; replay: ReplayInfo | null }
  | { type: 'frame'; frame: LiveFrame }
  | { type: 'status'; stale: boolean; replay: ReplayInfo | null }
  | { type: 'error'; error: { code: number | string; message?: string } }

export interface LiveWell {
  state: SocketState
  /** No message for 10 s (socket), or the backend says no frame for 30 s (stream). */
  stale: boolean
  frames: LiveFrame[]
  latest: LiveFrame | null
  replay: ReplayInfo | null
  /** Final close reason: 4401 log in, 4403 role, 4404 unknown well. */
  closedCode: number | null
  /** Wall time the last frame arrived, for the "updated N s ago" label. */
  receivedAt: number | null
}

const EMPTY: LiveWell = {
  state: 'connecting',
  stale: false,
  frames: [],
  latest: null,
  replay: null,
  closedCode: null,
  receivedAt: null,
}

export function useLiveWell(wellId: number | null, token?: string | null): LiveWell {
  // State is tagged with its well, so switching wells shows EMPTY until the new socket speaks.
  const [tagged, setTagged] = useState<{ well: number | null; live: LiveWell }>({
    well: null,
    live: EMPTY,
  })
  const ring = useRef(new RingBuffer<LiveFrame>(RING_SIZE))
  useEffect(() => {
    if (wellId === null) return
    ring.current.clear()
    const setLive = (f: (l: LiveWell) => LiveWell) =>
      setTagged((t) => ({ well: wellId, live: f(t.well === wellId ? t.live : EMPTY) }))
    let socketStale = false
    let streamStale = false
    const sock = new LiveSocket<LiveMsg>({
      url: wsUrl(`/ws/wells/${wellId}/live`, token),
      onMessage: (m) => {
        if (m.type === 'frame') {
          ring.current.push(m.frame)
          streamStale = false
          setLive((l) => ({
            ...l,
            frames: ring.current.toArray(),
            latest: m.frame,
            stale: socketStale,
            receivedAt: Date.now(),
          }))
        } else if (m.type === 'status') {
          streamStale = m.stale
          setLive((l) => ({ ...l, replay: m.replay, stale: socketStale || streamStale }))
        } else if (m.type === 'hello') {
          setLive((l) => ({ ...l, replay: m.replay }))
        }
      },
      onState: (state, detail) =>
        setLive((l) => ({ ...l, state, closedCode: detail?.code ?? l.closedCode })),
      onStale: (s) => {
        socketStale = s
        setLive((l) => ({ ...l, stale: s || streamStale }))
      },
    }).start()
    return () => sock.stop()
  }, [wellId, token])
  return tagged.well === wellId ? tagged.live : EMPTY
}

/** Wall clock that ticks every `ms`, for "updated N s ago" labels. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(t)
  }, [ms])
  return now
}

type AlertMsg =
  | { type: 'hello'; well_id: number | null }
  | { type: 'alert'; action: 'created' | 'fused'; alert: AlertOut }

/**
 * /ws/alerts: every alert created or fused. Each one refreshes the cached lists and the
 * alert's own detail, and is handed to `onAlert` (toasts, the title badge).
 */
export function useAlertsFeed(
  opts: {
    wellId?: number | null
    token?: string | null
    enabled?: boolean
    onAlert?: (a: AlertOut, action: string) => void
  } = {},
): SocketState {
  const { wellId = null, token = null, enabled = true, onAlert } = opts
  const client = useQueryClient()
  const [state, setState] = useState<SocketState>('connecting')
  const cb = useRef(onAlert)
  useEffect(() => {
    cb.current = onAlert
  }, [onAlert])
  useEffect(() => {
    if (!enabled) return
    const path = wellId === null ? '/ws/alerts' : `/ws/alerts?well_id=${wellId}`
    const sock = new LiveSocket<AlertMsg>({
      url: wsUrl(path, token),
      // Alerts are rare; the socket has no heartbeat, so silence is not staleness.
      staleAfterMs: Number.POSITIVE_INFINITY,
      onMessage: (m) => {
        if (m.type !== 'alert') return
        client.setQueryData(queryKeys.alert(m.alert.id), m.alert)
        void client.invalidateQueries({ queryKey: ['alerts'] })
        cb.current?.(m.alert, m.action)
      },
      onState: (s) => setState(s),
    }).start()
    return () => sock.stop()
  }, [client, wellId, token, enabled])
  return state
}
