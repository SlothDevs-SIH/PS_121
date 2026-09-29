/**
 * Minimal typed HTTP client for the SMRITI backend.
 *
 * All URLs are same-origin and relative (/api/v1/..., /readyz): the Vite dev server and the
 * nginx image both proxy them to the API, so there is no CORS and no hard-coded host.
 * Every non-2xx response from the backend uses one envelope (docs/BACKEND_PLAN.md §3.1):
 *   {"error": {"code", "message", "details", "request_id"}}
 * which is turned into an ApiError here.
 */
import type { components } from './schema'

export type ErrorBody = components['schemas']['ErrorBody']
export type ReadinessReport = components['schemas']['ReadinessReport']
export type Meta = components['schemas']['Meta']
export type CurrentUser = components['schemas']['Me']
export type WellSummary = components['schemas']['WellSummary']
export type WellList = components['schemas']['WellList']
export type WellDetail = components['schemas']['WellDetail']
export type TrajectoryOut = components['schemas']['TrajectoryOut']
export type OffsetsOut = components['schemas']['OffsetsOut']
export type OffsetOut = components['schemas']['OffsetOut']
export type FormationOut = components['schemas']['FormationOut']
export type DocumentSummary = components['schemas']['DocumentSummary']
export type DocumentList = components['schemas']['DocumentList']
export type DocumentDetail = components['schemas']['DocumentDetail']
export type PageOut = components['schemas']['PageOut']
export type SpanOut = components['schemas']['SpanOut']
export type UploadResult = components['schemas']['UploadResult']
export type EventSummary = components['schemas']['EventSummary']
export type EventPage = components['schemas']['EventPage']
export type ReviewPage = components['schemas']['ReviewPage']
export type ReviewItem = components['schemas']['ReviewItem']
export type EventDetail = components['schemas']['EventDetail']
export type EventTimeline = components['schemas']['EventTimeline']
export type EvidenceRef = components['schemas']['EvidenceRef']
export type LessonCard = components['schemas']['LessonCard']
export type CorrelationPanel = components['schemas']['CorrelationPanel']
export type CorrelationWell = components['schemas']['CorrelationWell']
export type EventMarker = components['schemas']['EventMarker']
export type FormationStats = components['schemas']['FormationStats']
export type SearchResponse = components['schemas']['SearchResponse']
export type Passage = components['schemas']['Passage']
export type Alignment = components['schemas']['Alignment']
export type LedgerResponse = components['schemas']['LedgerResponse']
export type LedgerEntry = components['schemas']['LedgerEntry']
export type LedgerCase = components['schemas']['LedgerCase']
export type RiskProfile = components['schemas']['RiskProfile']
export type EventType = EventSummary['event_type']
export type ProximityMode = 'SURFACE' | 'AT_FORMATION' | 'CLOSEST_APPROACH'

/** Extra offset parameters for the subsurface proximity modes (B2). */
export interface OffsetOptions {
  formation?: string | null
  tvdssFrom?: number | null
  tvdssTo?: number | null
}

export interface SearchParams {
  q: string
  well_id?: number | null
  radius_km?: number | null
  formation?: string | null
  event_type?: string[]
  doc_type?: string | null
  date_from?: string | null
  date_to?: string | null
  limit?: number
}

export interface LedgerParams {
  event_type: string
  formation?: string | null
  severity?: string | null
  well_id?: number | null
  radius_km?: number | null
}

export type ReviewDecision =
  | { action: 'accept'; note?: string }
  | { action: 'correct'; fields: Record<string, unknown>; note?: string }
  | { action: 'reject'; reason: string }

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  readonly requestId: string | null

  constructor(status: number, body: Partial<ErrorBody> | null, fallbackMessage: string) {
    super(body?.message ?? fallbackMessage)
    this.name = 'ApiError'
    this.status = status
    this.code = body?.code ?? (status === 0 ? 'network_error' : 'http_error')
    this.details = (body?.details as Record<string, unknown> | undefined) ?? {}
    this.requestId = body?.request_id ?? null
  }

  /** Backend phase that will implement this route, for 501 skeleton responses. */
  get plannedPhase(): string | null {
    const phase = this.details['phase']
    return this.code === 'not_implemented' && typeof phase === 'string' ? phase : null
  }
}

function isErrorEnvelope(value: unknown): value is { error: ErrorBody } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error: unknown }).error === 'object'
  )
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch (cause) {
    throw new ApiError(0, null, `Backend unreachable: ${String(cause)}`)
  }

  const text = await response.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      isErrorEnvelope(data) ? data.error : null,
      `HTTP ${response.status} ${response.statusText}`.trim(),
    )
  }
  return data as T
}

