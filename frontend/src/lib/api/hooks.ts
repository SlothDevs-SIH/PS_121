import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  api,
  type AlertOut,
  type AlertPage,
  type AlertQuery,
  type AlertVerdict,
  type Alignment,
  type DocumentSummary,
  type LedgerParams,
  type OffsetOptions,
  type ProximityMode,
  type ReplayAction,
  type ReviewDecision,
  type SearchParams,
} from './client'

export const queryKeys = {
  readiness: ['readiness'] as const,
  meta: ['meta'] as const,
  me: ['me'] as const,
  wells: ['wells'] as const,
  well: (id: number) => ['well', id] as const,
  trajectory: (id: number) => ['trajectory', id] as const,
  offsets: (id: number, r: number, mode: ProximityMode, opts: OffsetOptions = {}) =>
    ['offsets', id, r, mode, opts] as const,
  documents: (status?: string) => ['documents', status ?? 'all'] as const,
  document: (id: number) => ['document', id] as const,
  page: (id: number, pageNo: number) => ['page', id, pageNo] as const,
  events: (params: object) => ['events', params] as const,
  reviewCounts: ['review-counts'] as const,
  reviewQueue: (params: object) => ['review-queue', params] as const,
  event: (id: number) => ['event', id] as const,
  timeline: (id: number) => ['timeline', id] as const,
  formations: ['formations'] as const,
  wellDocuments: (id: number) => ['documents', 'well', id] as const,
  correlation: (wells: number[], align: Alignment, top: string | null) =>
    ['correlation', wells, align, top] as const,
  formationStats: (wells: number[]) => ['formation-stats', wells] as const,
  search: (params: SearchParams) => ['search', params] as const,
  ledger: (params: LedgerParams) => ['ledger', params] as const,
  riskProfile: (id: number) => ['risk-profile', id] as const,
  alerts: (q: AlertQuery) => ['alerts', q] as const,
  alert: (id: number) => ['alert', id] as const,
  dejavu: (id: number) => ['dejavu', id] as const,
  realtime: (wellId: number, params: object) => ['realtime', wellId, params] as const,
  replays: ['replays'] as const,
}

/** Polled so the header status pill reflects outages within ~15 s. */
export function useReadiness() {
  return useQuery({
    queryKey: queryKeys.readiness,
    queryFn: api.readiness,
    refetchInterval: 15_000,
    retry: false,
  })
}

export function useMeta() {
  return useQuery({ queryKey: queryKeys.meta, queryFn: api.meta, staleTime: 60_000 })
}

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: api.me, staleTime: 300_000 })
}

export function useWells() {
  return useQuery({ queryKey: queryKeys.wells, queryFn: () => api.wells(), staleTime: 60_000 })
}

export function useWell(id: number | null) {
  return useQuery({
    queryKey: queryKeys.well(id ?? 0),
    queryFn: () => api.well(id as number),
    enabled: id !== null,
  })
}

export function useTrajectory(id: number | null) {
  return useQuery({
    queryKey: queryKeys.trajectory(id ?? 0),
    queryFn: () => api.trajectory(id as number),
    enabled: id !== null,
    staleTime: 300_000,
  })
}

