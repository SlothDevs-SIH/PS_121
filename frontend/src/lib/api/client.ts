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
export type CurrentUser = components['schemas']['CurrentUser']

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

export const api = {
  meta: () => apiFetch<Meta>('/api/v1/meta'),
  me: () => apiFetch<CurrentUser>('/api/v1/me'),
  readiness: fetchReadiness,
}
