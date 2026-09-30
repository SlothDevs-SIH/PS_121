/**
 * Pure helpers for the Live Well Monitor and the alert evidence charts (F4): channel
 * metadata, rig-state segments, score trends, the look-ahead to the next hazard, and SVG
 * paths. Kept apart from the components so they are unit-tested directly.
 */
import type { RealtimeWindow } from './api/client'
import type { LiveFrame } from './live'
import type { RiskInterval, RiskProfile } from './risk'

export interface ChannelMeta {
  label: string
  unit: string
  color: string
  digits: number
}

/** Stream channels in canonical units (backend `stream.mapping`). */
export const CHANNELS: Record<string, ChannelMeta> = {
  bit_depth_m: { label: 'Bit depth', unit: 'm', color: 'var(--text-muted)', digits: 1 },
  hole_depth_m: { label: 'Hole depth', unit: 'm', color: 'var(--text-muted)', digits: 1 },
  hookload_kn: { label: 'Hookload', unit: 'kN', color: 'var(--ev-stuck)', digits: 0 },
  wob_kn: { label: 'WOB', unit: 'kN', color: 'var(--ev-tight)', digits: 0 },
  rpm: { label: 'RPM', unit: 'rpm', color: 'var(--ev-instab)', digits: 0 },
  torque_knm: { label: 'Torque', unit: 'kN·m', color: 'var(--ev-torque)', digits: 1 },
  spp_kpa: { label: 'SPP', unit: 'kPa', color: 'var(--ev-overp)', digits: 0 },
  flow_in_lpm: { label: 'Flow in', unit: 'L/min', color: 'var(--info)', digits: 0 },
  flow_out_lpm: { label: 'Flow out', unit: 'L/min', color: 'var(--ev-loss)', digits: 0 },
  pit_volume_m3: { label: 'Pit volume', unit: 'm³', color: 'var(--ev-kick)', digits: 2 },
  rop_m_h: { label: 'ROP', unit: 'm/h', color: 'var(--ev-balling)', digits: 1 },
  gas_pct: { label: 'Gas', unit: '%', color: 'var(--ev-gas)', digits: 2 },
}

/** Déjà Vu matcher channels (backend `risk.dejavu.CHANNELS`), as prepared for matching. */
export const DEJAVU_CHANNELS: Record<string, { label: string; unit: string }> = {
  torque: { label: 'Torque (drilling)', unit: 'kN·m' },
  hookload: { label: 'Hookload (drilling)', unit: 'kN' },
  spp: { label: 'SPP (pumping)', unit: 'kPa' },
  rop: { label: 'ROP (drilling)', unit: 'm/h' },
  imbalance: { label: 'Flow out − in', unit: '% of flow in' },
  pit: { label: 'Pit change', unit: 'm³' },
  gas: { label: 'Gas', unit: '%' },
}

export function channelMeta(key: string): ChannelMeta {
  return CHANNELS[key] ?? { label: key, unit: '', color: 'var(--text-muted)', digits: 2 }
}

/** Rig states from the backend state machine, each with a colour and a text code. */
export const RIG_STATES: Record<string, { label: string; code: string; color: string }> = {
  DRILLING: { label: 'Drilling', code: 'DRL', color: 'var(--ok)' },
  REAMING: { label: 'Reaming', code: 'RM', color: 'var(--ev-instab)' },
  CIRCULATING: { label: 'Circulating', code: 'CIR', color: 'var(--info)' },
  IN_SLIPS: { label: 'In slips', code: 'SLP', color: 'var(--text-muted)' },
  TRIP_IN: { label: 'Tripping in', code: 'TIH', color: 'var(--ev-tight)' },
  TRIP_OUT: { label: 'Tripping out', code: 'POOH', color: 'var(--ev-torque)' },
  STATIONARY: { label: 'Stationary', code: 'STA', color: 'var(--border)' },
  STUCK: { label: 'Stuck', code: 'STK', color: 'var(--danger)' },
}

export function rigMeta(state: string | null | undefined) {
  return (
    (state && RIG_STATES[state]) || { label: state ?? 'Unknown', code: '?', color: 'var(--border)' }
  )
}

export interface Segment {
  state: string
  from: number
  to: number
}

/** Consecutive runs of the same rig state as [from, to] times (ms). The last run ends at
 * the last sample. */
export function rigSegments(times: number[], states: (string | null)[]): Segment[] {
  const out: Segment[] = []
  for (let i = 0; i < times.length; i++) {
    const s = states[i] ?? 'UNKNOWN'
    const t = times[i]!
    const last = out[out.length - 1]
    if (last && last.state === s) last.to = t
    else {
      if (last) last.to = t
      out.push({ state: s, from: t, to: t })
    }
  }
  return out
}

export type Trend = 'up' | 'down' | 'flat'

