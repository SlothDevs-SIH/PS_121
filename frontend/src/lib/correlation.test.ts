import { describe, expect, it } from 'vitest'

import type { CorrelationPanel, CorrelationWell } from './api/client'
import {
  formatAligned,
  initialWindow,
  makeScale,
  mwDomain,
  niceTicks,
  panelFormations,
  tvdssAt,
  zoomWindow,
} from './correlation'

function well(overrides: Partial<CorrelationWell> = {}): CorrelationWell {
  return {
    well_id: 1,
    name: 'W1',
    status: 'completed',
    fluid_type: 'oil',
    synthetic: true,
    fallback_to_tvdss: false,
    reason: null,
    td_aligned: null,
    tracks: {
      formations: [
        {
          name: 'A',
          strat_order: 1,
          lithology: 'sand',
          top: 0,
          base: 1,
          top_tvdss_m: 100,
          base_tvdss_m: 500,
        },
        {
          name: 'B',
          strat_order: 2,
          lithology: 'shale',
          top: 1,
          base: 2,
          top_tvdss_m: 500,
          base_tvdss_m: 700,
        },
      ],
      casing_shoes: [],
      cement_tops: [],
      mud: [],
      events: [],
    },
    ...overrides,
  }
}

describe('scale and ticks', () => {
  it('maps the window onto the pixel height and back', () => {
    const s = makeScale({ lo: -100, hi: 3900 }, 800)
    expect(s.y(-100)).toBe(0)
    expect(s.y(3900)).toBe(800)
    expect(s.invert(s.y(1234.5))).toBeCloseTo(1234.5)
  })

  it('picks 1-2-2.5-5 steps inside the range', () => {
    expect(niceTicks(0, 3700, 8)).toEqual([0, 500, 1000, 1500, 2000, 2500, 3000, 3500])
    expect(niceTicks(-2280, 1570, 8)).toEqual([-2000, -1500, -1000, -500, 0, 500, 1000, 1500])
    expect(niceTicks(0, 1, 4)).toEqual([0, 0.25, 0.5, 0.75, 1])
    expect(niceTicks(5, 5)).toEqual([])
  })

  it('zooms about a centre and never leaves the axis', () => {
    const limits = { lo: 0, hi: 4000 }
    const z = zoomWindow(limits, 0.5, 1000, limits)
    expect(z.hi - z.lo).toBe(2000)
    expect((1000 - z.lo) / (z.hi - z.lo)).toBeCloseTo(0.25) // the centre keeps its place
    const edge = zoomWindow({ lo: 3000, hi: 4000 }, 3, 3900, limits)
    expect(edge.lo).toBeGreaterThanOrEqual(0)
    expect(edge.hi).toBeLessThanOrEqual(4000)
  })

  it('pads the backend axis a little', () => {
    const panel = { depth_axis: { min: 0, max: 1000, label: '', unit: 'm' } } as CorrelationPanel
    expect(initialWindow(panel)).toEqual({ lo: -20, hi: 1020 })
  })
})

describe('reading TVDSS back from an aligned position', () => {
  it('is the identity on TVDSS and for wells that fell back to it', () => {
    expect(tvdssAt(well(), 'TVDSS', 1234)).toBe(1234)
    expect(tvdssAt(well({ fallback_to_tvdss: true }), 'FORMATION_RELATIVE', 1234)).toBe(1234)
  })

  it('undoes flattening with one shift', () => {
    const w = well()
    w.tracks.formations = w.tracks.formations.map((f) => ({
      ...f,
      top: f.top_tvdss_m - 500,
      base: (f.base_tvdss_m ?? 0) - 500,
    }))
    expect(tvdssAt(w, 'FLATTEN_ON_TOP', 0)).toBe(500)
    expect(tvdssAt(w, 'FLATTEN_ON_TOP', -250)).toBe(250)
  })

  it('interpolates inside a formation on the relative axis, and is unknown below it', () => {
    expect(tvdssAt(well(), 'FORMATION_RELATIVE', 0.5)).toBe(300)
    expect(tvdssAt(well(), 'FORMATION_RELATIVE', 1.25)).toBe(550)
    expect(tvdssAt(well(), 'FORMATION_RELATIVE', 2.5)).toBeNull()
  })
})

describe('labels and domains', () => {
  it('names the reference in every alignment', () => {
    expect(formatAligned(2340, 'TVDSS', null, [], 'metric')).toBe('2,340 m TVDSS')
    expect(formatAligned(-120, 'FLATTEN_ON_TOP', 'Tipam', [], 'metric')).toBe(
      '120 m above Tipam top',
    )
    expect(formatAligned(80, 'FLATTEN_ON_TOP', 'Tipam', [], 'metric')).toBe('80 m below Tipam top')
    expect(formatAligned(0.2, 'FLATTEN_ON_TOP', 'Tipam', [], 'metric')).toBe('at Tipam top')
    expect(formatAligned(1.4, 'FORMATION_RELATIVE', null, ['A', 'B'], 'metric')).toBe('B · 40%')
    expect(formatAligned(304.8, 'TVDSS', null, [], 'oilfield')).toBe('1,000 ft TVDSS')
  })

  it('lists formations once, in stratigraphic order', () => {
    const b = well({ well_id: 2 })
    b.tracks.formations = [...b.tracks.formations].reverse()
    const panel = { wells: [well(), b] } as unknown as CorrelationPanel
    expect(panelFormations(panel)).toEqual(['A', 'B'])
  })

  it('shares one padded mud-weight domain, with a default when there is no mud', () => {
    const w = well()
    w.tracks.mud = [
      {
        mud_interval_id: 1,
        md_from_m: 0,
        md_to_m: 1,
        tvdss_from_m: 0,
        tvdss_to_m: 1,
        top: 0,
        base: 1,
        mw_sg: 1.1,
        ecd_sg: 1.25,
        mud_type: null,
        confidence: 1,
        verified: false,
        evidence: [],
      },
    ]
    const [lo, hi] = mwDomain({ wells: [w] } as unknown as CorrelationPanel)
    expect(lo).toBeLessThan(1.1)
    expect(hi).toBeGreaterThan(1.25)
    expect(mwDomain({ wells: [well()] } as unknown as CorrelationPanel)).toEqual([1, 2])
  })
})
