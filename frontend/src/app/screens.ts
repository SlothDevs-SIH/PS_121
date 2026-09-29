/**
 * Registry of every screen in master plan §10 (plus the Dashboard of FRONTEND_SPEC §4.2),
 * with its build status. Keep in sync with docs/FRONTEND_PLAN.md §5 — update both together.
 */
import {
  Activity,
  BarChart3,
  Bell,
  BookOpenText,
  Columns3,
  FileStack,
  Gauge,
  LayoutDashboard,
  Map as MapIcon,
  Scale,
  Settings2,
  Waypoints,
  type LucideIcon,
} from 'lucide-react'

/** F0–F6: frontend phases (FRONTEND_PLAN §9). P2: the Part 2 design-system revamp. */
export type FrontendPhase = 'F0' | 'F1' | 'P2' | 'F2' | 'F3' | 'F4' | 'F5' | 'F6'
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
  icon: LucideIcon
}

export const CURRENT_FRONTEND_PHASE: FrontendPhase = 'F4'

export const SCREENS: ScreenSpec[] = [
  {
    id: 'dashboard',
    planNo: 0,
    path: '/',
    navPath: '/',
    title: 'Dashboard',
    purpose:
      'Field at a glance: wells by fluid, wells drilling now, the document pipeline, extracted events, the review backlog and open live alerts.',
    audiences: ['office', 'field'],
    psRefs: [],
    phase: 'P2',
    status: 'built',
    endpoints: [
      { method: 'GET', path: '/api/v1/wells' },
      { method: 'GET', path: '/api/v1/events' },
    ],
    icon: LayoutDashboard,
  },
  {
    id: 'map',
    planNo: 1,
    path: '/map',
    navPath: '/map',
    title: 'Map Explorer',
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
    icon: MapIcon,
  },
  {
    id: 'well360',
    planNo: 2,
    path: '/wells/:wellId',
    navPath: '/wells/1',
    title: 'Well 360',
    purpose:
      'Everything known about one well: wellbore sketch, casing and cement, mud programme, events timeline, 3D trajectory with offsets, lessons, documents, and a data-quality score with its reasons.',
    audiences: ['office'],
    psRefs: ['O-iii'],
    phase: 'F2',
    status: 'built',
    endpoints: [
      { method: 'GET', path: '/api/v1/wells/1' },
      { method: 'GET', path: '/api/v1/wells/1/trajectory' },
    ],
    icon: Waypoints,
  },
  {
    id: 'correlation',
    planNo: 3,
    path: '/correlation',
    navPath: '/correlation',
    title: 'Correlation Panel',
    purpose:
      'Offset wells side by side on TVDSS, flattened on a formation top, or formation-relative, with formations, casing and cement, mud weight and events (each linked to its report page).',
    audiences: ['office', 'field'],
    psRefs: ['O-iv', 'G-iii'],
    phase: 'F2',
    status: 'built',
    endpoints: [{ method: 'GET', path: '/api/v1/correlation?wells=1&wells=2&align=TVDSS' }],
    icon: Columns3,
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
    status: 'built',
    endpoints: [
      { method: 'WS', path: '/ws/wells/1/live' },
      { method: 'GET', path: '/api/v1/wells/1/risk-profile' },
    ],
    icon: Activity,
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
    status: 'built',
    endpoints: [
      { method: 'GET', path: '/api/v1/alerts' },
      { method: 'WS', path: '/ws/alerts' },
    ],
    icon: Bell,
  },
  {
    id: 'search',
    planNo: 6,
    path: '/search',
    navPath: '/search',
    title: 'Knowledge Search',
    purpose:
      'Hybrid search over drilling history: lessons cards first, then report passages with page-level citations; says "no record found" plainly. Copilot side panel in F5.',
    audiences: ['office', 'field'],
    psRefs: ['O-iii', 'G-ii'],
    phase: 'F2',
    status: 'built',
    endpoints: [
      { method: 'GET', path: '/api/v1/search?q=lost%20circulation' },
      { method: 'GET', path: '/api/v1/events?event_type=LOSS' },
      { method: 'POST', path: '/api/v1/copilot/chat' },
    ],
    icon: BookOpenText,
  },
  {
    id: 'ledger',
    planNo: 7,
    path: '/ledger',
    navPath: '/ledger',
    title: 'Mitigation Ledger',
    purpose:
      'Mitigations ranked by recorded outcome (success rate with credible interval, NPT hours, n) per event type and formation, with every case and its report page. Observational, not causal.',
    audiences: ['office', 'field'],
    psRefs: ['O-iii', 'O-vi'],
    phase: 'F3',
    status: 'built',
    endpoints: [{ method: 'GET', path: '/api/v1/ledger?event_type=LOSS' }],
    icon: Scale,
  },
  {
    id: 'documents',
    planNo: 8,
    path: '/documents',
    navPath: '/documents',
    title: 'Documents Library',
    purpose:
      'Upload reports and follow each through text/OCR, extraction and indexing; open any page with its extracted lines; review low-confidence extractions against their page (accept, correct, reject).',
    audiences: ['office'],
    psRefs: ['O-i'],
    phase: 'F1',
    status: 'built',
    endpoints: [
      { method: 'POST', path: '/api/v1/documents' },
      { method: 'GET', path: '/api/v1/documents' },
      { method: 'GET', path: '/api/v1/review-queue' },
    ],
    icon: FileStack,
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
    endpoints: [
      { method: 'GET', path: '/api/v1/analytics/npt?group_by=formation' },
      { method: 'GET', path: '/api/v1/analytics/recurring' },
      { method: 'GET', path: '/api/v1/analytics/alerts' },
    ],
    icon: BarChart3,
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
    icon: Settings2,
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
    icon: Gauge,
  },
]

export function screensFor(mode: Audience): ScreenSpec[] {
  return SCREENS.filter((s) => s.audiences.includes(mode))
}