/** Direction of a score over the lookback (a change under `tolerance` is flat). */
export function trend(values: (number | null | undefined)[], tolerance = 0.02): Trend {
  const xs = values.filter((v): v is number => typeof v === 'number')
  if (xs.length < 2) return 'flat'
  const d = xs[xs.length - 1]! - xs[0]!
  return d > tolerance ? 'up' : d < -tolerance ? 'down' : 'flat'
}

export interface LookAhead {
  current: RiskInterval | null
  next: RiskInterval | null
  /** TVD metres from the bit to the next formation top (prognosed tops are estimates). */
  distanceM: number | null
  /** The next interval's highest risk, if any is at least `floor`. */
  hazard: { event_type: string; probability: number; label: string } | null
}

/** Where the bit is in the offset risk profile, and what is next below it. */
export function lookAhead(
  profile: RiskProfile | undefined,
  bitTvdss: number | null | undefined,
  floor = 0.1,
): LookAhead {
  const none: LookAhead = { current: null, next: null, distanceM: null, hazard: null }
  if (!profile || bitTvdss === null || bitTvdss === undefined) return none
  const ivs = profile.intervals
  const idx = ivs.findIndex(
    (iv) => bitTvdss >= iv.top_tvdss_m && (iv.base_tvdss_m === null || bitTvdss < iv.base_tvdss_m),
  )
  const current = idx >= 0 ? ivs[idx]! : null
  const next = ivs.find((iv) => iv.top_tvdss_m > bitTvdss) ?? null
  const top = next?.risks[0]
  return {
    current,
    next,
    distanceM: next ? next.top_tvdss_m - bitTvdss : null,
    hazard:
      top && top.probability >= floor
        ? { event_type: top.event_type, probability: top.probability, label: top.label }
        : null,
  }
}

/** An SVG polyline path; nulls break the line (a gap is never drawn as a value). */
export function linePath(
  xs: number[],
  ys: (number | null | undefined)[],
  x: (v: number) => number,
  y: (v: number) => number,
): string {
  let d = ''
  let pen = false
  for (let i = 0; i < xs.length; i++) {
    const v = ys[i]
    if (v === null || v === undefined || !Number.isFinite(v)) {
      pen = false
      continue
    }
    d += `${pen ? 'L' : 'M'}${x(xs[i]!).toFixed(1)} ${y(v).toFixed(1)}`
    pen = true
  }
  return d
}

/** Min and max of the finite values, padded so a flat line sits mid-strip. */
export function extent(values: (number | null | undefined)[], pad = 0.08): [number, number] {
  const xs = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (xs.length === 0) return [0, 1]
  let lo = Math.min(...xs)
  let hi = Math.max(...xs)
  if (hi - lo < 1e-9) {
    const w = Math.abs(hi) * 0.05 || 1
    lo -= w
    hi += w
  }
  const p = (hi - lo) * pad
  return [lo - p, hi + p]
}

export function formatValue(v: number | null | undefined, digits: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return v.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

/** "12 s ago", "3 min ago". */
export function ago(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return s < 60 ? `${s} s ago` : `${Math.round(s / 60)} min ago`
}

export interface Series {
  times: number[]
  values: Record<string, (number | null)[]>
  rig: (string | null)[]
}

/** The first-paint window from REST plus the frames pushed since, on one time axis. */
export function mergeSeries(
  win: RealtimeWindow | undefined,
  frames: LiveFrame[],
  channels: string[],
  windowMin: number,
): Series {
  const times: number[] = []
  const values: Record<string, (number | null)[]> = {}
  const rig: (string | null)[] = []
  for (const c of channels) values[c] = []
  if (win) {
    win.ts.forEach((t, i) => {
      times.push(Date.parse(t))
      rig.push(win.rig_state[i] ?? null)
      for (const c of channels) values[c]!.push(win.values[c]?.[i] ?? null)
    })
  }
  const lastRest = times.length ? times[times.length - 1]! : -Infinity
  for (const f of frames) {
    const t = Date.parse(f.ts)
    if (t <= lastRest) continue
    times.push(t)
    rig.push(f.rig_state)
    for (const c of channels) values[c]!.push(f.values[c] ?? null)
  }
  // Keep the last windowMin of data time.
  const end = times.length ? times[times.length - 1]! : 0
  const start = times.findIndex((t) => t >= end - windowMin * 60_000)
  if (start > 0) {
    times.splice(0, start)
    rig.splice(0, start)
    for (const c of channels) values[c]!.splice(0, start)
  }
  return { times, values, rig }
}

/** Plain words for a stream data-quality flag (Part 7, backend `stream.quality`). */
export const QUALITY_LABELS: Record<string, string> = {
  flatline: 'Frozen? No change for 10 min',
  unit_jump: 'Unit changed at source?',
  out_of_range: 'Impossible value',
  missing: 'Missing',
  unreadable: 'Unreadable',
  unmapped: 'Not mapped',
}