/** /readyz answers 503 with a full report when a dependency is down; return it either way. */
export async function fetchReadiness(): Promise<ReadinessReport> {
  let response: Response
  try {
    response = await fetch('/readyz', { headers: { Accept: 'application/json' } })
  } catch (cause) {
    throw new ApiError(0, null, `Backend unreachable: ${String(cause)}`)
  }
  if (response.status === 200 || response.status === 503) {
    return (await response.json()) as ReadinessReport
  }
  throw new ApiError(response.status, null, `Unexpected /readyz status ${response.status}`)
}

type QueryValue = string | number | undefined | null
function qs(params: Record<string, QueryValue | QueryValue[]>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    for (const item of Array.isArray(v) ? v : [v])
      if (item !== undefined && item !== null && item !== '') q.append(k, String(item))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  meta: () => apiFetch<Meta>('/api/v1/meta'),
  me: () => apiFetch<CurrentUser>('/api/v1/me'),
  readiness: fetchReadiness,
  wells: (params: { q?: string; status?: string } = {}) =>
    apiFetch<WellList>(`/api/v1/wells${qs({ ...params, limit: 500 })}`),
  well: (id: number) => apiFetch<WellDetail>(`/api/v1/wells/${id}`),
  trajectory: (id: number) => apiFetch<TrajectoryOut>(`/api/v1/wells/${id}/trajectory`),
  offsets: (id: number, radiusKm: number, mode: ProximityMode, opts: OffsetOptions = {}) =>
    apiFetch<OffsetsOut>(
      `/api/v1/wells/${id}/offsets${qs({
        radius_km: radiusKm,
        mode,
        formation: mode === 'AT_FORMATION' ? opts.formation : undefined,
        tvdss_from_m: mode === 'CLOSEST_APPROACH' ? opts.tvdssFrom : undefined,
        tvdss_to_m: mode === 'CLOSEST_APPROACH' ? opts.tvdssTo : undefined,
      })}`,
    ),
  formations: () => apiFetch<FormationOut[]>('/api/v1/formations'),
  documents: (params: { status?: string; well_id?: number } = {}) =>
    apiFetch<DocumentList>(`/api/v1/documents${qs({ ...params, limit: 500 })}`),
  document: (id: number) => apiFetch<DocumentDetail>(`/api/v1/documents/${id}`),
  page: (id: number, pageNo: number) =>
    apiFetch<PageOut>(`/api/v1/documents/${id}/pages/${pageNo}`),
  events: (params: { well_id?: number; event_type?: string; limit?: number } = {}) =>
    apiFetch<EventPage>(`/api/v1/events${qs({ limit: 500, ...params })}`),
  event: (id: number) => apiFetch<EventDetail>(`/api/v1/events/${id}`),
  timeline: (wellId: number) => apiFetch<EventTimeline>(`/api/v1/wells/${wellId}/events/timeline`),
  reviewQueue: (params: { status?: string; kind?: string; limit?: number; cursor?: string } = {}) =>
    apiFetch<ReviewPage>(`/api/v1/review-queue${qs({ limit: 1, ...params })}`),
  decideReview: (id: number, decision: ReviewDecision) =>
    apiFetch<ReviewItem>(`/api/v1/review-queue/${id}`, json(decision)),
  correlation: (wells: number[], align: Alignment, top?: string | null) =>
    apiFetch<CorrelationPanel>(
      `/api/v1/correlation${qs({ wells, align, top: align === 'FLATTEN_ON_TOP' ? top : undefined })}`,
    ),
  formationStats: (wells: number[]) =>
    apiFetch<FormationStats>(`/api/v1/correlation/formation-stats${qs({ wells })}`),
  search: ({ event_type, ...rest }: SearchParams) =>
    apiFetch<SearchResponse>(`/api/v1/search${qs({ ...rest, event_type })}`),
  ledger: (params: LedgerParams) => apiFetch<LedgerResponse>(`/api/v1/ledger${qs({ ...params })}`),
  riskProfile: (wellId: number) => apiFetch<RiskProfile>(`/api/v1/wells/${wellId}/risk-profile`),
  pageImageUrl: (id: number, pageNo: number) => `/api/v1/documents/${id}/pages/${pageNo}/image`,
  upload: (files: File[]) => {
    const body = new FormData()
    for (const f of files) body.append('files', f, f.name)
    return apiFetch<UploadResult[]>('/api/v1/documents', { method: 'POST', body })
  },
}
