import { ChevronDown, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'

import { useTheme } from '../../app/themeContext'
import type { EventSummary, EventTimeline } from '../../lib/api/client'
import { useEvent } from '../../lib/api/hooks'
import { eventMeta, markerPath, markerRadius } from '../../lib/eventTypes'
import { formatDepth, formatMudWeight, formatNumber } from '../../lib/format/units'
import { ConfidenceValue } from '../ConfidenceValue'
import { EvidenceLink } from '../evidence/EvidenceLink'
import { Badge } from '../ui/Badge'
import { Card, CardTitle } from '../ui/Card'
import { DataTable, type Column } from '../ui/DataTable'
import { Segmented } from '../ui/Segmented'

const PARAMS: Record<string, [string, string]> = {
  loss_rate_m3_h: ['Loss rate', 'm³/h'],
  total_loss_m3: ['Total loss', 'm³'],
  pit_gain_m3: ['Pit gain', 'm³'],
  sidpp_kpa: ['SIDPP', 'kPa'],
  sicp_kpa: ['SICP', 'kPa'],
  kill_mw_sg: ['Kill mud weight', 'SG'],
  overpull_kn: ['Overpull', 'kN'],
  torque_knm: ['Torque', 'kN·m'],
  jarring_h: ['Jarring', 'h'],
  gas_pct: ['Gas', '%'],
  h2s_ppm: ['H₂S', 'ppm'],
  ecd_sg: ['ECD', 'SG'],
  time_to_cure_h: ['Time to cure', 'h'],
}

type Order = 'date' | 'depth'

function dayNumber(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isNaN(t) ? null : t / 86_400_000
}

/** One strip: events along time (spud → completion) or along measured depth. */
function Strip({
  tl,
  order,
  onPick,
}: {
  tl: EventTimeline
  order: Order
  onPick: (id: number) => void
}) {
  const W = 800
  const H = 84
  const pts = tl.events
    .map((e) => ({ e, v: order === 'date' ? dayNumber(e.event_date ?? e.t_start) : e.md_m }))
    .filter((p): p is { e: EventSummary; v: number } => p.v !== null)
  const lo = order === 'date' ? (dayNumber(tl.spud_date) ?? Math.min(...pts.map((p) => p.v))) : 0
  const hi =
    order === 'date'
      ? (dayNumber(tl.completion_date) ?? Math.max(...pts.map((p) => p.v)))
      : (tl.td_md_m ?? Math.max(1, ...pts.map((p) => p.v)))
  const span = hi - lo || 1
  const x = (v: number) => 24 + ((v - lo) / span) * (W - 48)
  const label = (v: number) =>
    order === 'date'
      ? new Date(v * 86_400_000).toISOString().slice(0, 10)
      : `${formatNumber(v)} m MD`
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="group"
      aria-label={`Events by ${order}`}
      data-testid="events-strip"
    >
      <line x1={24} x2={W - 24} y1={H / 2} y2={H / 2} stroke="var(--border)" strokeWidth={2} />
      <text x={24} y={H - 6} fontSize={10} fill="var(--text-muted)">
        {order === 'date' ? (tl.spud_date ? `spud ${tl.spud_date}` : label(lo)) : '0 m MD'}
      </text>
      <text x={W - 24} y={H - 6} fontSize={10} textAnchor="end" fill="var(--text-muted)">
        {order === 'date'
          ? tl.completion_date
            ? `completed ${tl.completion_date}`
            : label(hi)
          : `TD ${label(hi)}`}
      </text>
      {pts.map(({ e, v }, i) => {
        const meta = eventMeta(e.event_type)
        const cy = H / 2 + (i % 2 ? 14 : -14)
        return (
          <g
            key={e.id}
            transform={`translate(${x(v)}, ${cy})`}
            role="button"
            tabIndex={0}
            aria-label={`${meta.label}, ${label(v)}`}
            className="cursor-pointer"
            onClick={() => onPick(e.id)}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault()
                onPick(e.id)
              }
            }}
          >
            <title>{`${meta.label}, ${label(v)}${e.npt_hours ? `, ${formatNumber(e.npt_hours, 1)} h NPT` : ''}`}</title>
            <line x1={0} x2={0} y1={0} y2={H / 2 - cy} stroke="var(--border)" />
            <path
              d={markerPath(meta.shape, markerRadius(e.npt_hours))}
              fill={meta.colorVar}
              stroke="var(--surface)"
              strokeDasharray={e.verified ? undefined : '2 1.5'}
            />
          </g>
        )
      })}
    </svg>
  )
}

