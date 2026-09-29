import { Bell, Check, HelpCircle, MessageSquare, ShieldAlert, X } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'

import { EvidenceLink } from '../components/evidence/EvidenceLink'
import { ChannelStrip } from '../components/live/ChannelStrip'
import { DejaVuChart } from '../components/live/DejaVuChart'
import { DriversBar } from '../components/live/DriversBar'
import { IntervalBar } from '../components/risk/IntervalBar'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardTitle } from '../components/ui/Card'
import { SkeletonBlock } from '../components/ui/Skeleton'
import { TabPanel, Tabs } from '../components/ui/Tabs'
import {
  api,
  type AlertEvidence,
  type AlertOut,
  type AlertStatus,
  type AlertVerdict,
  type CopilotAnswer,
} from '../lib/api/client'
import {
  useAlert,
  useAlertAction,
  useAlerts,
  useDejaVu,
  useMe,
  useRealtimeWindow,
} from '../lib/api/hooks'
import { eventMeta } from '../lib/eventTypes'
import { scoreText, sortAlerts } from '../lib/alerts'
import { formatValue } from '../lib/liveView'
import { pct } from '../lib/risk'

const SEVERITY_TONE = { critical: 'danger', warning: 'warn', info: 'info' } as const
const STATUS_FILTERS: { id: string; label: string; status?: AlertStatus[] }[] = [
  { id: 'open', label: 'Open', status: ['new', 'ack'] },
  { id: 'new', label: 'New', status: ['new'] },
  { id: 'dismissed', label: 'Dismissed', status: ['dismissed'] },
  { id: 'all', label: 'All' },
]
const VERDICTS: { id: AlertVerdict; label: string }[] = [
  { id: 'useful', label: 'Useful' },
  { id: 'not_useful', label: 'Not useful' },
  { id: 'false_alarm', label: 'False alarm' },
]

function AlertRow({ a, selected }: { a: AlertOut; selected: boolean }) {
  const [params] = useSearchParams()
  const next = new URLSearchParams(params)
  next.set('id', String(a.id))
  return (
    <li>
      <Link
        to={`/alerts?${next.toString()}`}
        aria-current={selected ? 'true' : undefined}
        data-testid="alert-row"
        data-id={a.id}
        className={`block rounded-lg border px-3 py-2 ${selected ? 'border-accent bg-surface-2' : 'border-border hover:bg-surface-2'}`}
      >
        <div className="flex items-center gap-2">
          <Badge tone={SEVERITY_TONE[a.severity]}>{a.severity}</Badge>
          {a.budget_exempt && (
            <Badge
              tone="danger"
              title="Well control: always shown, never counted against the alert budget"
            >
              <ShieldAlert size={12} aria-hidden /> pinned
            </Badge>
          )}
          <span className="ml-auto text-xs text-muted">{a.status}</span>
        </div>
        <div className="mt-1 truncate text-sm font-medium text-text">{a.title}</div>
        <div className="text-xs text-muted">
          {a.well_name} · {eventMeta(a.event_type).label} ·{' '}
          {a.alert_type.replace('_', ' ').toLowerCase()} ·{' '}
          {new Date(a.t_data).toISOString().slice(0, 16).replace('T', ' ')}
        </div>
      </Link>
    </li>
  )
}

function StreamEvidence({ alert, ev }: { alert: AlertOut; ev: AlertEvidence }) {
  const win = useRealtimeWindow(alert.well_id, { minutes: 30, max_points: 360, end: alert.t_data })
  if (win.isLoading) return <SkeletonBlock className="h-40 w-full" />
  if (!win.data || win.data.ts.length === 0)
    return (
      <p className="text-sm text-muted">The stream samples for this alert are no longer stored.</p>
    )
  const times = win.data.ts.map((t) => Date.parse(t))
  const domain: [number, number] = [times[0]!, times[times.length - 1]!]
  const channels = ev.channels.length ? ev.channels : ['torque_knm']
  return (
    <div className="space-y-2" data-testid="stream-evidence">
      <p className="text-xs text-muted">
        The 30 min of this well’s stream up to the alert (red line).
      </p>
      {channels.map((c) => (
        <ChannelStrip
          key={c}
          channel={c}
          times={times}
          values={win.data.values[c] ?? []}
          domain={domain}
          markers={[{ t: Date.parse(alert.t_data), label: 'alert raised' }]}
        />
      ))}
    </div>
  )
}

