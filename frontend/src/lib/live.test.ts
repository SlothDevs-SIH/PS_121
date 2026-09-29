import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeWebSocket } from '../test/fakeWebSocket'
import { backoffMs, LiveSocket, RingBuffer, wsUrl } from './live'

describe('live plumbing', () => {
  it('backs off 1, 2, 4 … and caps at 30 s', () => {
    expect([0, 1, 2, 3, 4, 5, 6, 10].map(backoffMs)).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000,
    ])
  })

  it('builds same-origin ws URLs with the token in the query', () => {
    const loc = { protocol: 'https:', host: 'smriti.example' } as Location
    expect(wsUrl('/ws/alerts', null, loc)).toBe('wss://smriti.example/ws/alerts')
    expect(wsUrl('/ws/alerts?well_id=4', 'a b', loc)).toBe(
      'wss://smriti.example/ws/alerts?well_id=4&token=a%20b',
    )
  })

  it('keeps only the last N items', () => {
    const r = new RingBuffer<number>(3)
    for (let i = 0; i < 5; i++) r.push(i)
    expect(r.toArray()).toEqual([2, 3, 4])
    expect(r.length).toBe(3)
  })
})

describe('LiveSocket', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  const make = (onMessage = vi.fn()) => {
    const states: string[] = []
    const stale: boolean[] = []
    const sock = new LiveSocket({
      url: 'ws://x/ws/wells/4/live',
      onMessage,
      onState: (s) => states.push(s),
      onStale: (s) => stale.push(s),
      staleAfterMs: 10_000,
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    }).start()
    return { sock, states, stale, onMessage }
  }

  it('parses messages and reconnects with backoff after a drop', () => {
    const { sock, states, onMessage } = make()
    const first = FakeWebSocket.find('/ws/wells/4/live')!
    first.open()
    first.receive({ type: 'hello' })
    expect(onMessage).toHaveBeenCalledWith({ type: 'hello' })
    first.close(1006)
    expect(states.at(-1)).toBe('reconnecting')
    expect(FakeWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(999)
    expect(FakeWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
    FakeWebSocket.instances[1]!.close(1006) // second failure: waits 2 s
    vi.advanceTimersByTime(1999)
    expect(FakeWebSocket.instances).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(FakeWebSocket.instances).toHaveLength(3)
    FakeWebSocket.instances[2]!.open() // success resets the backoff
    expect(states.at(-1)).toBe('open')
    sock.stop()
    expect(states.at(-1)).toBe('closed')
  })

  it('does not retry after an auth or not-found close', () => {
    const { states } = make()
    FakeWebSocket.find('live')!.close(4403)
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(states.at(-1)).toBe('closed')
  })

  it('turns stale after 10 s of silence and fresh on the next message', () => {
    const { stale, sock } = make()
    const ws = FakeWebSocket.find('live')!
    ws.open()
    vi.advanceTimersByTime(9_000)
    expect(stale).toEqual([])
    vi.advanceTimersByTime(2_000)
    expect(stale).toEqual([true])
    ws.receive({ type: 'frame' })
    expect(stale).toEqual([true, false])
    sock.stop()
  })
})
