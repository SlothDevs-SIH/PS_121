/**
 * Registry of every screen in master plan §10, with its build status.
 * Keep in sync with docs/FRONTEND_PLAN.md §5 — update both in the same PR.
 */

export type FrontendPhase = 'F0' | 'F1' | 'F2' | 'F3' | 'F4' | 'F5' | 'F6'
export type ScreenStatus = 'planned' | 'in_progress' | 'built'
export type Audience = 'office' | 'field'

export interface ProbeEndpoint {
  method: 'GET' | 'POST' | 'WS'
  /** Concrete example path; GET endpoints are probed live on the placeholder page. */
  path: string
}

export interface ScreenSpec {
  id: string
  /** Screen number in master plan §10 (0 = not in §10). */
  planNo: number
  path: string
  navPath: string
  title: string
  purpose: string
  audiences: Audience[]
  psRefs: string[]
  phase: FrontendPhase
  status: ScreenStatus
  endpoints: ProbeEndpoint[]
}

export const CURRENT_FRONTEND_PHASE: FrontendPhase = 'F1'

export const SCREENS: ScreenSpec[] = [
  {
    id: 'map',
    planNo: 1,
    path: '/map',
    navPath: '/map',
    title: 'Well Map',
    purpose:
      'Offset wells around the active well within a user-defined radius; surface, at-formation and closest-approach distance modes.',
    audiences: ['office', 'field'],
    psRefs: ['O-ii', 'G-i'],
    phase: 'F1',
    status: 'built',
    endpoints: [
      { method: 'GET', path: '/api/v1/wells' },
      { method: 'GET', path: '/api/v1/wells/1/offsets?radius_km=5&mode=SURFACE' },
    ],
  },
  {
    id: 'well360',
    planNo: 2,
    path: '/wells/:wellId',
    navPath: '/wells/1',
    title: 'Well 360',
    purpose:
      'Everything known about one well: casing, cement, mud program, events timeline, lessons, documents, data-quality score.',
    audiences: ['office'],
    psRefs: ['O-iii'],
    phase: 'F2',
    status: 'planned',
    endpoints: [
      { method: 'GET', path: '/api/v1/wells/1' },
      { method: 'GET', path: '/api/v1/wells/1/trajectory' },
    ],
  },
  {
    id: 'correlation',
    planNo: 3,
    path: '/correlation',
    navPath: '/correlation',
    title: 'Correlation Panel',
    purpose:
      'Offset wells aligned by TVDSS or formation tops, with events, casing shoes and mud weights on depth tracks.',
    audiences: ['office', 'field'],
    psRefs: ['O-iv', 'G-iii'],
    phase: 'F2',
    status: 'planned',
    endpoints: [{ method: 'GET', path: '/api/v1/correlation?wells=1&wells=2&align=TVDSS' }],
  },
  {
    id: 'live',
    planNo: 4,
    path: '/live',
    navPath: '/live',
    title: 'Live Well Monitor',
    purpose:
      'Bit position, formation now/next, look-ahead to the next offset hazard, channel strips, risk gauges, alert feed. Used at the rig (field view) and by RTMAC engineers in the office.',
    audiences: ['field', 'office'],
    psRefs: ['O-vi', 'O-vii'],
    phase: 'F4',
    status: 'planned',
    endpoints: [
      { method: 'WS', path: '/ws/wells/1/live' },
      { method: 'GET', path: '/api/v1/wells/1/risk-profile' },
    ],
  },
  {
    id: 'alerts',
    planNo: 5,
    path: '/alerts',
    navPath: '/alerts',
    title: 'Alerts',
    purpose:
      'Alert feed and alert detail: trigger, evidence tabs, Déjà Vu overlay, ranked mitigations, acknowledge/dismiss/feedback.',
    audiences: ['field', 'office'],
    psRefs: ['O-vi'],
    phase: 'F4',
    status: 'planned',
    endpoints: [
      { method: 'GET', path: '/api/v1/alerts' },
      { method: 'WS', path: '/ws/alerts' },
    ],
  },
  {
    id: 'search',
    planNo: 6,
    path: '/search',
    navPath: '/search',
    title: 'Knowledge Search',
    purpose:
      'Hybrid search over drilling history with lessons cards and page-level citations; copilot side panel (F5).',
    audiences: ['office', 'field'],
    psRefs: ['O-iii', 'G-ii'],
    phase: 'F2',
    status: 'planned',
    endpoints: [
      { method: 'GET', path: '/api/v1/search?q=lost%20circulation' },
      { method: 'GET', path: '/api/v1/events?event_type=LOSS' },
      { method: 'POST', path: '/api/v1/copilot/chat' },
    ],
  },
  {
    id: 'ledger',
    planNo: 7,
    path: '/ledger',
    navPath: '/ledger',
    title: 'Mitigation Ledger',
    purpose:
      'Mitigations ranked by recorded outcome (success rate with credible interval, NPT hours, n) per event type and formation.',
    audiences: ['office', 'field'],
    psRefs: ['O-iii', 'O-vi'],
    phase: 'F3',
    status: 'planned',
    endpoints: [{ method: 'GET', path: '/api/v1/ledger?event_type=LOSS' }],
  },
  {
    id: 'ingest',
    planNo: 8,
    path: '/ingest',
    navPath: '/ingest',
    title: 'Ingestion & Review',
    purpose:
      'Upload reports, follow ingestion jobs, review low-confidence extractions side by side with the page image.',
    audiences: ['office'],
    psRefs: ['O-i'],
    phase: 'F1',
    status: 'in_progress',
    endpoints: [
      { method: 'POST', path: '/api/v1/documents' },
      { method: 'GET', path: '/api/v1/documents' },
      { method: 'GET', path: '/api/v1/review-queue' },
    ],
  },
  {
    id: 'analytics',
    planNo: 9,
    path: '/analytics',
    navPath: '/analytics',
    title: 'Analytics',
    purpose:
      'NPT by event type, formation, field and year; recurring problems; alert precision and alerts per shift.',
    audiences: ['office'],
    psRefs: ['O-vii'],
    phase: 'F5',
    status: 'planned',
    endpoints: [],
  },
  {
    id: 'admin',
    planNo: 10,
    path: '/admin',
    navPath: '/admin',
    title: 'Admin',
    purpose: 'Users and roles, channel mappings, alert thresholds and budget, replay control.',
    audiences: ['office'],
    psRefs: [],
    phase: 'F6',
    status: 'planned',
    endpoints: [{ method: 'POST', path: '/api/v1/replay' }],
  },
  {
    id: 'system',
    planNo: 0,
    path: '/system',
    navPath: '/system',
    title: 'System Status',
    purpose:
      'Live readiness of every backend dependency and the build status of every backend component.',
    audiences: ['office', 'field'],
    psRefs: [],
    phase: 'F0',
    status: 'built',
    endpoints: [
      { method: 'GET', path: '/readyz' },
      { method: 'GET', path: '/api/v1/meta' },
    ],
  },
]

export function screensFor(mode: Audience): ScreenSpec[] {
  return SCREENS.filter((s) => s.audiences.includes(mode))
}
