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
  body: {
    user_id: 'dev',
    name: 'Local Developer',
    roles: ['admin'],
    permissions: [
      'act_alerts',
      'admin',
      'control_replay',
      'copilot',
      'ingest',
      'read_knowledge',
      'read_live',
      'read_risk',
      'review',
    ],
    auth_mode: 'dev',
  },
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
    distance_label: 'Surface distance between wellheads',
    excluded: [] as { well_id: number; name: string; reason: string }[],
    subject_entry_md_m: null,
    subject_entry_tvdss_m: null,
    tvdss_from_m: null,
    tvdss_to_m: null,
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

// ─── Part 3 (F2) fixtures ────────────────────────────────────────────────────────────────

const EV_REF = {
  document_id: 7,
  page_no: 1,
  span_ids: [102],
  filename: 'SYN-ASM-01_DDR.pdf',
  doc_type: 'DDR',
}

function corrWell(id: number, name: string, shift: number, extra: Record<string, unknown> = {}) {
  return {
    well_id: id,
    name,
    status: 'completed',
    fluid_type: 'oil',
    synthetic: true,
    fallback_to_tvdss: false,
    reason: null,
    td_aligned: 3400 + shift,
    tracks: {
      formations: [
        {
          name: 'Girujan Clay',
          strat_order: 3,
          lithology: 'mottled clay',
          top: 1200 + shift,
          base: 2150 + shift,
          top_tvdss_m: 1200 + shift,
          base_tvdss_m: 2150 + shift,
        },
        {
          name: 'Tipam Sandstone',
          strat_order: 4,
          lithology: 'sandstone',
          top: 2150 + shift,
          base: 2860 + shift,
          top_tvdss_m: 2150 + shift,
          base_tvdss_m: 2860 + shift,
        },
        {
          name: 'Barail',
          strat_order: 5,
          lithology: 'shale, coal',
          top: 2860 + shift,
          base: null,
          top_tvdss_m: 2860 + shift,
          base_tvdss_m: null,
        },
      ],
      casing_shoes: [
        {
          casing_id: id * 10,
          od_in: 9.625,
          hole_size_in: 12.25,
          shoe_md_m: 2360,
          shoe_tvdss_m: 2230 + shift,
          aligned: 2230 + shift,
          confidence: 0.95,
          verified: false,
          evidence: [EV_REF],
        },
      ],
      cement_tops: [],
      mud: [
        {
          mud_interval_id: id * 10,
          md_from_m: 800,
          md_to_m: 2360,
          tvdss_from_m: 680,
          tvdss_to_m: 2230,
          top: 680 + shift,
          base: 2230 + shift,
          mw_sg: 1.18,
          ecd_sg: null,
          mud_type: 'water-based',
          confidence: 0.95,
          verified: false,
          evidence: [EV_REF],
        },
      ],
      events: [
        {
          event_id: id * 100,
          event_type: 'LOSS',
          severity: 'high',
          md_m: 2415,
          tvdss_m: 2280 + shift,
          aligned: 2280 + shift,
          relative_position: 0.2,
          npt_hours: 3.5,
          confidence: 0.95,
          verified: false,
          evidence: [EV_REF],
        },
      ],
    },
    ...extra,
  }
}

export const CORRELATION = {
  status: 200,
  body: {
    align: 'TVDSS',
    top: null,
    depth_axis: { label: 'TVDSS (m)', unit: 'm', min: -120, max: 3500 },
    wells: [
      corrWell(2, 'SYN-ASM-P01', 0, { status: 'planned' }),
      corrWell(1, 'SYN-ASM-01', 40),
      corrWell(3, 'SYN-ASM-03', 80, { fallback_to_tvdss: true, reason: 'no Tipam Sandstone top' }),
    ],
  },
}

export const FORMATION_STATS = {
  status: 200,
  body: {
    wells: [2, 1, 3],
    rows: [
      {
        formation: 'Tipam Sandstone',
        strat_order: 4,
        wells_penetrating: 3,
        events_by_type: { LOSS: 2 },
        wells_with_event_by_type: { LOSS: 2 },
        median_mw_sg: 1.3,
        median_npt_hours: 3.5,
      },
      {
        formation: 'Barail',
        strat_order: 5,
        wells_penetrating: 3,
        events_by_type: {},
        wells_with_event_by_type: {},
        median_mw_sg: 1.4,
        median_npt_hours: null,
      },
    ],
  },
}

