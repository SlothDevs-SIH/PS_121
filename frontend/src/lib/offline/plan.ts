/**
 * What a well pack contains: the exact API reads the knowledge screens make for one well
 * (Map, Well 360 with its lessons, Correlation, Ledger), so the service worker can answer
 * them offline without the pages knowing. Planned in stages because later reads depend on
 * earlier answers (the offsets pick the correlation wells, the panels pick the tops).
 * The URL shapes mirror src/lib/api/client.ts; plan.test.ts pins them to it.
 */
import type {
  CorrelationPanel,
  EventDetail,
  EventTimeline,
  EvidenceRef,
  OffsetsOut,
  PageOut,
  WellDetail,
} from '../api/client'
import { panelFormations } from '../correlation'
import { EVENT_TYPES } from '../eventTypes'
import { PACK_RADIUS_KM } from './keys'

/** Proximity modes other than surface are packed at the map's default radius. */
const MODE_RADIUS_KM = 5
/** Well 360 "Correlate with nearest offsets": the well and its 4 nearest drilled offsets
 * within 5 km. Correlation Panel default: the well and its 5 nearest within 10 km. */
const CORRELATION_SETS = [
  { radiusKm: 5, count: 4, byDistance: false },
  { radiusKm: 10, count: 5, byDistance: true },
] as const
/** Well 360 trajectory tab: up to 6 drilled offsets within 3 km. */
const TRAJECTORY_OFFSETS = { radiusKm: 3, count: 6 }
const MAX_EVENT_DETAILS = 400
const MAX_EVIDENCE_PAGES = 250

export const wellUrls = {
  wells: () => '/api/v1/wells?limit=500',
  well: (id: number) => `/api/v1/wells/${id}`,
  timeline: (id: number) => `/api/v1/wells/${id}/events/timeline`,
  riskProfile: (id: number) => `/api/v1/wells/${id}/risk-profile`,
  trajectory: (id: number) => `/api/v1/wells/${id}/trajectory`,
  offsets: (id: number, radiusKm: number, mode = 'SURFACE', formation?: string) =>
    `/api/v1/wells/${id}/offsets?${new URLSearchParams({
      radius_km: String(radiusKm),
      mode,
      ...(formation ? { formation } : {}),
    })}`,
  documents: (id: number) => `/api/v1/documents?well_id=${id}&limit=500`,
  formations: () => '/api/v1/formations',
  event: (id: number) => `/api/v1/events/${id}`,
  correlation: (wells: number[], align: string, top?: string) => {
    const q = new URLSearchParams(wells.map((w) => ['wells', String(w)]))
    q.append('align', align)
    if (top) q.append('top', top)
    return `/api/v1/correlation?${q}`
  },
  formationStats: (wells: number[]) =>
    `/api/v1/correlation/formation-stats?${new URLSearchParams(wells.map((w) => ['wells', String(w)]))}`,
  ledger: (eventType: string, formation?: string) =>
    `/api/v1/ledger?${new URLSearchParams({ event_type: eventType, ...(formation ? { formation } : {}) })}`,
  page: (documentId: number, pageNo: number) => `/api/v1/documents/${documentId}/pages/${pageNo}`,
}

/** Stage 1: the well itself and everything that does not depend on another answer. */
export function coreUrls(wellId: number): string[] {
  return [
    wellUrls.wells(),
    wellUrls.well(wellId),
    wellUrls.timeline(wellId),
    wellUrls.riskProfile(wellId),
    wellUrls.trajectory(wellId),
    wellUrls.offsets(wellId, PACK_RADIUS_KM),
    wellUrls.documents(wellId),
    wellUrls.formations(),
  ]
}

function drilled(offsets: OffsetsOut | null | undefined, radiusKm: number) {
  return (offsets?.offsets ?? []).filter(
    (o) => o.status !== 'planned' && o.distance_m <= radiusKm * 1000,
  )
}

