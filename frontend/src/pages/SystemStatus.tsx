import { ExternalLink } from 'lucide-react'

import { SCREENS, CURRENT_FRONTEND_PHASE } from '../app/screens'
import { Badge, type Tone } from '../components/ui/Badge'
import { Card, CardTitle } from '../components/ui/Card'
import { useMe, useMeta, useReadiness } from '../lib/api/hooks'
import { buildInfo, useRuntimeConfig } from '../lib/config'

const statusTone: Record<string, Tone> = { built: 'ok', in_progress: 'info', planned: 'neutral' }

export function SystemStatus() {
  const readiness = useReadiness()
  const meta = useMeta()
  const me = useMe()
  const config = useRuntimeConfig()
  const build = buildInfo()
  const grafana = config.data?.grafanaUrl ?? ''

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
            <dt className="text-muted">Version</dt>
            <dd data-testid="frontend-version">{build.version ?? 'unversioned (dev build)'}</dd>
            <dt className="text-muted">Build</dt>
            <dd className="font-mono break-all" data-testid="frontend-commit">
              {build.commit}
            </dd>
            <dt className="text-muted">Built</dt>
            <dd data-testid="frontend-built-at">{build.builtAt ?? '—'}</dd>
            <dt className="text-muted">Screens built</dt>
            <dd>
              {SCREENS.filter((s) => s.status === 'built').length} of {SCREENS.length}
            </dd>
          </dl>
        </Card>
      </div>

      <Card data-testid="monitoring">
        <CardTitle>Monitoring</CardTitle>
        {config.isPending ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : grafana ? (
          <p className="text-sm">
            <a
              href={grafana}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-accent hover:underline"
              data-testid="grafana-link"
            >
              Open Grafana dashboards <ExternalLink size={14} aria-hidden />
              <span className="sr-only">(opens in a new tab)</span>
            </a>{' '}
            <span className="text-muted">for this deployment's metrics over time.</span>
          </p>
        ) : (
          <p className="text-sm text-muted" data-testid="grafana-none">
            No Grafana is configured for this deployment. Set <code>GRAFANA_URL</code> on the web
            container to link its dashboards here.
          </p>
        )}
      </Card>

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
