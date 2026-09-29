import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'

import { Providers } from '../app/providers'
import { makeQueryClient } from '../app/queryClient'
import { routes } from '../app/router'

type Route = { status: number; body: unknown } | 'network-error'

/**
 * Replace global fetch with a table of path → response. Keys may be "METHOD /path" or just
 * "/path" (any method); the query string is ignored unless the key includes one.
 */
export function mockBackend(table: Record<string, Route>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = (init?.method ?? 'GET').toUpperCase()
    const bare = url.split('?')[0]
    const key =
      Object.keys(table).find((k) => k === `${method} ${url}` || k === `${method} ${bare}`) ??
      Object.keys(table).find((k) => url === k || bare === k)
    const route = key
      ? table[key]
      : {
          status: 404,
          body: { error: { code: 'not_found', message: 'nf', details: {}, request_id: 'r' } },
        }
    if (route === 'network-error' || route === undefined) throw new TypeError('Failed to fetch')
    return new Response(JSON.stringify(route.body), {
      status: route.status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function renderApp(path: string) {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false, refetchInterval: false } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  return render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
  )
}

export const READY = {
  status: 200,
  body: {
    status: 'ready',
    components: [
      { name: 'postgres', ok: true, latency_ms: 3.1, detail: 'extensions ok' },
      { name: 'redis', ok: true, latency_ms: 1.0, detail: 'ping ok' },
      { name: 'object_storage', ok: true, latency_ms: 2.0, detail: 'buckets ok' },
    ],
  },
}

export const NOT_READY = {
  status: 503,
  body: {
    status: 'not_ready',
    components: [
      { name: 'postgres', ok: true, latency_ms: 3.1, detail: 'extensions ok' },
      { name: 'redis', ok: false, latency_ms: 2000, detail: 'ConnectionError' },
    ],
  },
}

export const META = {
  status: 200,
  body: {
    name: 'SMRITI backend',
    version: '0.1.0',
    git_sha: 'abc1234',
    env: 'dev',
    backend_phase: 'B0',
    components: [
      { key: 'platform', stage: '-', name: 'Skeleton', phase: 'B0', status: 'built' },
      {
        key: 'ingest',
        stage: 'S1',
        name: 'Document ingestion & OCR',
        phase: 'B1',
        status: 'planned',
      },
    ],
  },
}

export const ME = {
  status: 200,
  body: { user_id: 'dev', name: 'Local Developer', roles: ['admin'] },
}

export function notImplemented(phase: string) {
  return {
    status: 501,
    body: {
      error: {
        code: 'not_implemented',
        message: `planned for ${phase}`,
        details: { feature: 'x', phase },
        request_id: 'req-1',
      },
    },
  }
}

export const WELLS = {
  status: 200,
  body: {
    total: 4,
    items: [
      {
        id: 1,
        name: 'SYN-ASM-01',
        field: 'F',
        status: 'completed',
        well_type: 'development',
        fluid_type: 'oil',
        profile: 'J',
        lat: 27.4,
        lon: 95.25,
        td_md_m: 3500,
        spud_date: '2010-01-01',
        synthetic: true,
        document_count: 4,
      },
      {
        id: 2,
        name: 'SYN-ASM-P01',
        field: 'F',
        status: 'planned',
        well_type: 'development',
        fluid_type: null,
        profile: 'J',
        lat: 27.41,
        lon: 95.26,
        td_md_m: 3600,
        spud_date: '2027-01-15',
        synthetic: true,
        document_count: 0,
      },
      {
        id: 3,
        name: 'SYN-ASM-03',
        field: 'F',
        status: 'completed',
        well_type: 'development',
        fluid_type: 'gas',
        profile: 'vertical',
        lat: 27.43,
        lon: 95.27,
        td_md_m: 3900,
        spud_date: '2012-01-01',
        synthetic: true,
        document_count: 2,
      },
      {
        id: 4,
        name: 'SYN-ASM-41',
        field: 'F',
        status: 'drilling',
        well_type: 'development',
        fluid_type: 'oil',
        profile: 'J',
        lat: 27.42,
        lon: 95.24,
        td_md_m: 2200,
        spud_date: '2026-09-01',
        synthetic: true,
        document_count: 0,
      },
    ],
  },
}

export function wellDetail(id: number) {
  const w = WELLS.body.items.find((x) => x.id === id)!
  return {
    status: 200,
    body: {
      ...w,
      aliases: [],
      rkb_elev_m: 120,
      gl_elev_m: 111,
      datum_assumed: false,
      completion_date: null,
      rig_name: 'Rig',
      units_system: 'metric',
      trajectory_assumed: false,
      crs_epsg: 32646,
      formation_tops: [],
      data_quality: { score: 0.8, checks: [] },
      casing: [],
      mud: [],
      event_counts: { LOSS: 2 },
      recent_events: [],
      documents: {
        total: 1,
        by_doc_type: { DDR: 1 },
        by_ingest_status: {},
        by_extract_status: {},
        by_index_status: {},
      },
      lessons: [],
    },
  }
}

export const OFFSETS = {
  status: 200,
  body: {
    well_id: 2,
    mode: 'SURFACE',
    radius_km: 5,
    formation: null,
    offsets: [
      {
        well_id: 3,
        name: 'SYN-ASM-03',
        status: 'completed',
        well_type: 'development',
        lat: 27.43,
        lon: 95.27,
        td_md_m: 3900,
        synthetic: true,
        distance_m: 2400,
        bearing_deg: 30,
      },
      {
        well_id: 1,
        name: 'SYN-ASM-01',
        status: 'completed',
        well_type: 'development',
        lat: 27.4,
        lon: 95.25,
        td_md_m: 3500,
        synthetic: true,
        distance_m: 1400,
        bearing_deg: 225,
      },
    ],
  },
}

export const PAGE = {
  status: 200,
  body: {
    document_id: 7,
    page_no: 1,
    width_px: 1240,
    height_px: 1754,
    image_url: '/api/v1/documents/7/pages/1/image',
    ocr_used: true,
    ocr_mean_conf: 88.2,
    spans: [
      {
        id: 101,
        line_no: 0,
        text: 'DAILY DRILLING REPORT',
        bbox: [0.08, 0.05, 0.35, 0.07],
        conf: 96,
      },
      {
        id: 102,
        line_no: 1,
        text: 'Partial losses of 45 bbl/hr at 2,415 m in Tipam',
        bbox: [0.08, 0.2, 0.8, 0.22],
        conf: 91,
      },
    ],
  },
}

export const DOCUMENTS = {
  status: 200,
  body: {
    total: 2,
    status_counts: { processed: 1, needs_review: 1 },
    items: [
      {
        id: 7,
        filename: 'SYN-ASM-01_DDR.pdf',
        doc_type: 'DDR',
        well_id: 1,
        well_name: 'SYN-ASM-01',
        raw_well_name: 'SYN-ASM-01',
        report_date: '2010-02-01',
        page_count: 1,
        ingest_status: 'processed',
        extract_status: 'done',
        index_status: 'done',
        extract_error: null,
        event_count: 2,
        error: null,
        synthetic: true,
        size_bytes: 20480,
        created_at: '2026-09-28T10:00:00Z',
        processed_at: '2026-09-28T10:00:05Z',
      },
      {
        id: 8,
        filename: 'unknown_scan.pdf',
        doc_type: 'DDR',
        well_id: null,
        well_name: null,
        raw_well_name: 'SYN ASM 9x',
        report_date: null,
        page_count: 1,
        ingest_status: 'needs_review',
        extract_status: 'skipped',
        index_status: 'done',
        extract_error: 'well not identified; confirm the well name first',
        event_count: 0,
        error: "well not identified (read: 'SYN ASM 9x')",
        synthetic: true,
        size_bytes: 90000,
        created_at: '2026-09-28T10:01:00Z',
        processed_at: '2026-09-28T10:01:09Z',
      },
    ],
  },
}

export const EVENTS = {
  status: 200,
  body: {
    next_cursor: null,
    items: [
      {
        id: 11,
        well_id: 1,
        well_name: 'SYN-ASM-01',
        wellbore_id: 1,
        synthetic: true,
        event_type: 'LOSS',
        subtype: 'partial',
        severity: 'medium',
        event_date: '2010-02-01',
        t_start: null,
        t_end: null,
        md_m: 2415,
        tvd_m: 2400,
        tvdss_m: 2280,
        formation_id: 4,
        formation: 'Tipam Sandstone',
        hole_size_in: 12.25,
        mw_sg: 1.18,
        npt_hours: 3.5,
        resolved: true,
        source: 'rules',
        status: 'active',
        confidence: 0.95,
        verified: false,
        evidence: [{ document_id: 7, page_no: 1, span_ids: [102], filename: 'x', doc_type: 'DDR' }],
      },
      {
        id: 12,
        well_id: 3,
        well_name: 'SYN-ASM-03',
        wellbore_id: 3,
        synthetic: true,
        event_type: 'STUCK',
        subtype: 'differential',
        severity: 'high',
        event_date: '2012-05-01',
        t_start: null,
        t_end: null,
        md_m: 3100,
        tvd_m: 3000,
        tvdss_m: 2880,
        formation_id: 5,
        formation: 'Barail',
        hole_size_in: 8.5,
        mw_sg: 1.4,
        npt_hours: 12,
        resolved: true,
        source: 'rules',
        status: 'active',
        confidence: 0.9,
        verified: true,
        evidence: [],
      },
    ],
  },
}

export const REVIEW = {
  status: 200,
  body: {
    items: [],
    next_cursor: null,
    status_counts: { pending: 5, accepted: 1, corrected: 0, rejected: 0 },
  },
}

export const CONFIG = { status: 200, body: { mapTileUrl: '', mapTileAttribution: '' } }

/** Everything the shell and dashboard read, for tests that just need a working app. */
export function fullBackend(extra: Record<string, Route> = {}) {
  return mockBackend({
    '/readyz': READY,
    '/api/v1/meta': META,
    '/api/v1/me': ME,
    '/config.json': CONFIG,
    '/api/v1/wells': WELLS,
    '/api/v1/events': EVENTS,
    '/api/v1/review-queue': REVIEW,
    'GET /api/v1/documents': DOCUMENTS,
    ...extra,
  })
}