export function useOffsets(
  id: number | null,
  radiusKm: number,
  mode: ProximityMode,
  opts: OffsetOptions = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.offsets(id ?? 0, radiusKm, mode, opts),
    queryFn: () => api.offsets(id as number, radiusKm, mode, opts),
    enabled: id !== null && enabled,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useFormations() {
  return useQuery({ queryKey: queryKeys.formations, queryFn: api.formations, staleTime: 300_000 })
}

export function useEvent(id: number | null) {
  return useQuery({
    queryKey: queryKeys.event(id ?? 0),
    queryFn: () => api.event(id as number),
    enabled: id !== null,
  })
}

export function useTimeline(id: number | null) {
  return useQuery({
    queryKey: queryKeys.timeline(id ?? 0),
    queryFn: () => api.timeline(id as number),
    enabled: id !== null,
    staleTime: 60_000,
  })
}

export function useWellDocuments(id: number | null) {
  return useQuery({
    queryKey: queryKeys.wellDocuments(id ?? 0),
    queryFn: () => api.documents({ well_id: id as number }),
    enabled: id !== null,
    staleTime: 60_000,
  })
}

export function useCorrelation(wells: number[], align: Alignment, top: string | null) {
  return useQuery({
    queryKey: queryKeys.correlation(wells, align, top),
    queryFn: () => api.correlation(wells, align, top),
    enabled: wells.length > 0 && (align !== 'FLATTEN_ON_TOP' || Boolean(top)),
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useFormationStats(wells: number[]) {
  return useQuery({
    queryKey: queryKeys.formationStats(wells),
    queryFn: () => api.formationStats(wells),
    enabled: wells.length > 0,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useSearch(params: SearchParams | null) {
  return useQuery({
    queryKey: queryKeys.search(params ?? { q: '' }),
    queryFn: () => api.search(params as SearchParams),
    enabled: Boolean(params?.q.trim()),
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useReviewQueue(params: { status: string; kind?: string; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.reviewQueue(params),
    queryFn: () => api.reviewQueue({ limit: 100, ...params }),
  })
}

/** Accept / correct / reject a review item; refreshes everything the decision can change. */
export function useDecideReview() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: ReviewDecision }) =>
      api.decideReview(id, decision),
    onSuccess: () => {
      for (const key of ['review-queue', 'review-counts', 'events', 'event', 'well', 'timeline'])
        void client.invalidateQueries({ queryKey: [key] })
    },
  })
}

const RECENT_MS = 15 * 60_000

/** True while a document is still moving through ingest → extraction → indexing. Stages
 * left 'pending' long after upload (e.g. extraction switched off) don't keep us polling. */
export function inPipeline(d: DocumentSummary, now = Date.now()): boolean {
  if (d.ingest_status === 'queued' || d.ingest_status === 'processing') return true
  if (d.ingest_status === 'failed') return false
  if (d.extract_status === 'running' || d.index_status === 'running') return true
  const recent = now - Date.parse(d.created_at) < RECENT_MS
  return recent && (d.extract_status === 'pending' || d.index_status === 'pending')
}

/** Polls every 3 s while any document is still in the pipeline. */
export function useDocuments(status?: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.documents(status),
    queryFn: () => api.documents(status ? { status } : {}),
    enabled,
    refetchInterval: (q) => (q.state.data?.items.some((d) => inPipeline(d)) ? 3000 : false),
  })
}

export function useEvents(params: { well_id?: number; event_type?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.events(params),
    queryFn: () => api.events(params),
    staleTime: 60_000,
  })
}

/** Items per review status (one tiny page request; the counts cover the whole queue). */
export function useReviewCounts() {
  return useQuery({
    queryKey: queryKeys.reviewCounts,
    queryFn: () => api.reviewQueue({ status: 'pending', limit: 1 }),
    select: (page) => page.status_counts,
    staleTime: 30_000,
  })
}

export function useDocumentPage(id: number, pageNo: number) {
  return useQuery({ queryKey: queryKeys.page(id, pageNo), queryFn: () => api.page(id, pageNo) })
}

export function useDocument(id: number) {
  return useQuery({ queryKey: queryKeys.document(id), queryFn: () => api.document(id) })
}

export function useUpload() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.upload,
    onSuccess: () => client.invalidateQueries({ queryKey: ['documents'] }),
  })
}