function EventDetailPanel({ id }: { id: number }) {
  const { units } = useTheme()
  const { data, isPending, isError } = useEvent(id)
  if (isPending) return <p className="text-sm text-muted">Loading event…</p>
  if (isError || !data) return <p className="text-sm text-danger">Event could not be loaded.</p>
  const params = Object.entries(data.params).filter(([, v]) => v !== null)
  return (
    <div className="space-y-3 border-t border-border pt-3 text-sm" data-testid="event-detail">
      {data.description && <p className="text-text">{data.description}</p>}
      {params.length > 0 && (
        <dl className="flex flex-wrap gap-2">
          {params.map(([k, v]) => {
            const [label, unit] = PARAMS[k] ?? [k, '']
            return (
              <div key={k} className="rounded-lg bg-surface-2 px-2 py-1">
                <dt className="text-[0.7rem] text-muted">{label}</dt>
                <dd>
                  <ConfidenceValue verified={data.verified} confidence={data.confidence}>
                    {k.endsWith('_sg')
                      ? formatMudWeight(Number(v), units)
                      : `${formatNumber(Number(v), 1)} ${unit}`}
                  </ConfidenceValue>
                </dd>
              </div>
            )
          })}
        </dl>
      )}
      {data.mitigations.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted">Actions in the order they were tried</p>
          <ol className="mt-1 space-y-1">
            {data.mitigations.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-2">
                <span className="num text-xs text-muted">{m.seq}.</span>
                <span className="text-text">{m.action_text ?? m.action_code}</span>
                <Badge
                  tone={
                    m.outcome === 'success'
                      ? 'ok'
                      : m.outcome === 'fail'
                        ? 'danger'
                        : m.outcome === 'partial'
                          ? 'warn'
                          : 'neutral'
                  }
                >
                  {m.outcome}
                </Badge>
                {m.npt_hours_after !== null && (
                  <span className="text-xs text-muted">{formatNumber(m.npt_hours_after, 1)} h</span>
                )}
                {m.evidence[0] && (
                  <EvidenceLink
                    documentId={m.evidence[0].document_id}
                    pageNo={m.evidence[0].page_no}
                    spanIds={m.evidence[0].span_ids}
                    title={m.evidence[0].filename ?? undefined}
                  >
                    source
                  </EvidenceLink>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
      {data.lesson_card?.lesson && (
        <p className="rounded-lg bg-surface-2 p-2 text-text">
          <span className="text-xs font-medium text-muted">Lesson · </span>
          {data.lesson_card.lesson}
        </p>
      )}
    </div>
  )
}

export function EventsTab({ tl, initialOpen }: { tl: EventTimeline; initialOpen?: number | null }) {
  const { units } = useTheme()
  const [order, setOrder] = useState<Order>('date')
  const [open, setOpen] = useState<number | null>(initialOpen ?? null)
  const events = useMemo(() => {
    const key = (e: EventSummary) =>
      order === 'date'
        ? (e.event_date ?? e.t_start ?? '9999')
        : String(e.md_m ?? 1e9).padStart(12, '0')
    return [...tl.events].sort((a, b) => key(a).localeCompare(key(b)))
  }, [tl.events, order])

  type Op = EventTimeline['npt_operations'][number]
  const opColumns: Column<Op>[] = [
    {
      key: 'date',
      header: 'Report date',
      render: (o) => <span className="num">{o.report_date ?? '—'}</span>,
      sortValue: (o) => o.report_date,
    },
    {
      key: 'time',
      header: 'Time',
      render: (o) => (
        <span className="num whitespace-nowrap">
          {o.t_from ?? '—'}–{o.t_to ?? '—'}
        </span>
      ),
    },
    {
      key: 'hours',
      header: 'Hours',
      render: (o) => (
        <span className="num">{o.hours !== null ? formatNumber(o.hours, 1) : '—'}</span>
      ),
      sortValue: (o) => o.hours,
      align: 'right',
    },
    {
      key: 'desc',
      header: 'Operation',
      render: (o) => <span className="text-text">{o.description}</span>,
    },
    {
      key: 'ev',
      header: 'Source',
      render: (o) =>
        o.evidence[0] ? (
          <EvidenceLink
            documentId={o.evidence[0].document_id}
            pageNo={o.evidence[0].page_no}
            spanIds={o.evidence[0].span_ids}
            title={o.evidence[0].filename ?? undefined}
          >
            p.{o.evidence[0].page_no}
          </EvidenceLink>
        ) : (
          '—'
        ),
    },
  ]

  return (
    <div className="space-y-4">
      <Card className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="mb-0">
            {tl.events.length} events
            {tl.total_npt_hours !== null &&
              ` · ${formatNumber(tl.total_npt_hours, 1)} h NPT recorded`}
          </CardTitle>
          <Segmented
            label="Order events by"
            options={[
              { id: 'date', label: 'By date' },
              { id: 'depth', label: 'By depth' },
            ]}
            value={order}
            onChange={setOrder}
            testId="events-order"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(tl.counts_by_type).map(([t, n]) => (
            <Badge key={t} tone="neutral">
              {eventMeta(t).label}: {n}
            </Badge>
          ))}
        </div>
        {tl.events.length > 0 && <Strip tl={tl} order={order} onPick={setOpen} />}
      </Card>

      {tl.events.length === 0 && (
        <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted">
          No drilling problems were extracted from this well's reports.
        </p>
      )}
      <ul className="space-y-2" data-testid="event-list">
        {events.map((e) => {
          const meta = eventMeta(e.event_type)
          const expanded = open === e.id
          return (
            <li key={e.id} className="rounded-xl border border-border bg-surface p-3">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : e.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  data-testid="event-row"
                >
                  {expanded ? (
                    <ChevronDown size={15} aria-hidden />
                  ) : (
                    <ChevronRight size={15} aria-hidden />
                  )}
                  <svg width={14} height={14} viewBox="-7 -7 14 14" aria-hidden>
                    <path d={markerPath(meta.shape, 5)} fill={meta.colorVar} />
                  </svg>
                  <span className="font-medium text-text">
                    {meta.label}
                    {e.subtype ? ` (${e.subtype})` : ''}
                  </span>
                  <span className="truncate text-xs text-muted">
                    {e.event_date ?? 'no date'}
                    {e.md_m !== null ? ` · ${formatDepth(e.md_m, units, 'MD')}` : ''}
                    {e.tvdss_m !== null ? ` · ${formatDepth(e.tvdss_m, units, 'TVDSS')}` : ''}
                    {e.formation ? ` · ${e.formation}` : ''}
                  </span>
                </button>
                {e.severity && (
                  <Badge
                    tone={
                      e.severity === 'high'
                        ? 'danger'
                        : e.severity === 'medium'
                          ? 'warn'
                          : 'neutral'
                    }
                  >
                    {e.severity}
                  </Badge>
                )}
                {e.npt_hours !== null && (
                  <ConfidenceValue verified={e.verified} confidence={e.confidence}>
                    {formatNumber(e.npt_hours, 1)} h NPT
                  </ConfidenceValue>
                )}
                {e.evidence.map((ev) => (
                  <EvidenceLink
                    key={`${ev.document_id}-${ev.page_no}`}
                    documentId={ev.document_id}
                    pageNo={ev.page_no}
                    spanIds={ev.span_ids}
                    title={ev.filename ?? undefined}
                  >
                    {ev.doc_type ?? 'doc'} p.{ev.page_no}
                  </EvidenceLink>
                ))}
              </div>
              {expanded && <EventDetailPanel id={e.id} />}
            </li>
          )
        })}
      </ul>

      {tl.npt_operations.length > 0 && (
        <Card>
          <CardTitle>Non-productive time lines from the daily reports</CardTitle>
          <DataTable
            testId="npt-operations"
            caption="NPT operations"
            columns={opColumns}
            rows={tl.npt_operations}
            rowKey={(o) => o.id}
            initialSort={{ key: 'date', dir: 'asc' }}
          />
        </Card>
      )}
    </div>
  )
}