function PastEvent({ ev }: { ev: AlertEvidence }) {
  return (
    <li
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border px-3 py-2 text-sm"
      data-testid="past-event"
    >
      <Badge tone="neutral">{ev.kind === 'matched_event' ? 'Déjà Vu match' : 'offset'}</Badge>
      {ev.well_id ? (
        <Link
          to={`/wells/${ev.well_id}?tab=events`}
          className="font-medium text-accent hover:underline"
        >
          {ev.well_name ?? `well ${ev.well_id}`}
        </Link>
      ) : null}
      <span className="text-muted">
        {ev.event_type ? eventMeta(ev.event_type).label : 'event'} · {ev.formation ?? 'formation —'}{' '}
        ·{' '}
        {ev.md_m !== null && ev.md_m !== undefined ? `${formatValue(ev.md_m, 0)} m MD` : 'depth —'}
      </span>
      <span className="ml-auto flex flex-wrap gap-2">
        {ev.refs.length === 0 ? (
          <span className="text-xs text-muted">no report page</span>
        ) : (
          ev.refs.slice(0, 3).map((r) => (
            <EvidenceLink
              key={`${r.document_id}-${r.page_no}`}
              documentId={r.document_id}
              pageNo={r.page_no}
              spanIds={r.span_ids}
              title={r.filename ?? undefined}
            >
              {r.doc_type ?? 'doc'} p.{r.page_no}
            </EvidenceLink>
          ))
        )}
      </span>
    </li>
  )
}

function DejaVuTab({ id }: { id: number }) {
  const q = useDejaVu(id)
  if (q.isLoading) return <SkeletonBlock className="h-48 w-full" />
  if (q.isError || !q.data)
    return <p className="text-sm text-muted">No Déjà Vu match recorded for this alert.</p>
  return <DejaVuChart overlay={q.data} />
}

