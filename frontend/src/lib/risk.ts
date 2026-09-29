/**
 * Offset prior risk helpers (S7a, FRONTEND_PLAN §4.5/§4.6): the 5-step risk scale and the
 * step series a RiskCurve draws. Pure, so they are unit-tested.
 */
import type { components } from './api/schema'

export type RiskProfile = components['schemas']['RiskProfile']
export type RiskInterval = components['schemas']['RiskInterval']
export type EventRisk = components['schemas']['EventRisk']

/** Upper bounds of risk steps 0-3; step 4 is everything from 50 % up. */
export const RISK_STEPS = [0.05, 0.15, 0.3, 0.5] as const

export function riskStep(p: number): number {
  const i = RISK_STEPS.findIndex((b) => p < b)
  return i === -1 ? RISK_STEPS.length : i
}

export function riskColor(p: number): string {
  return `var(--risk-${riskStep(p)})`
}

/** The event types worth drawing: highest peak probability first, above `floor`. */
export function topTypes(profile: RiskProfile, n = 3, floor = 0.05): string[] {
  const peak = new Map<string, number>()
  for (const iv of profile.intervals)
    for (const r of iv.risks)
      peak.set(r.event_type, Math.max(peak.get(r.event_type) ?? 0, r.probability))
  return [...peak.entries()]
    .filter(([, p]) => p >= floor)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, n)
    .map(([t]) => t)
}

export interface CurveStep {
  formation: string
  top: number
  base: number
  p: number
  lo: number
  hi: number
  prognosed: boolean
  risk: EventRisk
}

/** Base of an interval on the TVDSS axis; the last interval gets `openBase` metres. */
export function intervalBase(iv: RiskInterval, openBase = 150): number {
  return iv.base_tvdss_m ?? iv.top_tvdss_m + openBase
}

/** One step per interval for one event type (intervals without the type are skipped). */
export function curveSteps(profile: RiskProfile, eventType: string): CurveStep[] {
  const out: CurveStep[] = []
  for (const iv of profile.intervals) {
    const r = iv.risks.find((x) => x.event_type === eventType)
    if (!r) continue
    out.push({
      formation: iv.formation,
      top: iv.top_tvdss_m,
      base: intervalBase(iv),
      p: r.probability,
      lo: r.ci90_low,
      hi: r.ci90_high,
      prognosed: iv.prognosed,
      risk: r,
    })
  }
  return out
}

/** The highest-risk event of an interval (for a hazard strip). */
export function peakRisk(iv: RiskInterval): EventRisk | null {
  return iv.risks.reduce<EventRisk | null>(
    (a, r) => (a && a.probability >= r.probability ? a : r),
    null,
  )
}

export function pct(p: number | null | undefined, digits = 0): string {
  return p === null || p === undefined ? '—' : `${(p * 100).toFixed(digits)}%`
}