/** The well sets the screens open a correlation panel with, deduplicated. */
export function correlationSets(
  wellId: number,
  offsets: OffsetsOut | null | undefined,
): number[][] {
  const sets = CORRELATION_SETS.map(({ radiusKm, count, byDistance }) => {
    const rows = drilled(offsets, radiusKm)
    if (byDistance) rows.sort((a, b) => a.distance_m - b.distance_m)
    return [wellId, ...rows.slice(0, count).map((o) => o.well_id)]
  })
  const seen = new Set<string>()
  return sets.filter((s) => {
    const k = s.join(',')
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

export interface CoreAnswers {
  well: WellDetail
  offsets?: OffsetsOut | null
  timeline?: EventTimeline | null
}

/** Stage 2: offsets in every mode, correlation panels, event details, trajectories, ledger. */
export function knowledgeUrls(wellId: number, core: CoreAnswers): string[] {
  const { well, offsets, timeline } = core
  const urls: string[] = []
  const tops = [...new Set(well.formation_tops.map((t) => t.formation))]
  for (const fm of tops) urls.push(wellUrls.offsets(wellId, MODE_RADIUS_KM, 'AT_FORMATION', fm))
  urls.push(wellUrls.offsets(wellId, MODE_RADIUS_KM, 'CLOSEST_APPROACH'))

  for (const set of correlationSets(wellId, offsets)) {
    urls.push(wellUrls.correlation(set, 'TVDSS'))
    urls.push(wellUrls.correlation(set, 'FORMATION_RELATIVE'))
    urls.push(wellUrls.formationStats(set))
  }

  for (const o of drilled(offsets, TRAJECTORY_OFFSETS.radiusKm).slice(0, TRAJECTORY_OFFSETS.count))
    urls.push(wellUrls.trajectory(o.well_id))

  const events = timeline?.events ?? well.recent_events
  for (const e of events.slice(0, MAX_EVENT_DETAILS)) urls.push(wellUrls.event(e.id))

  // The ledger opens on one event type with no filter; filtered by formation, the types
  // this well has actually met are the ones worth carrying.
  for (const type of Object.keys(EVENT_TYPES)) urls.push(wellUrls.ledger(type))
  const met = Object.keys(timeline?.counts_by_type ?? well.event_counts)
  for (const type of met) for (const fm of tops) urls.push(wellUrls.ledger(type, fm))
  return urls
}

/** Stage 3: flattened panels (one per top the TVDSS panel shows) and the markers' events. */
export function correlationUrls(
  panels: { wells: number[]; panel: CorrelationPanel }[],
  known: ReadonlySet<string>,
): string[] {
  const urls: string[] = []
  for (const { wells, panel } of panels)
    for (const top of panelFormations(panel))
      urls.push(wellUrls.correlation(wells, 'FLATTEN_ON_TOP', top))
  let budget = MAX_EVENT_DETAILS - [...known].filter((u) => u.startsWith('/api/v1/events/')).length
  for (const { panel } of panels)
    for (const w of panel.wells)
      for (const m of w.tracks.events) {
        const u = wellUrls.event(m.event_id)
        if (budget > 0 && !known.has(u) && !urls.includes(u)) {
          urls.push(u)
          budget -= 1
        }
      }
  return urls
}

/** Every report page cited by the packed lessons, events and markers, deduplicated. */
export function evidencePages(answers: {
  well?: WellDetail | null
  timeline?: EventTimeline | null
  events?: EventDetail[]
  panels?: CorrelationPanel[]
}): { documentId: number; pageNo: number }[] {
  const refs: EvidenceRef[] = []
  for (const l of answers.well?.lessons ?? []) refs.push(...l.evidence)
  for (const e of answers.timeline?.events ?? []) refs.push(...e.evidence)
  for (const e of answers.events ?? []) refs.push(...e.evidence)
  for (const p of answers.panels ?? [])
    for (const w of p.wells) for (const m of w.tracks.events) refs.push(...m.evidence)
  const seen = new Set<string>()
  const out: { documentId: number; pageNo: number }[] = []
  for (const r of refs) {
    const k = `${r.document_id}:${r.page_no}`
    if (seen.has(k)) continue
    seen.add(k)
    out.push({ documentId: r.document_id, pageNo: r.page_no })
  }
  return out.slice(0, MAX_EVIDENCE_PAGES)
}

/** Stage 4: the page images the packed evidence pages point at. */
export function imageUrls(pages: PageOut[]): string[] {
  return [...new Set(pages.map((p) => p.image_url))]
}
