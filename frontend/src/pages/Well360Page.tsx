import {
  Activity,
  BookOpenText,
  CheckCircle2,
  Columns3,
  FileStack,
  Gauge,
  LayoutList,
  Map as MapIcon,
  Search,
  Waypoints,
  XCircle,
} from 'lucide-react'
import { lazy, Suspense, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { useTheme } from '../app/themeContext'
import { ConfidenceValue } from '../components/ConfidenceValue'
import { EvidenceLink } from '../components/evidence/EvidenceLink'
import { LessonCardView } from '../components/knowledge/LessonCardView'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { Card, CardTitle } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { SkeletonBlock } from '../components/ui/Skeleton'
import { TabPanel, Tabs } from '../components/ui/Tabs'
import { EventsTab } from '../components/well360/EventsTab'
import { RiskTab } from '../components/well360/RiskTab'
import { WellSchematic } from '../components/well360/WellSchematic'
import {
  ApiError,
  type DocumentSummary,
  type EvidenceRef,
  type WellDetail,
} from '../lib/api/client'
import { useOffsets, useTimeline, useWell, useWellDocuments } from '../lib/api/hooks'
import { formatDepth, formatInches, formatMudWeight, formatNumber } from '../lib/format/units'
import { FLUIDS, fluidOf } from '../lib/wellTypes'

const TrajectoryTab = lazy(() =>
  import('../components/well360/TrajectoryTab').then((m) => ({ default: m.TrajectoryTab })),
)
const PageViewer = lazy(() =>
  import('../components/evidence/PageViewer').then((m) => ({ default: m.PageViewer })),
)

const TABS = ['overview', 'events', 'risk', 'trajectory', 'lessons', 'documents'] as const
type Tab = (typeof TABS)[number]

function Cite({ refs }: { refs: EvidenceRef[] }) {
  if (refs.length === 0) return <span className="text-xs text-muted">no citation</span>
  const r = refs[0]!
  return (
    <EvidenceLink
      documentId={r.document_id}
      pageNo={r.page_no}
      spanIds={r.span_ids}
      title={r.filename ?? undefined}
    >
      {r.doc_type ?? 'doc'} p.{r.page_no}
    </EvidenceLink>
  )
}

function DataQuality({ well }: { well: WellDetail }) {
  const pct = Math.round(well.data_quality.score * 100)
  return (
    <details
      className="group rounded-xl border border-border bg-surface px-3 py-2 text-sm"
      data-testid="data-quality"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2">
        <span
          className="grid size-9 place-items-center rounded-full text-xs font-semibold"
          style={{
            background: `conic-gradient(var(--ok) ${pct * 3.6}deg, var(--surface-2) 0deg)`,
          }}
          aria-hidden
        >
          <span className="grid size-7 place-items-center rounded-full bg-surface text-text">
            {pct}
          </span>
        </span>
        <span>
          <span className="block font-medium text-text">Data quality {pct}%</span>
          <span className="text-xs text-muted">why? (click)</span>
        </span>
      </summary>
      <ul className="mt-2 space-y-1">
        {well.data_quality.checks.map((c) => (
          <li key={c.name} className="flex items-start gap-1.5">
            {c.ok ? (
              <CheckCircle2 size={14} className="mt-0.5 text-ok" aria-label="ok" />
            ) : (
              <XCircle size={14} className="mt-0.5 text-danger" aria-label="missing" />
            )}
            <span>
              <span className="font-medium text-text">{c.name.replace('_', ' ')}</span>
              <span className="text-muted"> · {c.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}

function Overview({ well, onPickEvent }: { well: WellDetail; onPickEvent: (id: number) => void }) {
  const { units } = useTheme()
  const tl = useTimeline(well.id)
  type Casing = WellDetail['casing'][number]
  const casingColumns: Column<Casing>[] = [
    {
      key: 'od',
      header: 'Casing',
      render: (c) => (
        <ConfidenceValue verified={c.verified} confidence={c.confidence}>
          {formatInches(c.od_in)}
        </ConfidenceValue>
      ),
      sortValue: (c) => c.od_in,
    },
    { key: 'hole', header: 'Hole', render: (c) => formatInches(c.hole_size_in) },
    {
      key: 'shoe',
      header: 'Shoe',
      render: (c) => (
        <span className="num whitespace-nowrap">
          {c.shoe_md_m !== null ? formatDepth(c.shoe_md_m, units, 'MD') : '—'}
          {c.shoe_tvdss_m !== null && (
            <span className="block text-xs text-muted">
              {formatDepth(c.shoe_tvdss_m, units, 'TVDSS')}
            </span>
          )}
        </span>
      ),
      sortValue: (c) => c.shoe_md_m,
    },
    {
      key: 'cement',
      header: 'Cement',
      render: (c) =>
        c.cement.length === 0 ? (
          <span className="text-muted">—</span>
        ) : (
          <span className="flex flex-col gap-0.5">
            {c.cement.map((j) => (
              <ConfidenceValue key={j.id} verified={j.verified} confidence={j.confidence}>
                TOC {j.toc_md_m !== null ? formatDepth(j.toc_md_m, units, 'MD') : '—'}
                {j.returns ? ` · ${j.returns} returns` : ''}
                {j.slurry_density_sg !== null
                  ? ` · ${formatMudWeight(j.slurry_density_sg, units)}`
                  : ''}
              </ConfidenceValue>
            ))}
          </span>
        ),
    },
    { key: 'src', header: 'Source', render: (c) => <Cite refs={c.evidence} /> },
  ]
  type Mud = WellDetail['mud'][number]
  const mudColumns: Column<Mud>[] = [
    {
      key: 'range',
      header: 'Interval',
      render: (m) => (
        <span className="num whitespace-nowrap">
          {formatNumber(m.md_from_m)}–{formatDepth(m.md_to_m, units, 'MD')}
        </span>
      ),
      sortValue: (m) => m.md_from_m,
    },
    { key: 'hole', header: 'Hole', render: (m) => formatInches(m.hole_size_in) },
    { key: 'type', header: 'Mud', render: (m) => m.mud_type ?? '—' },
    {
      key: 'mw',
      header: 'Mud weight',
      render: (m) =>
        m.mw_sg !== null ? (
          <ConfidenceValue verified={m.verified} confidence={m.confidence}>
            {formatMudWeight(m.mw_sg, units)}
          </ConfidenceValue>
        ) : (
          '—'
        ),
      align: 'right',
    },
    { key: 'src', header: 'Source', render: (m) => <Cite refs={m.evidence} /> },
  ]
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,34rem)_minmax(0,1fr)]">
      <Card>
        <CardTitle>Wellbore</CardTitle>
        <WellSchematic
          well={well}
          events={tl.data?.events ?? well.recent_events}
          units={units}
          onSelectEvent={onPickEvent}
        />
        <p className="mt-1 text-xs text-muted">
          Hole sections and casing are drawn to scale in inches; dashed = extracted, not yet
          verified. Click an event marker to open it.
        </p>
      </Card>
      <div className="min-w-0 space-y-4">
        <Card>
          <CardTitle>Casing and cement</CardTitle>
          <DataTable
            testId="casing-table"
            caption="Casing and cement"
            columns={casingColumns}
            rows={well.casing}
            rowKey={(c) => c.id}
            initialSort={{ key: 'shoe', dir: 'asc' }}
            empty="No casing extracted from this well's reports yet."
          />
        </Card>
        <Card>
          <CardTitle>Mud programme</CardTitle>
          <DataTable
            testId="mud-table"
            caption="Mud programme"
            columns={mudColumns}
            rows={well.mud}
            rowKey={(m) => m.id}
            initialSort={{ key: 'range', dir: 'asc' }}
            empty="No mud programme extracted yet."
          />
        </Card>
        <Card>
          <CardTitle>Formation tops</CardTitle>
          {well.formation_tops.length === 0 ? (
            <p className="text-sm text-muted">No formation tops recorded.</p>
          ) : (
            <table className="w-full text-sm" data-testid="tops-table">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-1 text-left font-medium">Formation</th>
                  <th className="py-1 text-right font-medium">Top MD</th>
                  <th className="py-1 text-right font-medium">Top TVDSS</th>
                </tr>
              </thead>
              <tbody>
                {well.formation_tops.map((t) => (
                  <tr key={t.formation} className="border-t border-border">
                    <td className="py-1 text-text">{t.formation}</td>
                    <td className="num py-1 text-right">{formatDepth(t.top_md_m, units, 'MD')}</td>
                    <td className="num py-1 text-right">
                      {formatDepth(t.top_tvdss_m, units, 'TVDSS')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  )
}

function Documents({ wellId }: { wellId: number }) {
  const docs = useWellDocuments(wellId)
  const [open, setOpen] = useState<DocumentSummary | null>(null)
  const columns: Column<DocumentSummary>[] = [
    {
      key: 'file',
      header: 'File',
      render: (d) => <span className="break-all">{d.filename}</span>,
      sortValue: (d) => d.filename,
    },
    { key: 'type', header: 'Type', render: (d) => d.doc_type ?? '—', sortValue: (d) => d.doc_type },
    {
      key: 'date',
      header: 'Report date',
      render: (d) => <span className="num">{d.report_date ?? '—'}</span>,
      sortValue: (d) => d.report_date,
    },
    { key: 'pages', header: 'Pages', render: (d) => d.page_count ?? '—', align: 'right' },
    {
      key: 'events',
      header: 'Events',
      render: (d) => <span className="num">{d.event_count}</span>,
      sortValue: (d) => d.event_count,
      align: 'right',
    },
  ]
  if (docs.isPending) return <SkeletonBlock className="h-40 w-full" />
  return (
    <>
      <DataTable
        testId="well-documents"
        caption="Documents of this well"
        columns={columns}
        rows={docs.data?.items ?? []}
        rowKey={(d) => d.id}
        initialSort={{ key: 'date', dir: 'asc' }}
        onRowClick={(d) => d.page_count && setOpen(d)}
        empty="No documents are linked to this well."
      />
      {open && (
        <Suspense fallback={null}>
          <PageViewer
            documentId={open.id}
            title={open.filename}
            pageCount={open.page_count}
            onClose={() => setOpen(null)}
          />
        </Suspense>
      )}
    </>
  )
}

export function Well360Page() {
  const { units } = useTheme()
  const { wellId } = useParams()
  const id = Number(wellId)
  const valid = Number.isInteger(id) && id > 0
  const [params, setParams] = useSearchParams()
  const tab: Tab = (TABS as readonly string[]).includes(params.get('tab') ?? '')
    ? (params.get('tab') as Tab)
    : 'overview'
  const [focusEvent, setFocusEvent] = useState<number | null>(null)
  const well = useWell(valid ? id : null)
  const tl = useTimeline(valid ? id : null)
  const near = useOffsets(valid ? id : null, 5, 'SURFACE')
  const correlateIds = useMemo(
    () => [
      id,
      ...(near.data?.offsets ?? [])
        .filter((o) => o.status !== 'planned')
        .slice(0, 4)
        .map((o) => o.well_id),
    ],
    [id, near.data],
  )

  const setTab = (t: Tab) => {
    const next = new URLSearchParams(params)
    next.set('tab', t)
    setParams(next, { replace: true })
  }
  const openEvent = (eventId: number) => {
    setFocusEvent(eventId)
    setTab('events')
  }

  if (!valid) return <p className="text-danger">“{wellId}” is not a well id.</p>
  if (well.isError) {
    const notFound = well.error instanceof ApiError && well.error.status === 404
    return (
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-text">Well 360</h1>
        <p className="text-danger" role="alert">
          {notFound ? `There is no well with id ${id}.` : 'The well could not be loaded.'}
        </p>
        <Link to="/map" className="text-accent hover:underline">
          Pick a well on the map
        </Link>
      </div>
    )
  }
  const w = well.data
  if (!w)
    return (
      <div className="space-y-4" aria-busy="true">
        <SkeletonBlock className="h-10 w-72" />
        <SkeletonBlock className="h-96 w-full" />
      </div>
    )

  const fluid = fluidOf(w.fluid_type)
  const eventTotal = Object.values(w.event_counts).reduce((a, b) => a + b, 0)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-text">
              <span className="sr-only">Well 360:</span> {w.name}
            </h1>
            <Badge
              tone={w.status === 'drilling' ? 'warn' : w.status === 'planned' ? 'info' : 'neutral'}
            >
              {w.status}
            </Badge>
            {fluid && (
              <Badge tone="neutral">
                <span
                  aria-hidden
                  className="size-2 rounded-full"
                  style={{ background: FLUIDS[fluid].colorVar }}
                />
                {FLUIDS[fluid].label}
              </Badge>
            )}
            {w.synthetic && <SyntheticBadge label="SYNTHETIC" />}
            {w.datum_assumed && <Badge tone="warn">datum assumed</Badge>}
            {w.trajectory_assumed && <Badge tone="warn">trajectory assumed</Badge>}
          </div>
          <p className="text-sm text-muted" data-testid="well-facts">
            {w.field} · {w.well_type ?? 'type —'} · {w.profile ?? '—'} profile · rig{' '}
            {w.rig_name ?? '—'} · spud {w.spud_date ?? '—'}
            {w.completion_date ? ` · completed ${w.completion_date}` : ''}
            {w.td_md_m !== null ? ` · TD ${formatDepth(w.td_md_m, units, 'MD')}` : ''}
            {w.aliases.length > 0 ? ` · also written ${w.aliases.join(', ')}` : ''}
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-1 text-sm">
            <Link
              to={`/map?well=${w.id}`}
              className="inline-flex items-center gap-1 text-accent hover:underline"
            >
              <MapIcon size={14} aria-hidden /> On the map
            </Link>
            <Link
              to={`/correlation?wells=${correlateIds.join(',')}`}
              className="inline-flex items-center gap-1 text-accent hover:underline"
              data-testid="correlate-link"
            >
              <Columns3 size={14} aria-hidden /> Correlate with nearest offsets
            </Link>
            <Link
              to={`/search?well=${w.id}`}
              className="inline-flex items-center gap-1 text-accent hover:underline"
            >
              <Search size={14} aria-hidden /> Search this well's reports
            </Link>
          </div>
        </div>
        <DataQuality well={w} />
      </div>

      <Tabs
        label="Well 360 sections"
        idPrefix="w360"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'overview', label: 'Overview', icon: <LayoutList size={14} aria-hidden /> },
          {
            id: 'events',
            label: 'Events',
            icon: <Activity size={14} aria-hidden />,
            count: eventTotal,
          },
          { id: 'risk', label: 'Risk', icon: <Gauge size={14} aria-hidden /> },
          { id: 'trajectory', label: 'Trajectory', icon: <Waypoints size={14} aria-hidden /> },
          {
            id: 'lessons',
            label: 'Lessons',
            icon: <BookOpenText size={14} aria-hidden />,
            count: w.lessons.length,
          },
          {
            id: 'documents',
            label: 'Documents',
            icon: <FileStack size={14} aria-hidden />,
            count: w.documents.total,
          },
        ]}
      />

      <TabPanel idPrefix="w360" id={tab}>
        {tab === 'overview' && <Overview well={w} onPickEvent={openEvent} />}
        {tab === 'events' &&
          (tl.data ? (
            <EventsTab key={focusEvent ?? 'none'} tl={tl.data} initialOpen={focusEvent} />
          ) : (
            <SkeletonBlock className="h-64 w-full" />
          ))}
        {tab === 'risk' && <RiskTab well={w} />}
        {tab === 'trajectory' && (
          <Suspense fallback={<SkeletonBlock className="h-[30rem] w-full rounded-xl" />}>
            <TrajectoryTab well={w} events={tl.data?.events ?? w.recent_events} />
          </Suspense>
        )}
        {tab === 'lessons' &&
          (w.lessons.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted">
              No lessons yet: they are written from this well's extracted events.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {w.lessons.map((l) => (
                <LessonCardView key={l.event_id} card={l} showWell={false} />
              ))}
            </div>
          ))}
        {tab === 'documents' && <Documents wellId={w.id} />}
      </TabPanel>
    </div>
  )
}
