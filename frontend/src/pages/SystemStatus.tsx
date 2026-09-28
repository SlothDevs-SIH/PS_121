import { SCREENS, CURRENT_FRONTEND_PHASE } from '../app/screens'
import { Badge, type Tone } from '../components/ui/Badge'
import { Card, CardTitle } from '../components/ui/Card'
import { useMe, useMeta, useReadiness } from '../lib/api/hooks'

const statusTone: Record<string, Tone> = { built: 'ok', in_progress: 'info', planned: 'neutral' }

export function SystemStatus() {
  const readiness = useReadiness()
  const meta = useMeta()
  const me = useMe()

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <h1 className="text-2xl font-semibold text-text">System Status</h1>

      <Card>
        <CardTitle>Backend readiness</CardTitle>
        {readiness.isPending && <p className="text-sm text-muted">Checking…</p>}
        {readiness.isError && (
          <p className="text-sm text-danger" role="alert">
            Backend unreachable. Start it with <code>docker compose up -d --wait</code>.
          </p>
        )}
        {readiness.data && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left text-sm" data-testid="readiness-table">
              <thead className="text-muted">
                <tr>
                  <th className="py-1 pr-4 font-medium">Component</th>
                  <th className="py-1 pr-4 font-medium">State</th>
                  <th className="py-1 pr-4 font-medium">Latency</th>
                  <th className="py-1 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {readiness.data.components.map((c) => (
                  <tr key={c.name} className="border-t border-border align-top">
                    <td className="py-1.5 pr-4 font-mono">{c.name}</td>
                    <td className="py-1.5 pr-4">
                      <Badge tone={c.ok ? 'ok' : 'danger'}>{c.ok ? 'ok' : 'down'}</Badge>
                    </td>
                    <td className="py-1.5 pr-4 tabular-nums">{c.latency_ms} ms</td>
                    <td className="py-1.5 break-words text-muted">{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardTitle>Backend</CardTitle>
          {meta.data ? (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">Version</dt>
              <dd>{meta.data.version}</dd>
              <dt className="text-muted">Build</dt>
              <dd className="font-mono">{meta.data.git_sha}</dd>
              <dt className="text-muted">Environment</dt>
              <dd>{meta.data.env}</dd>
              <dt className="text-muted">Phase</dt>
              <dd data-testid="backend-phase">{meta.data.backend_phase}</dd>
              <dt className="text-muted">Signed in as</dt>
              <dd>{me.data ? `${me.data.name} (${me.data.roles.join(', ')})` : '—'}</dd>
            </dl>
          ) : (
            <p className="text-sm text-muted">{meta.isError ? 'Unavailable' : 'Loading…'}</p>
          )}
        </Card>
        <Card>
          <CardTitle>Frontend</CardTitle>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted">Phase</dt>
            <dd>{CURRENT_FRONTEND_PHASE}</dd>
            <dt className="text-muted">Build</dt>
            <dd className="font-mono">{import.meta.env.VITE_GIT_SHA ?? 'dev'}</dd>
            <dt className="text-muted">Screens built</dt>
            <dd>
              {SCREENS.filter((s) => s.status === 'built').length} of {SCREENS.length}
            </dd>
          </dl>
        </Card>
      </div>

      <Card>
        <CardTitle>Backend components</CardTitle>
        {meta.data && (
          <ul className="grid gap-1 text-sm sm:grid-cols-2" data-testid="component-list">
            {meta.data.components.map((c) => (
              <li
                key={c.key}
                className="flex items-center justify-between gap-2 border-t border-border py-1"
              >
                <span>
                  {c.stage !== '-' && <span className="text-muted">{c.stage} </span>}
                  {c.name}
                </span>
                <Badge tone={statusTone[c.status] ?? 'neutral'}>
                  {c.status} · {c.phase}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