export function useLedger(params: LedgerParams | null) {
  return useQuery({
    queryKey: queryKeys.ledger(params ?? { event_type: '' }),
    queryFn: () => api.ledger(params as LedgerParams),
    enabled: Boolean(params?.event_type),
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useRiskProfile(id: number | null) {
  return useQuery({
    queryKey: queryKeys.riskProfile(id ?? 0),
    queryFn: () => api.riskProfile(id as number),
    enabled: id !== null,
    staleTime: 300_000,
    retry: false,
  })
}

// ─── Part 5 (F4): alerts, real-time window, replay ───────────────────────────────────────

export function useAlerts(q: AlertQuery = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.alerts(q),
    queryFn: () => api.alerts(q),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  })
}

export function useAlert(id: number | null) {
  return useQuery({
    queryKey: queryKeys.alert(id ?? 0),
    queryFn: () => api.alert(id as number),
    enabled: id !== null,
    retry: false,
  })
}

export function useDejaVu(id: number | null) {
  return useQuery({
    queryKey: queryKeys.dejavu(id ?? 0),
    queryFn: () => api.dejavu(id as number),
    enabled: id !== null,
    staleTime: Infinity,
    retry: false,
  })
}

export function useRealtimeWindow(
  wellId: number | null,
  params: { minutes?: number; max_points?: number; end?: string } = {},
) {
  return useQuery({
    queryKey: queryKeys.realtime(wellId ?? 0, params),
    queryFn: () => api.realtime(wellId as number, params),
    enabled: wellId !== null,
    staleTime: params.end ? Infinity : 0,
    retry: false,
  })
}

export function useReplays(poll = false) {
  return useQuery({
    queryKey: queryKeys.replays,
    queryFn: api.replays,
    refetchInterval: poll ? 5000 : false,
  })
}

export function useReplayControl() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      wellId,
      action,
      speed,
    }: {
      wellId: number
      action: ReplayAction
      speed?: number
    }) => api.replay(wellId, action, speed),
    onSettled: () => client.invalidateQueries({ queryKey: queryKeys.replays }),
  })
}

export type AlertAction =
  | { kind: 'ack' }
  | { kind: 'dismiss'; reason: string }
  | { kind: 'feedback'; verdict: AlertVerdict; comment?: string }

function applyOptimistic(a: AlertOut, action: AlertAction, user: string): AlertOut {
  const now = new Date().toISOString()
  if (action.kind === 'ack') return { ...a, status: 'ack', acked_by: user, acked_at: now }
  if (action.kind === 'dismiss') return { ...a, status: 'dismissed', dismiss_reason: action.reason }
  return {
    ...a,
    feedback: [
      ...a.feedback,
      {
        id: -1,
        alert_id: a.id,
        verdict: action.verdict,
        comment: action.comment ?? null,
        user_id: user,
        created_at: now,
      },
    ],
  }
}

/** Acknowledge / dismiss / give feedback, applied at once to every cached copy of the alert
 * and rolled back if the backend refuses (e.g. 409: someone else acted first). */
export function useAlertAction(user = 'you') {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, action }: { id: number; action: AlertAction }) => {
      if (action.kind === 'ack') return api.ackAlert(id)
      if (action.kind === 'dismiss') return api.dismissAlert(id, action.reason)
      await api.alertFeedback(id, action.verdict, action.comment)
      return api.alert(id)
    },
    onMutate: async ({ id, action }) => {
      await client.cancelQueries({ queryKey: ['alerts'] })
      await client.cancelQueries({ queryKey: queryKeys.alert(id) })
      const pages = client.getQueriesData<AlertPage>({ queryKey: ['alerts'] })
      const one = client.getQueryData<AlertOut>(queryKeys.alert(id))
      for (const [key, page] of pages) {
        if (!page) continue
        client.setQueryData<AlertPage>(key, {
          ...page,
          items: page.items.map((a) => (a.id === id ? applyOptimistic(a, action, user) : a)),
        })
      }
      if (one) client.setQueryData(queryKeys.alert(id), applyOptimistic(one, action, user))
      return { pages, one }
    },
    onError: (_err, { id }, ctx) => {
      for (const [key, page] of ctx?.pages ?? []) client.setQueryData(key, page)
      if (ctx?.one) client.setQueryData(queryKeys.alert(id), ctx.one)
    },
    onSuccess: (alert) => {
      client.setQueryData(queryKeys.alert(alert.id), alert)
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}