export function eventDetail(id: number, wellId = 1) {
  const summary = EVENTS.body.items[0]!
  return {
    status: 200,
    body: {
      ...summary,
      id,
      well_id: wellId,
      description: 'Partial losses of 45 bbl/hr at 2,415 m in Tipam',
      cause_text: null,
      params: {
        loss_rate_m3_h: 7.2,
        total_loss_m3: null,
        pit_gain_m3: null,
        sidpp_kpa: null,
        sicp_kpa: null,
        kill_mw_sg: null,
        overpull_kn: null,
        torque_knm: null,
        jarring_h: null,
        gas_pct: null,
        h2s_ppm: null,
        ecd_sg: null,
        time_to_cure_h: null,
      },
      mitigations: [
        {
          id: 501,
          seq: 1,
          action_code: 'LCM_PILL_FINE',
          action_text: 'Pumped fine LCM pill',
          outcome: 'fail',
          npt_hours_after: 1.5,
          recurrence: null,
          t_start: null,
          volume_lost_m3: null,
          confidence: 0.9,
          verified: false,
          evidence: [EV_REF],
        },
        {
          id: 502,
          seq: 2,
          action_code: 'LCM_PILL_COARSE',
          action_text: 'Pumped coarse LCM pill',
          outcome: 'success',
          npt_hours_after: 2,
          recurrence: null,
          t_start: null,
          volume_lost_m3: null,
          confidence: 0.9,
          verified: false,
          evidence: [EV_REF],
        },
      ],
      lesson_card: {
        problem: 'Losses',
        likely_cause: null,
        action_taken: 'LCM',
        outcome: 'Cured',
        lesson: 'Go coarse sooner in Tipam.',
        generated_by: 'template:v1',
      },
      created_at: '2026-09-28T10:00:00Z',
      updated_at: '2026-09-28T10:00:00Z',
      verified_at: null,
      verified_by: null,
      evidence: [EV_REF],
    },
  }
}

export const LESSON = {
  event_id: 11,
  well_id: 1,
  well_name: 'SYN-ASM-01',
  synthetic: true,
  event_type: 'LOSS',
  formation: 'Tipam Sandstone',
  md_m: 2415,
  tvdss_m: 2280,
  problem: 'Lost circulation (partial) at 2415 m MD in Tipam Sandstone.',
  likely_cause: 'Weak sand, as stated in the report',
  action_taken: '1. Pumped coarse LCM pill (success)',
  outcome: 'Resolved on attempt 1 of 1; 3.5 h NPT.',
  lesson:
    'Coarse LCM worked first time here; check the ledger across offsets before relying on it.',
  confidence: 0.95,
  verified: false,
  evidence: [EV_REF],
}

export const TIMELINE = {
  status: 200,
  body: {
    well_id: 1,
    well_name: 'SYN-ASM-01',
    synthetic: true,
    spud_date: '2010-01-01',
    completion_date: '2010-03-01',
    td_md_m: 3500,
    total_npt_hours: 15.5,
    counts_by_type: { LOSS: 1, STUCK: 1 },
    events: [
      EVENTS.body.items[0],
      { ...EVENTS.body.items[1], well_id: 1, well_name: 'SYN-ASM-01' },
    ],
    npt_operations: [
      {
        id: 9,
        document_id: 7,
        page_no: 1,
        report_date: '2010-02-01',
        t_from: '06:00',
        t_to: '09:30',
        hours: 3.5,
        activity_code: 'NPT-LOSS',
        npt_category: 'LOSS',
        description: 'Partial losses, pumped LCM',
        md_m: 2415,
        is_npt: true,
        event_id: 11,
        evidence: [EV_REF],
      },
    ],
  },
}

export const TRAJECTORY_1 = {
  status: 200,
  body: {
    well_id: 1,
    wellbore_id: 1,
    assumed: false,
    crs_epsg: 32646,
    stations: [0, 1000, 2000, 3500].map((md, i) => ({
      md_m: md,
      inc_deg: i === 0 ? 0 : 10 + i,
      azi_deg: 145,
      tvd_m: md * 0.98,
      tvdss_m: md * 0.98 - 120,
      north_m: -i * 60,
      east_m: i * 40,
      dls_deg_30m: i === 2 ? 1.5 : 0.4,
    })),
    path: [
      { lat: 27.4, lon: 95.25, tvdss_m: -120 },
      { lat: 27.398, lon: 95.252, tvdss_m: 3310 },
    ],
  },
}

export const SEARCH_RESULT = {
  status: 200,
  body: {
    query: 'lost circulation Tipam',
    took_ms: 28,
    embedding_provider: 'hash:v1',
    no_record_found: false,
    lessons: [LESSON],
    passages: [
      {
        chunk_id: 47,
        document_id: 7,
        filename: 'SYN-ASM-01_DDR.pdf',
        doc_type: 'DDR',
        well_id: 1,
        well_name: 'SYN-ASM-01',
        synthetic: true,
        page_from: 1,
        page_to: 1,
        span_ids: [102],
        snippet: 'Lost circulation (Severe) in Tipam Sandstone.',
        highlights: [
          [0, 4],
          [5, 16],
          [29, 34],
        ],
        score: 0.03,
        lexical_rank: 1,
        dense_rank: 2,
      },
    ],
  },
}

export const NO_RECORD = {
  status: 200,
  body: {
    query: 'unicorn',
    took_ms: 5,
    embedding_provider: 'hash:v1',
    no_record_found: true,
    lessons: [],
    passages: [],
  },
}

