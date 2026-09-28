import { useQueries } from '@tanstack/react-query'

import type { ScreenSpec } from '../app/screens'
import { Badge } from '../components/ui/Badge'
import { Card, CardTitle } from '../components/ui/Card'
import { ApiError, apiFetch } from '../lib/api/client'

interface ProbeResult {
  status: number
  code: string
  phase: string | null
}

async function probe(path: string): Promise<ProbeResult> {
  try {
    await apiFetch<unknown>(path)
    return { status: 200, code: 'ok', phase: null }
  } catch (err) {
    if (err instanceof ApiError)
      return { status: err.status, code: err.code, phase: err.plannedPhase }
    throw err
  }
}

/**
 * Placeholder for a screen that isn't built yet. It states what the screen will do and
 * probes its backend endpoints live, so the frontend↔backend contract is visible from F0.
 */
export function PlannedScreen({ screen }: { screen: ScreenSpec }) {
  const gets = screen.endpoints.filter((e) => e.method === 'GET')
  const results = useQueries({
    queries: gets.map((e) => ({
      queryKey: ['probe', e.path],
      queryFn: () => probe(e.path),
      staleTime: 30_000,
      retry: false,
    })),
  })
  const resultByPath = new Map(gets.map((e, i) => [e.path, results[i]]))

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold text-text">{screen.title}</h1>
        <Badge tone="warn" data-testid="planned-phase">
          Planned · frontend phase {screen.phase}
        </Badge>
      </div>
      <p className="text-muted">{screen.purpose}</p>

      <Card>
        <CardTitle>Plan reference</CardTitle>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted">Master plan</dt>
          <dd>{screen.planNo > 0 ? `§10 screen ${screen.planNo}` : 'Supporting screen'}</dd>
          <dt className="text-muted">Audience</dt>
          <dd className="capitalize">{screen.audiences.join(', ')}</dd>
          <dt className="text-muted">PS requirements</dt>
          <dd>{screen.psRefs.length ? screen.psRefs.join(', ') : '—'}</dd>
        </dl>
      </Card>

      <Card>
        <CardTitle>Backend endpoints (live check)</CardTitle>
        {screen.endpoints.length === 0 ? (
          <p className="text-sm text-muted">
            No dedicated endpoint defined yet (see FRONTEND_PLAN §4).
          </p>
        ) : (
          <ul className="space-y-2 text-sm" data-testid="endpoint-probes">
            {screen.endpoints.map((e) => {
              const r = resultByPath.get(e.path)
              return (
                <li key={`${e.method} ${e.path}`} className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral" className="font-mono">
                    {e.method}
                  </Badge>
                  <code className="break-all text-text">{e.path}</code>
                  {e.method !== 'GET' ? (
                    <span className="text-muted">
                      not probed ({e.method === 'WS' ? 'WebSocket' : 'write'})
                    </span>
                  ) : r?.isPending ? (
                    <span className="text-muted">checking…</span>
                  ) : r?.isError ? (
                    <Badge tone="danger">error</Badge>
                  ) : r?.data?.phase ? (
                    <Badge tone="warn">
                      {r.data.status} · backend phase {r.data.phase}
                    </Badge>
                  ) : r?.data?.status === 0 ? (
                    <Badge tone="danger">backend unreachable</Badge>
                  ) : (
                    <Badge tone={r?.data?.status === 200 ? 'ok' : 'danger'}>
                      {r?.data?.status} {r?.data?.code}
                    </Badge>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </div>
  )
}
