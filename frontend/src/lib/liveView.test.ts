import { describe, expect, it } from 'vitest'

import { RISK_PROFILE, REALTIME, liveFrame } from '../test/utils'
import type { RealtimeWindow } from './api/client'
import type { LiveFrame } from './live'
import { extent, linePath, lookAhead, mergeSeries, rigSegments, trend } from './liveView'
import type { RiskProfile } from './risk'

describe('live view helpers', () => {
  it('groups rig states into runs', () => {
    expect(rigSegments([0, 10, 20, 30], ['DRILLING', 'DRILLING', 'IN_SLIPS', 'DRILLING'])).toEqual([
      { state: 'DRILLING', from: 0, to: 20 },
      { state: 'IN_SLIPS', from: 20, to: 30 },
      { state: 'DRILLING', from: 30, to: 30 },
    ])
  })

  it('reads a trend with a tolerance', () => {
    expect(trend([0.1, 0.2])).toBe('up')
    expect(trend([0.3, 0.1])).toBe('down')
    expect(trend([0.1, null, 0.11])).toBe('flat')
    expect(trend([0.5])).toBe('flat')
  })

  it('breaks lines at gaps instead of drawing zero', () => {
    const d = linePath(
      [0, 1, 2, 3],
      [1, null, 2, 3],
      (x) => x,
      (y) => y,
    )
    expect(d).toBe('M0.0 1.0M2.0 2.0L3.0 3.0')
  })

  it('pads a flat extent so the line sits mid-strip', () => {
    const [lo, hi] = extent([5, 5, null])
    expect(lo).toBeLessThan(5)
    expect(hi).toBeGreaterThan(5)
    expect(extent([])).toEqual([0, 1])
  })

  it('finds the formation now and the next hazard below the bit', () => {
    const profile = RISK_PROFILE.body as unknown as RiskProfile
    const la = lookAhead(profile, 2120)
    expect(la.current?.formation).toBe('Girujan Clay')
    expect(la.next?.formation).toBe('Tipam Sandstone')
    expect(la.distanceM).toBe(30)
    expect(la.hazard?.event_type).toBe('LOSS')
    expect(lookAhead(profile, null).next).toBeNull()
    // Below the last top: nothing next.
    expect(lookAhead(profile, 3000).next).toBeNull()
  })

  it('appends pushed frames after the REST window and drops duplicates', () => {
    const win = REALTIME.body as unknown as RealtimeWindow
    const frames = [
      liveFrame({ ts: '2026-09-28T20:10:30Z' }), // already in the window
      liveFrame(),
    ] as unknown as LiveFrame[]
    const s = mergeSeries(win, frames, ['torque_knm'], 60)
    expect(s.times).toHaveLength(7)
    expect(s.values['torque_knm']!.at(-1)).toBe(13.4)
    expect(s.values['torque_knm']![2]).toBeNull()
    expect(s.rig.at(-1)).toBe('DRILLING')
  })

  it('keeps only the last window of data time', () => {
    const win = REALTIME.body as unknown as RealtimeWindow
    const late = liveFrame({ ts: '2026-09-28T22:00:00Z' }) as unknown as LiveFrame
    const s = mergeSeries(win, [late], ['torque_knm'], 60)
    expect(s.times).toEqual([Date.parse('2026-09-28T22:00:00Z')])
  })
})
