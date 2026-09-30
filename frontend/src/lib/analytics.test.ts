import { describe, expect, it } from 'vitest'

import {
  alertsPerShift,
  bandScale,
  cellKey,
  chronological,
  countRows,
  filtersToParams,
  heatmapFormations,
  heatmapGrid,
  heatOpacity,
  heatStep,
  linearScale,
  parseFilters,
  type AlertQuality,
  type NptBreakdown,
  type NptRow,
} from './analytics'

const row = (key: string, npt_hours: number, events = 1): NptRow => ({
  key,
  events,
  wells: 1,
  npt_hours,
  share_of_npt: 0,
  median_npt_hours: null,
})

const breakdown = (group_by: NptBreakdown['group_by'], rows: NptRow[]): NptBreakdown => ({
  group_by,
  rows,
  total_events: rows.length,
  total_npt_hours: rows.reduce((a, r) => a + r.npt_hours, 0),
  events_without_npt: 0,
  synthetic: true,
})

describe('analytics filters in the URL', () => {
  it('reads type, formation and a clamped minimum number of wells', () => {
    expect(parseFilters(new URLSearchParams(''))).toEqual({ type: null, fm: null, minWells: 3 })
    expect(parseFilters(new URLSearchParams('type=LOSS&fm=Barail&min=5'))).toEqual({
      type: 'LOSS',
      fm: 'Barail',
      minWells: 5,
    })
    expect(parseFilters(new URLSearchParams('min=99')).minWells).toBe(10)
    expect(parseFilters(new URLSearchParams('min=1')).minWells).toBe(2)
    expect(parseFilters(new URLSearchParams('min=abc')).minWells).toBe(3)
  })

  it('writes changes back, dropping empty values and the default', () => {
    const start = new URLSearchParams('type=LOSS&other=keep')
    expect(filtersToParams(start, { fm: 'Tipam Sandstone' }).toString()).toBe(
      'type=LOSS&other=keep&fm=Tipam+Sandstone',
    )
    expect(filtersToParams(start, { type: null }).toString()).toBe('other=keep')
    expect(filtersToParams(start, { minWells: 4 }).get('min')).toBe('4')
    expect(filtersToParams(new URLSearchParams('min=4'), { minWells: 3 }).has('min')).toBe(false)
  })
})

describe('chart scales', () => {
  it('rounds a linear scale up to a nice last tick', () => {
    const s = linearScale(412.5, 0, 1000)
    expect(s.ticks).toEqual([0, 100, 200, 300, 400, 500])
    expect(s.max).toBe(500)
    expect(s.at(250)).toBe(500)
    expect(s.at(500)).toBe(1000)
  })

  it('keeps an exact top and inverts for vertical axes', () => {
    const s = linearScale(40, 150, 0)
    expect(s.ticks).toEqual([0, 10, 20, 30, 40])
    expect(s.at(0)).toBe(150)
    expect(s.at(40)).toBe(0)
  })

  it('never divides by zero when everything is zero', () => {
    const s = linearScale(0, 0, 100)
    expect(s.max).toBeGreaterThan(0)
    expect(s.at(0)).toBe(0)
  })

  it('splits a range into equal bands with a gap between neighbours', () => {
    const b = bandScale(['a', 'b', 'c', 'd'], 0, 100, 4)
    expect(b.map((x) => x.size)).toEqual([21, 21, 21, 21])
    expect(b.map((x) => x.start)).toEqual([2, 27, 52, 77])
    expect(bandScale([], 0, 100)).toEqual([])
  })

  it('maps heat to five steps, with no fill for empty or zero cells', () => {
    expect(heatStep(0, 100)).toBe(-1)
    expect(heatStep(5, 0)).toBe(-1)
    expect(heatStep(1, 100)).toBe(0)
    expect(heatStep(20, 100)).toBe(0)
    expect(heatStep(21, 100)).toBe(1)
    expect(heatStep(100, 100)).toBe(4)
    expect(heatOpacity(-1)).toBe(0)
    expect(heatOpacity(0)).toBeLessThan(heatOpacity(4))
    expect(heatOpacity(4)).toBeCloseTo(0.9)
  })
})

describe('formation × year heatmap', () => {
  it('draws the known formations with the most NPT', () => {
    const byFm = breakdown('formation', [row('Barail', 90), row('unknown', 50), row('Tipam', 20)])
    expect(heatmapFormations(byFm)).toEqual(['Barail', 'Tipam'])
    expect(heatmapFormations(byFm, 1)).toEqual(['Barail'])
    expect(heatmapFormations(undefined)).toEqual([])
  })

  it('fills the year gaps and puts an unknown year last', () => {
    const grid = heatmapGrid([
      { formation: 'Barail', byYear: breakdown('year', [row('2019', 40, 3), row('2016', 10)]) },
      { formation: 'Tipam', byYear: breakdown('year', [row('unknown', 5), row('2017', 60, 2)]) },
    ])
    expect(grid.formations).toEqual(['Barail', 'Tipam'])
    expect(grid.years).toEqual(['2016', '2017', '2018', '2019', 'unknown'])
    expect(grid.max).toBe(60)
    expect(grid.cells.get(cellKey('Barail', '2019'))).toEqual({
      formation: 'Barail',
      year: '2019',
      hours: 40,
      events: 3,
    })
    expect(grid.cells.has(cellKey('Barail', '2018'))).toBe(false)
  })

  it('orders years chronologically for the column chart', () => {
    const rows = chronological([row('2020', 1), row('unknown', 9), row('2011', 5)])
    expect(rows.map((r) => r.key)).toEqual(['2011', '2020', 'unknown'])
  })
})

describe('alert statistics helpers', () => {
  it('sorts counts largest first and names the shift rate', () => {
    expect(countRows({ b: 2, a: 2, c: 5 })).toEqual([
      { key: 'c', value: 5 },
      { key: 'a', value: 2 },
      { key: 'b', value: 2 },
    ])
    const q = { alerts_per_12h: 1.5 } as AlertQuality
    expect(alertsPerShift(q)).toBe('1.50 per 12 h shift')
    expect(alertsPerShift({ ...q, alerts_per_12h: null })).toBe('no stream data scored yet')
  })
})
