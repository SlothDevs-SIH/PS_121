/**
 * Correlation panel maths, kept pure so it can be unit-tested (FRONTEND_PLAN §4.4).
 *
 * The backend sends every track already on the aligned axis (TVDSS, relative to a flattened
 * top, or formation index + fraction). Here: the pixel scale, ticks, zoom windows, and the
 * inverse mapping from an aligned position back to each well's own TVDSS, which the
 * crosshair shows per column.
 */
import type { Alignment, CorrelationPanel, CorrelationWell } from './api/client'
import { FT_TO_M, formatNumber, type UnitSystem } from './format/units'

/** Column layout (px): formations, casing & cement, mud weight, events. */
export const TRACK = { fm: 76, casing: 34, mud: 58, events: 48, gap: 3 } as const
export const COLUMN_WIDTH = TRACK.fm + TRACK.casing + TRACK.mud + TRACK.events + TRACK.gap * 3

export interface TrackToggles {
  casing: boolean
  mud: boolean
  events: boolean
}

export interface DepthWindow {
  lo: number
  hi: number
}

export function makeScale(win: DepthWindow, height: number) {
  const k = height / (win.hi - win.lo || 1)
  return {
    y: (v: number) => (v - win.lo) * k,
    invert: (px: number) => win.lo + px / k,
  }
}

/** Evenly spaced "nice" ticks (1, 2, 2.5 or 5 × 10ⁿ) inside [lo, hi], about `count` of them. */
export function niceTicks(lo: number, hi: number, count = 8): number[] {
  const span = hi - lo
  if (!(span > 0) || count < 1) return []
  const raw = span / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step)
    out.push(Number(v.toFixed(10)))
  return out
}

/** The axis extent with a little headroom, so the first top and TD aren't on the edge. */
export function initialWindow(panel: CorrelationPanel): DepthWindow {
  const { min, max } = panel.depth_axis
  const pad = (max - min || 1) * 0.02
  return { lo: min - pad, hi: max + pad }
}

/** Zoom by `factor` (< 1 zooms in) about `centre`, kept inside `limits`. */
export function zoomWindow(
  win: DepthWindow,
  factor: number,
  centre: number,
  limits: DepthWindow,
): DepthWindow {
  const full = limits.hi - limits.lo
  const span = Math.min(full, Math.max(full / 64, (win.hi - win.lo) * factor))
  let lo = centre - (centre - win.lo) * (span / (win.hi - win.lo))
  lo = Math.min(Math.max(lo, limits.lo), limits.hi - span)
  return { lo, hi: lo + span }
}

/** Formations present in the panel, in stratigraphic order (the FORMATION_RELATIVE axis). */
export function panelFormations(panel: CorrelationPanel): string[] {
  const byOrder = new Map<number, string>()
  for (const w of panel.wells)
    for (const f of w.tracks.formations) byOrder.set(f.strat_order, f.name)
  return [...byOrder.entries()].sort((a, b) => a[0] - b[0]).map(([, name]) => name)
}

/**
 * The well's own TVDSS at aligned position `v`, from its formation tops (linear inside a
 * formation, which is exact for TVDSS and flattening and is how the backend maps relative
 * positions). Null where the mapping is undefined (below TD on the relative axis).
 */
export function tvdssAt(well: CorrelationWell, align: Alignment, v: number): number | null {
  if (align === 'TVDSS' || well.fallback_to_tvdss) return v
  const fms = well.tracks.formations
  if (fms.length === 0) return null
  if (align === 'FLATTEN_ON_TOP') {
    const f = fms[0]!
    return v + (f.top_tvdss_m - f.top) // flattening is one shift for the whole well
  }
  for (const f of fms) {
    if (f.base === null || f.base_tvdss_m === null) continue
    if (v >= f.top && v <= f.base && f.base > f.top) {
      const frac = (v - f.top) / (f.base - f.top)
      return f.top_tvdss_m + frac * (f.base_tvdss_m - f.top_tvdss_m)
    }
  }
  return null
}

function metres(v: number, units: UnitSystem): string {
  return `${formatNumber(units === 'metric' ? v : v / FT_TO_M)} ${units === 'metric' ? 'm' : 'ft'}`
}

/** Axis value in words: "2,340 m TVDSS", "120 m below Tipam Sandstone top", "Barail · 40%". */
export function formatAligned(
  v: number,
  align: Alignment,
  top: string | null,
  formations: string[],
  units: UnitSystem,
): string {
  if (align === 'TVDSS') return `${metres(v, units)} TVDSS`
  if (align === 'FLATTEN_ON_TOP') {
    if (Math.abs(v) < 0.5) return `at ${top ?? 'the'} top`
    return `${metres(Math.abs(v), units)} ${v < 0 ? 'above' : 'below'} ${top ?? 'the'} top`
  }
  const k = Math.floor(v)
  const name = formations[Math.min(Math.max(k, 0), formations.length - 1)] ?? 'formation'
  return `${name} · ${Math.round((v - k) * 100)}%`
}

/** Shared mud-weight domain for the panel (SG), so MW curves compare across columns. */
export function mwDomain(panel: CorrelationPanel): [number, number] {
  const values = panel.wells.flatMap((w) =>
    w.tracks.mud.flatMap((m) => [m.mw_sg, m.ecd_sg]).filter((x): x is number => x !== null),
  )
  if (values.length === 0) return [1, 2]
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const pad = Math.max(0.05, (hi - lo) * 0.1)
  return [Math.max(0.8, lo - pad), hi + pad]
}
