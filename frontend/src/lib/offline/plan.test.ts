import { mockBackend } from '../../test/utils'
import {
  api,
  type CorrelationPanel,
  type EventTimeline,
  type OffsetsOut,
  type WellDetail,
} from '../api/client'
import { EVENT_TYPES } from '../eventTypes'
import { packKey } from './keys'
import {
  coreUrls,
  correlationSets,
  correlationUrls,
  evidencePages,
  knowledgeUrls,
  wellUrls,
} from './plan'

/** The URL the real API client requests for a call (what the service worker will see). */
async function urlOf(call: () => Promise<unknown>): Promise<string> {
  const fetchMock = mockBackend({})
  await call().catch(() => undefined)
  return String(fetchMock.mock.calls.at(-1)?.[0])
}

const ev = (document_id: number, page_no: number) => ({ document_id, page_no, span_ids: [] })

const WELL = {
  id: 3,
  name: 'SYN-ASM-03',
  formation_tops: [{ formation: 'Tipam' }, { formation: 'Barail' }, { formation: 'Tipam' }],
  event_counts: { LOSS: 2 },
  recent_events: [],
  lessons: [{ event_id: 11, evidence: [ev(9, 1)] }],
} as unknown as WellDetail

const OFFSETS = {
  well_id: 3,
  offsets: [
    { well_id: 7, status: 'completed', distance_m: 4200 },
    { well_id: 4, status: 'completed', distance_m: 1200 },
    { well_id: 8, status: 'planned', distance_m: 1500 },
    { well_id: 5, status: 'drilling', distance_m: 2800 },
    { well_id: 6, status: 'completed', distance_m: 9000 },
    { well_id: 9, status: 'completed', distance_m: 15000 },
  ],
} as unknown as OffsetsOut

const TIMELINE = {
  events: [
    { id: 11, evidence: [ev(9, 1), ev(9, 2)] },
    { id: 12, evidence: [ev(9, 1)] },
  ],
  counts_by_type: { LOSS: 1, STUCK: 1 },
} as unknown as EventTimeline

describe('well pack URL plan', () => {
  it('asks for exactly what the API client asks for (same key the service worker looks up)', async () => {
    const pairs: [string, () => Promise<unknown>][] = [
      [wellUrls.wells(), () => api.wells()],
      [wellUrls.well(3), () => api.well(3)],
      [wellUrls.timeline(3), () => api.timeline(3)],
      [wellUrls.riskProfile(3), () => api.riskProfile(3)],
      [wellUrls.trajectory(3), () => api.trajectory(3)],
      [wellUrls.offsets(3, 20), () => api.offsets(3, 20, 'SURFACE')],
      [
        wellUrls.offsets(3, 5, 'AT_FORMATION', 'Tipam'),
        () => api.offsets(3, 5, 'AT_FORMATION', { formation: 'Tipam' }),
      ],
      [wellUrls.offsets(3, 5, 'CLOSEST_APPROACH'), () => api.offsets(3, 5, 'CLOSEST_APPROACH')],
      [wellUrls.documents(3), () => api.documents({ well_id: 3 })],
      [wellUrls.formations(), () => api.formations()],
      [wellUrls.event(11), () => api.event(11)],
      [wellUrls.correlation([3, 4], 'TVDSS'), () => api.correlation([3, 4], 'TVDSS')],
      [
        wellUrls.correlation([3, 4], 'FLATTEN_ON_TOP', 'Tipam'),
        () => api.correlation([3, 4], 'FLATTEN_ON_TOP', 'Tipam'),
      ],
      [wellUrls.formationStats([3, 4]), () => api.formationStats([3, 4])],
      [wellUrls.ledger('LOSS'), () => api.ledger({ event_type: 'LOSS' })],
      [
        wellUrls.ledger('LOSS', 'Tipam'),
        () => api.ledger({ event_type: 'LOSS', formation: 'Tipam', severity: null }),
      ],
      [wellUrls.page(9, 2), () => api.page(9, 2)],
    ]
    for (const [planned, call] of pairs) expect(packKey(planned)).toBe(packKey(await urlOf(call)))
  })

  it('starts with the well, its surface offsets at 20 km and the lists every screen needs', () => {
    expect(coreUrls(3)).toEqual([
      '/api/v1/wells?limit=500',
      '/api/v1/wells/3',
      '/api/v1/wells/3/events/timeline',
      '/api/v1/wells/3/risk-profile',
      '/api/v1/wells/3/trajectory',
      '/api/v1/wells/3/offsets?radius_km=20&mode=SURFACE',
      '/api/v1/documents?well_id=3&limit=500',
      '/api/v1/formations',
    ])
  })

  it('picks the correlation wells the way Well 360 and the Correlation Panel do', () => {
    // Well 360: API order within 5 km, drilled only, 4 of them. Panel: nearest 5 within 10 km.
    expect(correlationSets(3, OFFSETS)).toEqual([
      [3, 7, 4, 5],
      [3, 4, 5, 7, 6],
    ])
    expect(correlationSets(3, null)).toEqual([[3]])
  })

  it('plans offsets per mode, panels, trajectories, event details and the ledger', () => {
    const urls = knowledgeUrls(3, { well: WELL, offsets: OFFSETS, timeline: TIMELINE })
    expect(urls).toContain(wellUrls.offsets(3, 5, 'AT_FORMATION', 'Tipam'))
    expect(urls).toContain(wellUrls.offsets(3, 5, 'AT_FORMATION', 'Barail'))
    expect(urls.filter((u) => u.includes('AT_FORMATION'))).toHaveLength(2)
    expect(urls).toContain(wellUrls.correlation([3, 7, 4, 5], 'TVDSS'))
    expect(urls).toContain(wellUrls.correlation([3, 4, 5, 7, 6], 'FORMATION_RELATIVE'))
    expect(urls).toContain(wellUrls.formationStats([3, 4, 5, 7, 6]))
    // Trajectory tab: drilled offsets within 3 km.
    expect(urls.filter((u) => u.endsWith('/trajectory')).sort()).toEqual([
      wellUrls.trajectory(4),
      wellUrls.trajectory(5),
    ])
    expect(urls).toContain(wellUrls.event(11))
    expect(urls).toContain(wellUrls.event(12))
    for (const t of Object.keys(EVENT_TYPES)) expect(urls).toContain(wellUrls.ledger(t))
    expect(urls).toContain(wellUrls.ledger('STUCK', 'Barail'))
    expect(urls).not.toContain(wellUrls.ledger('KICK', 'Barail'))
  })

  it('adds one flattened panel per top and the markers’ events it does not have yet', () => {
    const panel = {
      wells: [
        {
          tracks: {
            formations: [
              { name: 'Barail', strat_order: 2 },
              { name: 'Tipam', strat_order: 1 },
            ],
            events: [{ event_id: 11 }, { event_id: 40, evidence: [] }],
          },
        },
      ],
    } as unknown as CorrelationPanel
    const urls = correlationUrls([{ wells: [3, 4], panel }], new Set([wellUrls.event(11)]))
    expect(urls).toEqual([
      wellUrls.correlation([3, 4], 'FLATTEN_ON_TOP', 'Tipam'),
      wellUrls.correlation([3, 4], 'FLATTEN_ON_TOP', 'Barail'),
      wellUrls.event(40),
    ])
  })

  it('collects each cited report page once', () => {
    expect(evidencePages({ well: WELL, timeline: TIMELINE })).toEqual([
      { documentId: 9, pageNo: 1 },
      { documentId: 9, pageNo: 2 },
    ])
  })
})
