/**
 * Real-time plumbing for the Live Well Monitor and the Alerts Center (F4).
 *
 * - `LiveSocket`: one WebSocket that reconnects on its own with exponential backoff
 *   (1, 2, 4 … 30 s), and calls itself stale when nothing arrives for `staleAfterMs`.
 *   The backend closes with 4401 (log in) / 4403 (role) / 4404 (no such well): those are
 *   final, so no reconnect.
 * - `RingBuffer`: the last N frames, so a long session never grows memory.
 *
 * URLs are same-origin (/ws/...), proxied by Vite in dev and nginx in the image.
 */

export const BACKOFF_START_MS = 1000
export const BACKOFF_MAX_MS = 30_000
export const STALE_AFTER_MS = 10_000
export const RING_SIZE = 360 // 6 min of 1 Hz frames
export const FINAL_CLOSE_CODES = new Set([4401, 4403, 4404])

export type SocketState = 'connecting' | 'open' | 'reconnecting' | 'closed'

/** Delay before reconnect attempt `n` (0-based): 1, 2, 4, 8, 16, 30, 30 … seconds. */
export function backoffMs(attempt: number): number {
  return Math.min(BACKOFF_MAX_MS, BACKOFF_START_MS * 2 ** attempt)
}

export function wsUrl(path: string, token?: string | null, loc: Location = window.location) {
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  const sep = path.includes('?') ? '&' : '?'
  const q = token ? `${sep}token=${encodeURIComponent(token)}` : ''
  return `${proto}//${loc.host}${path}${q}`
}

export class RingBuffer<T> {
  private items: T[] = []
  readonly size: number
  constructor(size: number = RING_SIZE) {
    this.size = size
  }

  push(item: T): void {
    this.items.push(item)
    if (this.items.length > this.size) this.items.splice(0, this.items.length - this.size)
  }

  toArray(): T[] {
    return this.items.slice()
  }

  get length(): number {
    return this.items.length
  }

  clear(): void {
    this.items = []
  }
}

export interface LiveSocketOptions<M> {
  url: string
  onMessage: (msg: M) => void
  onState?: (state: SocketState, detail?: { code?: number; reason?: string }) => void
  onStale?: (stale: boolean) => void
  staleAfterMs?: number
  /** Injected for tests. */
  WebSocketImpl?: typeof WebSocket
  now?: () => number
}

export class LiveSocket<M = unknown> {
  private ws: WebSocket | null = null
  private attempt = 0
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private staleTimer: ReturnType<typeof setInterval> | null = null
  private lastMessageAt = 0
  private stale = false
  private stopped = false
  state: SocketState = 'connecting'
  private readonly opts: LiveSocketOptions<M>

  constructor(opts: LiveSocketOptions<M>) {
    this.opts = opts
  }

  start(): this {
    this.stopped = false
    this.connect()
    const every = Math.min(1000, this.opts.staleAfterMs ?? STALE_AFTER_MS)
    this.staleTimer = setInterval(() => this.checkStale(), every)
    return this
  }

  stop(): void {
    this.stopped = true
    if (this.retryTimer) clearTimeout(this.retryTimer)
    if (this.staleTimer) clearInterval(this.staleTimer)
    this.retryTimer = this.staleTimer = null
    const ws = this.ws
    this.ws = null
    if (ws && ws.readyState <= 1) ws.close(1000)
    this.setState('closed')
  }

  private now(): number {
    return (this.opts.now ?? Date.now)()
  }

  private setState(s: SocketState, detail?: { code?: number; reason?: string }) {
    this.state = s
    this.opts.onState?.(s, detail)
  }

  private connect() {
    const Impl = this.opts.WebSocketImpl ?? WebSocket
    const ws = new Impl(this.opts.url)
    this.ws = ws
    this.setState(this.attempt === 0 ? 'connecting' : 'reconnecting')
    ws.onopen = () => {
      if (this.ws !== ws) return
      this.attempt = 0
      this.lastMessageAt = this.now()
      this.setState('open')
    }
    ws.onmessage = (ev: MessageEvent) => {
      if (this.ws !== ws) return
      this.lastMessageAt = this.now()
      if (this.stale) {
        this.stale = false
        this.opts.onStale?.(false)
      }
      let msg: M
      try {
        msg = JSON.parse(String(ev.data)) as M
      } catch {
        return
      }
      this.opts.onMessage(msg)
    }
    ws.onclose = (ev: CloseEvent) => {
      if (this.ws !== ws || this.stopped) return
      this.ws = null
      if (FINAL_CLOSE_CODES.has(ev.code)) {
        this.setState('closed', { code: ev.code, reason: ev.reason })
        return
      }
      const delay = backoffMs(this.attempt)
      this.attempt += 1
      this.setState('reconnecting', { code: ev.code })
      this.retryTimer = setTimeout(() => this.connect(), delay)
    }
    ws.onerror = () => {
      // onclose follows and schedules the retry.
    }
  }

  private checkStale() {
    if (this.state !== 'open') return
    const stale = this.now() - this.lastMessageAt > (this.opts.staleAfterMs ?? STALE_AFTER_MS)
    if (stale !== this.stale) {
      this.stale = stale
      this.opts.onStale?.(stale)
    }
  }
}

/** One scoring frame from /ws/wells/{id}/live (the stream service's `Frame.to_json`). */
export interface LiveFrame {
  ts: string
  values: Record<string, number | null>
  rig_state: string
  bit_depth_m: number | null
  bit_tvdss_m: number | null
  formation: string | null
  indicators: Record<string, number | null>
  scores: Record<string, number> | null
  latest_scores?: Record<string, number>
  dejavu: {
    matches: {
      signature_id: number
      event_type: string
      event_id: number | null
      well_id: number | null
      similarity: number
      minutes_before_event: number
    }[]
  } | null
  session_id?: number
}

export interface ReplayInfo {
  id: number
  status: string
  speed: number
  position: number
  total_rows: number | null
  data_now: string | null
}
