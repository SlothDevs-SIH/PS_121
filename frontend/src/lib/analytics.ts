/**
 * Analytics screen maths (screen 9, FRONTEND_PLAN §4.9): the URL filters, the bar and
 * heatmap scales and the formation × year grid. Charts are React SVG with these scales
 * (ADR-F16/F18/F19), so everything here is pure and unit-tested.
 */
import type { components } from './api/schema'
import { niceTicks } from './correlation'
import { formatNumber } from './format/units'

export type NptBreakdown = components['schemas']['NptBreakdown']
export type NptRow = components['schemas']['NptRow']
export type NptGroupBy = NptBreakdown['group_by']
export type RecurringProblems = components['schemas']['RecurringProblems']
export type AlertQuality = components['schemas']['AlertQuality']

/** A shift at the rig is 12 h, which is what the backend's alert rate is per. */
export const SHIFT_HOURS = 12
/** Formations drawn as heatmap rows (the biggest NPT first); one request each. */
export const HEATMAP_ROWS = 8
export const MIN_WELLS = { min: 2, max: 10, fallback: 3 } as const

export interface AnalyticsFilters {
  /** Event type code, or null for every problem. */
  type: string | null
  /** Formation name, or null for every formation. */
  fm: string | null
  /** Recurring problems: the same problem in at least this many wells. */
  minWells: number
}

export function parseFilters(params: URLSearchParams): AnalyticsFilters {
  const raw = Number(params.get('min') ?? MIN_WELLS.fallback)
  const minWells = Number.isInteger(raw)
    ? Math.min(MIN_WELLS.max, Math.max(MIN_WELLS.min, raw))
    : MIN_WELLS.fallback
  return { type: params.get('type') || null, fm: params.get('fm') || null, minWells }
}

/** The URL for a filter change: empty values and the default minimum are dropped. */
export function filtersToParams(
  current: URLSearchParams,
  patch: Partial<AnalyticsFilters>,
): URLSearchParams {
  const next = new URLSearchParams(current)
  const set = (key: string, v: string | null) => (v ? next.set(key, v) : next.delete(key))
  if ('type' in patch) set('type', patch.type ?? null)
  if ('fm' in patch) set('fm', patch.fm ?? null)
  if ('minWells' in patch)
    set(
      'min',
      patch.minWells && patch.minWells !== MIN_WELLS.fallback ? String(patch.minWells) : null,
    )
  return next
}

export interface LinearScale {
  /** Upper end of the domain, rounded up to the last tick. */
  max: number
  ticks: number[]
  /** Domain value → pixel along the range. */
  at: (v: number) => number
}

/** A zero-based linear scale onto [r0, r1] whose top is the "nice" tick at or above `max`. */
export function linearScale(max: number, r0: number, r1: number, tickCount = 5): LinearScale {
  const top = max > 0 ? max : 1
  let ticks = niceTicks(0, top, tickCount)
  const step = ticks.length > 1 ? ticks[1]! - ticks[0]! : top
  const last = ticks[ticks.length - 1] ?? 0
  if (last < top - 1e-9) ticks = [...ticks, Number((last + step).toFixed(10))]
  const domainMax = ticks[ticks.length - 1] ?? top
  return { max: domainMax, ticks, at: (v: number) => r0 + (v / domainMax) * (r1 - r0) }
}

export interface Band {
  key: string
  /** Start of the band in pixels, and its width (the gap between bands is excluded). */
  start: number
  size: number
}

/** Evenly split [r0, r1] into one band per key, `gap` pixels between neighbours. */
export function bandScale(keys: string[], r0: number, r1: number, gap = 2): Band[] {
  if (keys.length === 0) return []
  const step = (r1 - r0) / keys.length
  const size = Math.max(1, step - gap)
  return keys.map((key, i) => ({ key, start: r0 + i * step + (step - size) / 2, size }))
}

/** The five sequential heat steps: 0 is the lightest; values ≤ 0 draw no fill (-1). */
export const HEAT_STEPS = 5

export function heatStep(value: number, max: number): number {
  if (!(value > 0) || !(max > 0)) return -1
  return Math.min(HEAT_STEPS - 1, Math.max(0, Math.ceil((value / max) * HEAT_STEPS) - 1))
}

/** Fill opacity of one accent hue per step: a single-hue light → dark ramp. */
export function heatOpacity(step: number): number {
  return step < 0 ? 0 : 0.18 + (step / (HEAT_STEPS - 1)) * 0.72
}

/** Formations to draw as heatmap rows: known ones, biggest NPT first (the API's order). */
export function heatmapFormations(byFormation: NptBreakdown | undefined, n = HEATMAP_ROWS) {
  return (byFormation?.rows ?? [])
    .map((r) => r.key)
    .filter((k) => k !== 'unknown')
    .slice(0, n)
}

export interface HeatCell {
  formation: string
  year: string
  hours: number
  events: number
}

export interface HeatGrid {
  formations: string[]
  years: string[]
  cells: Map<string, HeatCell>
  max: number
}

export const cellKey = (formation: string, year: string) => `${formation}|${year}`

/** Formation × year cells from one by-year breakdown per formation. Years run in order
 * with the gaps filled, so an empty column says "no events that year"; "unknown" is last. */
export function heatmapGrid(rows: { formation: string; byYear: NptBreakdown }[]): HeatGrid {
  const cells = new Map<string, HeatCell>()
  const years = new Set<number>()
  let unknown = false
  let max = 0
  for (const { formation, byYear } of rows) {
    for (const r of byYear.rows) {
      const y = Number(r.key)
      if (Number.isInteger(y)) years.add(y)
      else unknown = true
      cells.set(cellKey(formation, r.key), {
        formation,
        year: r.key,
        hours: r.npt_hours,
        events: r.events,
      })
      max = Math.max(max, r.npt_hours)
    }
  }
  const sorted = [...years].sort((a, b) => a - b)
  const span: string[] = []
  if (sorted.length > 0)
    for (let y = sorted[0]!; y <= sorted[sorted.length - 1]!; y++) span.push(String(y))
  if (unknown) span.push('unknown')
  return { formations: rows.map((r) => r.formation), years: span, cells, max }
}

/** Year breakdowns come largest NPT first; a chart over time wants them in order. */
export function chronological(rows: NptRow[]): NptRow[] {
  return [...rows].sort((a, b) => {
    const x = Number(a.key)
    const y = Number(b.key)
    if (Number.isNaN(x)) return 1
    if (Number.isNaN(y)) return -1
    return x - y
  })
}

export function formatHours(h: number | null | undefined, digits = 1): string {
  return h === null || h === undefined ? '—' : `${formatNumber(h, digits)} h`
}

/** Alerts per 12 h shift, or a reason there is no rate yet. */
export function alertsPerShift(q: AlertQuality): string {
  if (q.alerts_per_12h === null) return 'no stream data scored yet'
  return `${formatNumber(q.alerts_per_12h, 2)} per ${SHIFT_HOURS} h shift`
}

/** A {label: count} map as bar rows, largest first (ties by label). */
export function countRows(counts: Record<string, number>): { key: string; value: number }[] {
  return Object.entries(counts)
    .map(([key, value]) => ({ key, value }))
    .sort((a, b) => b.value - a.value || a.key.localeCompare(b.key))
}