export function reviewItem(id: number, extra: Record<string, unknown> = {}) {
  return {
    id,
    kind: 'casing',
    target_id: 36,
    document_id: 7,
    filename: 'SYN-ASM-01_WCR_scan.pdf',
    doc_type: 'WCR',
    well_id: 1,
    well_name: 'SYN-ASM-01',
    page_no: 1,
    span_ids: [102],
    evidence: [EV_REF],
    field: null,
    reason: "casing size unreadable ('T')",
    confidence: 0.47,
    proposed: { od_in: null, returns: 'full', toc_md_m: 2383, shoe_md_m: 3900, hole_size_in: 8.5 },
    status: 'pending',
    decided_by: null,
    decided_at: null,
    correction: null,
    created_at: '2026-09-29T05:53:18Z',
    ...extra,
  }
}

// ─── Part 4 (F3) fixtures ────────────────────────────────────────────────────────────────

function eventRisk(t: string, p: number, lo: number, hi: number, hits: number, total = 8) {
  return {
    event_type: t,
    probability: p,
    ci90_low: lo,
    ci90_high: hi,
    n_eff: 6.2,
    offsets_with_event: hits,
    offsets_total: total,
    base_rate: 0.05,
    label: `${t}: ${Math.round(p * 100)}% (${hits} of ${total} offsets)`,
  }
}

export const RISK_PROFILE = {
  status: 200,
  body: {
    well_id: 1,
    name: 'SYN-ASM-01',
    status: 'drilling',
    synthetic: true,
    td_md_m: 2300,
    td_tvdss_m: 2100,
    mode: 'AT_FORMATION',
    radius_km: 10,
    sigma_km: 5,
    prior_strength: 2,
    method: 'Weighted Beta-Binomial per formation and event type.',
    intervals: [
      {
        formation: 'Girujan Clay',
        strat_order: 3,
        top_md_m: 1300,
        base_md_m: 2260,
        top_tvdss_m: 1200,
        base_tvdss_m: 2150,
        prognosed: false,
        prognosis_spread_m: null,
        offsets: [],
        risks: [eventRisk('TIGHT', 0.46, 0.3, 0.63, 4), eventRisk('LOSS', 0.04, 0, 0.13, 0)],
      },
      {
        formation: 'Tipam Sandstone',
        strat_order: 4,
        top_md_m: 2260,
        base_md_m: null,
        top_tvdss_m: 2150,
        base_tvdss_m: null,
        prognosed: true,
        prognosis_spread_m: 4.6,
        offsets: [],
        risks: [eventRisk('LOSS', 0.36, 0.21, 0.53, 3), eventRisk('TIGHT', 0.02, 0, 0.1, 0)],
      },
    ],
  },
}

function ledgerEntry(code: string, label: string, s: number, n: number, mean: number) {
  return {
    action_code: code,
    action_label: label,
    n,
    successes: s,
    partial: 0,
    failures: n - s,
    unknown: code === 'REDUCE_MW' ? 2 : 0,
    first_choice: 1,
    success_rate: s / n,
    posterior_mean: mean,
    ci90_low: Math.max(0, mean - 0.2),
    ci90_high: Math.min(1, mean + 0.15),
    median_npt_hours: 4.1,
    median_volume_lost_m3: null,
    by_severity: [
      { severity: 'high', n: n - 1, successes: s - 1 },
      { severity: 'low', n: 1, successes: 1 },
    ],
    summary: `${label}: worked ${s} of ${n}`,
    cases: [
      {
        event_id: 29,
        mitigation_id: 38 + n,
        well_id: 8,
        well_name: 'SYN-ASM-08',
        synthetic: true,
        event_date: '2010-04-08',
        formation: 'Tipam Sandstone',
        severity: 'high',
        seq: 1,
        outcome: 'success',
        recorded_outcome: 'success',
        recurred: false,
        npt_hours_after: 4.8,
        verified: false,
        evidence: [EV_REF],
      },
      {
        event_id: 30,
        mitigation_id: 90 + n,
        well_id: 9,
        well_name: 'SYN-ASM-09',
        synthetic: true,
        event_date: '2011-01-02',
        formation: 'Tipam Sandstone',
        severity: 'high',
        seq: 2,
        outcome: 'partial',
        recorded_outcome: 'success',
        recurred: true,
        npt_hours_after: null,
        verified: true,
        evidence: [],
      },
    ],
  }
}

export const LEDGER = {
  status: 200,
  body: {
    event_type: 'LOSS',
    formation: null,
    basin: null,
    well_id: null,
    radius_km: null,
    min_n: 3,
    outcome_rule: 'success = resolved with no recurrence',
    caveat: 'Observational records: associated, not proven to cause.',
    scope: { wells: 19, events: 23, mitigations: 35, unknown_outcomes: 2 },
    ranked: [
      ledgerEntry('LCM_PILL_COARSE', 'LCM pill (coarse)', 7, 8, 0.8),
      ledgerEntry('LCM_PILL_FINE', 'LCM pill (fine)', 7, 12, 0.57),
      ledgerEntry('REDUCE_MW', 'Reduce mud weight', 4, 10, 0.42),
    ],
    insufficient: [ledgerEntry('CEMENT_PLUG', 'Cement plug', 2, 2, 0.75)],
    synthetic: true,
  },
}