function WhyFired({ alert }: { alert: AlertOut }) {
  const [answer, setAnswer] = useState<CopilotAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ask = async () => {
    setBusy(true)
    setError(null)
    try {
      setAnswer(
        await api.askCopilot(`Why did alert ${alert.id} fire?`, {
          alert_id: alert.id,
          well_id: alert.well_id,
        }),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-2">
      <Button onClick={() => void ask()} disabled={busy} data-testid="why-fired">
        <HelpCircle size={14} aria-hidden /> {busy ? 'Asking the copilot…' : 'Why did this fire?'}
      </Button>
      {error && <p className="text-sm text-danger">{error}</p>}
      {answer && (
        <div
          className="rounded-lg border border-border bg-surface-2 p-3 text-sm"
          data-testid="why-answer"
        >
          <p className="whitespace-pre-line text-text">{answer.answer}</p>
          {answer.citations.length > 0 && (
            <ol className="mt-2 space-y-1 text-xs text-muted">
              {answer.citations.map((c) => (
                <li key={c.n}>
                  [{c.n}]{' '}
                  {c.kind === 'page' && c.document_id !== null ? (
                    <EvidenceLink
                      documentId={c.document_id}
                      pageNo={c.page_no ?? 1}
                      spanIds={c.span_ids}
                    >
                      {c.label}
                    </EvidenceLink>
                  ) : (
                    c.label
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}

function Actions({ alert, canAct, user }: { alert: AlertOut; canAct: boolean; user: string }) {
  const action = useAlertAction(user)
  const [dismissing, setDismissing] = useState(false)
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  if (!canAct)
    return <p className="text-sm text-muted">Your role can read alerts but not act on them.</p>
  const open = alert.status === 'new' || alert.status === 'ack'
  const dismiss = (e: FormEvent) => {
    e.preventDefault()
    if (!reason.trim()) return
    action.mutate({ id: alert.id, action: { kind: 'dismiss', reason: reason.trim() } })
    setDismissing(false)
    setReason('')
  }
  const last = alert.feedback[alert.feedback.length - 1]
  return (
    <div className="space-y-3" data-testid="alert-actions">
      <div className="flex flex-wrap items-center gap-2">
        {alert.status === 'new' && (
          <Button
            variant="primary"
            onClick={() => action.mutate({ id: alert.id, action: { kind: 'ack' } })}
          >
            <Check size={14} aria-hidden /> Acknowledge
          </Button>
        )}
        {open && !dismissing && (
          <Button onClick={() => setDismissing(true)}>
            <X size={14} aria-hidden /> Dismiss…
          </Button>
        )}
        {alert.acked_by && (
          <span className="text-xs text-muted">
            Acknowledged by {alert.acked_by}
            {alert.acked_at
              ? ` at ${new Date(alert.acked_at).toISOString().slice(11, 16)} UTC`
              : ''}
          </span>
        )}
        {alert.dismiss_reason && (
          <span className="text-xs text-muted">Dismissed: {alert.dismiss_reason}</span>
        )}
      </div>
      {dismissing && (
        <form onSubmit={dismiss} className="flex flex-wrap items-center gap-2">
          <label htmlFor="dismiss-reason" className="text-sm text-muted">
            Reason
          </label>
          <input
            id="dismiss-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            maxLength={500}
            placeholder="e.g. handled on the rig"
            className="min-w-60 flex-1 rounded-md border border-border bg-surface px-2 py-1 text-sm"
          />
          <Button type="submit" variant="primary" disabled={!reason.trim()}>
            Dismiss
          </Button>
          <Button onClick={() => setDismissing(false)}>Cancel</Button>
        </form>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-sm text-muted">
          <MessageSquare size={14} aria-hidden /> Was it useful?
        </span>
        <label htmlFor="feedback-comment" className="sr-only">
          Comment (optional)
        </label>
        <input
          id="feedback-comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={1000}
          placeholder="Comment (optional)"
          className="min-w-40 flex-1 rounded-md border border-border bg-surface px-2 py-1 text-sm"
        />
        {VERDICTS.map((v) => (
          <Button
            key={v.id}
            aria-pressed={last?.verdict === v.id}
            onClick={() => {
              action.mutate({ id: alert.id, action: { kind: 'feedback', verdict: v.id, comment } })
              setComment('')
            }}
            className={last?.verdict === v.id ? 'bg-surface-2' : ''}
          >
            {v.label}
          </Button>
        ))}
      </div>
      {action.isError && (
        <p role="alert" className="text-sm text-danger" data-testid="action-error">
          Not saved: {action.error.message}
        </p>
      )}
    </div>
  )
}

type DetailTab = 'evidence' | 'drivers' | 'dejavu' | 'actions'

function AlertDetail({ id }: { id: number }) {
  const q = useAlert(id)
  const me = useMe()
  const [tab, setTab] = useState<DetailTab>('evidence')
  const perms = me.data?.permissions ?? []
  if (q.isLoading) return <SkeletonBlock className="h-96 w-full" />
  if (q.isError || !q.data) return <p className="text-sm text-muted">Alert {id} not found.</p>
  const a = q.data
  const stream = a.evidence.filter((e) => e.kind === 'stream')
  const past = a.evidence.filter((e) => e.kind !== 'stream')
  const hasDejaVu = a.sources.includes('DEJA_VU') || a.alert_type === 'DEJA_VU'
  const tabs = [
    { id: 'evidence' as const, label: 'Evidence', count: a.evidence.length },
    { id: 'drivers' as const, label: 'Drivers', count: a.drivers.length },
    ...(hasDejaVu ? [{ id: 'dejavu' as const, label: 'Déjà Vu' }] : []),
    { id: 'actions' as const, label: 'What worked', count: a.recommendations.length },
  ]
  const caveat = typeof a.detail['ledger_caveat'] === 'string' ? a.detail['ledger_caveat'] : null
  return (
    <div className="space-y-4" data-testid="alert-detail">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={SEVERITY_TONE[a.severity]}>{a.severity}</Badge>
        <Badge tone="neutral">{a.alert_type.replace('_', ' ')}</Badge>
        {a.sources.length > 1 && (
          <span className="text-xs text-muted">sources: {a.sources.join(' + ')}</span>
        )}
        {a.synthetic && <SyntheticBadge />}
      </div>
      <div>
        <h2 className="text-lg font-semibold text-text">{a.title}</h2>
        <p className="mt-1 text-sm text-text">{a.message}</p>
        <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted">Score</dt>
            <dd className="num" data-testid="alert-score">
              {scoreText(a)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Well</dt>
            <dd>
              <Link to={`/live?well=${a.well_id}`} className="text-accent hover:underline">
                {a.well_name}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Depth / formation</dt>
            <dd className="num">
              {a.md_m !== null ? `${formatValue(a.md_m, 0)} m MD` : '—'} · {a.formation ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Data time</dt>
            <dd className="num">
              {new Date(a.t_data).toISOString().slice(0, 19).replace('T', ' ')} UTC
            </dd>
          </div>
        </dl>
      </div>
      {a.evidence.length === 0 && (
        <div
          role="alert"
          className="rounded-lg border border-danger bg-danger-bg px-3 py-2 text-sm text-danger"
          data-testid="no-evidence"
        >
          This alert carries no evidence. That is a defect: every alert must cite its data. Report
          it and do not act on it alone.
        </div>
      )}
      <Tabs tabs={tabs} value={tab} onChange={setTab} label="Alert detail" idPrefix="alert" />
      <TabPanel idPrefix="alert" id={tab}>
        {tab === 'evidence' && (
          <div className="space-y-4">
            {stream[0] && <StreamEvidence alert={a} ev={stream[0]} />}
            {past.length > 0 && (
              <div>
                <h3 className="mb-1 text-sm font-semibold text-text">
                  Past events behind this alert
                </h3>
                <ul className="space-y-1.5">
                  {past.map((e, i) => (
                    <PastEvent key={`${e.kind}-${e.event_id ?? i}`} ev={e} />
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        {tab === 'drivers' && <DriversBar drivers={a.drivers} />}
        {tab === 'dejavu' && <DejaVuTab id={a.id} />}
        {tab === 'actions' && (
          <div className="space-y-2" data-testid="recommendations">
            {a.recommendations.length === 0 ? (
              <p className="text-sm text-muted">
                The ledger has no recorded mitigations for this problem here.
              </p>
            ) : (
              <ul className="space-y-2">
                {a.recommendations.map((r) => (
                  <li key={r.action_code} className="flex flex-wrap items-center gap-3 text-sm">
                    <span className="min-w-44 font-medium text-text">{r.action_label}</span>
                    <IntervalBar
                      value={r.posterior_mean}
                      low={r.ci90_low}
                      high={r.ci90_high}
                      label={`${r.action_label} worked`}
                    />
                    <span className="num text-xs text-muted">
                      {pct(r.posterior_mean)} ({pct(r.ci90_low)}–{pct(r.ci90_high)}), n = {r.n}
                      {r.insufficient ? ' · too few uses to rank' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted" data-testid="alert-caveat">
              {caveat ?? 'Observational records: associated with success, not proven to cause it.'}{' '}
              <Link
                to={`/ledger?type=${a.event_type}`}
                className="text-accent hover:underline"
              >
                Open the ledger
              </Link>
            </p>
          </div>
        )}
      </TabPanel>
      <Card className="space-y-3">
        <Actions alert={a} canAct={perms.includes('act_alerts')} user={me.data?.user_id ?? 'you'} />
        {perms.includes('copilot') && <WhyFired alert={a} />}
      </Card>
    </div>
  )
}

export function AlertsPage() {
  const [params, setParams] = useSearchParams()
  const filterId = params.get('status') ?? 'open'
  const filter = STATUS_FILTERS.find((f) => f.id === filterId) ?? STATUS_FILTERS[0]!
  const q = useAlerts({ status: filter.status, limit: 200 })
  const items = useMemo(() => sortAlerts(q.data?.items ?? []), [q.data])
  const selected = Number(params.get('id')) || items[0]?.id || null
  const counts = q.data?.counts ?? {}
  const budgeted = items.filter((a) => !a.budget_exempt && a.status !== 'dismissed').length
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <Bell className="text-accent" aria-hidden />
        <h1 className="text-xl font-semibold text-text">Alerts</h1>
        <div role="group" aria-label="Status filter" className="flex gap-1">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f.id}
              aria-pressed={f.id === filter.id}
              className={f.id === filter.id ? 'bg-surface-2' : ''}
              onClick={() => {
                const next = new URLSearchParams(params)
                next.set('status', f.id)
                next.delete('id')
                setParams(next)
              }}
            >
              {f.label}
            </Button>
          ))}
        </div>
        <span className="text-sm text-muted" data-testid="alert-counts">
          {Object.entries(counts)
            .map(([k, v]) => `${v} ${k}`)
            .join(' · ') || 'no alerts'}
        </span>
        <span
          className="ml-auto text-xs text-muted"
          title="Non-critical alerts shown here; the engine allows at most 6 per well per 12 h"
        >
          {budgeted} non-critical shown · budget 6 per well per 12 h
        </span>
      </header>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <Card className="max-h-[75vh] overflow-y-auto">
          {q.isLoading ? (
            <SkeletonBlock className="h-64 w-full" />
          ) : items.length === 0 ? (
            <p className="text-sm text-muted">
              No {filter.label.toLowerCase()} alerts. Start a replay on the Live Well Monitor to see
              some.
            </p>
          ) : (
            <ul className="space-y-2" data-testid="alert-list">
              {items.map((a) => (
                <AlertRow key={a.id} a={a} selected={a.id === selected} />
              ))}
            </ul>
          )}
        </Card>
        <Card className="min-w-0">
          {selected !== null ? <AlertDetail id={selected} /> : <CardTitle>Pick an alert</CardTitle>}
        </Card>
      </div>
    </div>
  )
}
