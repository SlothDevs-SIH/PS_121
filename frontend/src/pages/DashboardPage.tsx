import {
  ArrowRight,
  BellOff,
  ClipboardCheck,
  Drill,
  FileStack,
  Layers,
  TriangleAlert,
} from 'lucide-react'
import { motion } from 'motion/react'
import { lazy, Suspense, useMemo } from 'react'
import { Link, useNavigate } from 'react-router'

import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { Card, CardTitle } from '../components/ui/Card'
import { KpiCard } from '../components/ui/KpiCard'
import { SkeletonBlock } from '../components/ui/Skeleton'
import { useTheme } from '../app/themeContext'
import { useDocuments, useEvents, useReviewCounts, useWells } from '../lib/api/hooks'
import { eventMeta } from '../lib/eventTypes'
import { formatDepth } from '../lib/format/units'
import { staggerContainer, staggerItem } from '../lib/motion'
import { FLUID_ORDER, FLUIDS, fluidOf, matchesFilter } from '../lib/wellTypes'
import { useUiStore } from '../stores/ui'

const WellMap = lazy(() => import('../components/map/WellMap'))

export function DashboardPage() {
  const { units } = useTheme()
  const wellType = useUiStore((s) => s.wellType)
  const navigate = useNavigate()
  const wells = useWells()
  const docs = useDocuments()
  const events = useEvents()
  const review = useReviewCounts()

  const all = useMemo(() => wells.data?.items ?? [], [wells.data])
  const shown = useMemo(
    () => all.filter((w) => matchesFilter(w.fluid_type, wellType)),
    [all, wellType],
  )
  const shownIds = useMemo(() => new Set(shown.map((w) => w.id)), [shown])
  const drilling = all.filter((w) => w.status === 'drilling')

  const docItems = docs.data?.items ?? []
  const indexed = docItems.filter((d) => d.index_status === 'done').length
  const eventItems = useMemo(
    () => (events.data?.items ?? []).filter((e) => wellType === 'all' || shownIds.has(e.well_id)),
    [events.data, wellType, shownIds],
  )
  const recent = useMemo(
    () =>
      [...eventItems]
        .sort((a, b) => (b.event_date ?? '').localeCompare(a.event_date ?? ''))
        .slice(0, 6),
    [eventItems],
  )
  const moreEvents = Boolean(events.data?.next_cursor)

  const byFluid = FLUID_ORDER.map((f) => ({
    f,
    n: all.filter((w) => fluidOf(w.fluid_type) === f).length,
  }))

  const mapWells = all.map((w) => ({
    id: w.id,
    name: w.name,
    lat: w.lat,
    lon: w.lon,
    status: w.status,
    fluid: w.fluid_type ?? null,
    role: 'other' as const,
    dimmed: !shownIds.has(w.id),
  }))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text">Dashboard</h1>
          <p className="text-sm text-muted">
            {wellType === 'all' ? 'All wells' : FLUIDS[wellType].plural} · extracted from the
            field's drilling reports
          </p>
        </div>
        {all.some((w) => w.synthetic) && <SyntheticBadge />}
      </div>

      <motion.div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        variants={staggerContainer}
        initial="hidden"
        animate="show"
      >
        <KpiCard
          testId="kpi-wells"
          label={wellType === 'all' ? 'Wells' : FLUIDS[wellType].plural}
          value={wells.data ? shown.length : null}
          icon={<Layers size={18} />}
          footer={
            <div
              className="flex h-1.5 overflow-hidden rounded-full bg-surface-2"
              aria-label="Wells by fluid"
            >
              {byFluid.map(({ f, n }) => (
                <span
                  key={f}
                  title={`${FLUIDS[f].plural}: ${n}`}
                  style={{ flexGrow: n, background: FLUIDS[f].colorVar }}
                />
              ))}
            </div>
          }
          hint={byFluid.map(({ f, n }) => `${n} ${FLUIDS[f].label.toLowerCase()}`).join(' · ')}
        />
        <KpiCard
          testId="kpi-drilling"
          label="Drilling now"
          value={wells.data ? drilling.length : null}
          icon={<Drill size={18} />}
          live={drilling.length > 0}
          hint={drilling.map((w) => w.name).join(', ') || 'No well is drilling'}
        />
        <KpiCard
          testId="kpi-events"
          label="Drilling events extracted"
          value={events.data ? eventItems.length : null}
          suffix={moreEvents ? '+' : undefined}
          icon={<TriangleAlert size={18} />}
          hint="Each cites the report lines it came from"
        />
        <KpiCard
          testId="kpi-documents"
          label="Reports indexed"
          value={docs.data ? indexed : null}
          suffix={docs.data ? `/ ${docs.data.total}` : undefined}
          icon={<FileStack size={18} />}
          hint={
            review.data ? (
              <Link to="/documents" className="inline-flex items-center gap-1 hover:text-text">
                <ClipboardCheck size={12} aria-hidden />
                {review.data.pending ?? 0} extractions awaiting review
              </Link>
            ) : (
              'Review backlog loading…'
            )
          }
        />
      </motion.div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card className="flex flex-col p-0">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4">
            <CardTitle className="mb-0">Field map</CardTitle>
            <Link
              to="/map"
              className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
            >
              Open Map Explorer <ArrowRight size={14} aria-hidden />
            </Link>
          </div>
          <div className="mt-3 min-h-80 flex-1 px-4 pb-4">
            <Suspense fallback={<SkeletonBlock className="h-full w-full" />}>
              <WellMap
                wells={mapWells}
                interactive={false}
                onSelect={(id) => navigate(`/map?well=${id}`)}
                testId="dashboard-map"
                label="Overview map of the field"
              />
            </Suspense>
          </div>
        </Card>

        <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
          <Card>
            <CardTitle>Recent drilling events</CardTitle>
            {events.isPending ? (
              <div className="space-y-2">
                {[0, 1, 2, 3].map((k) => (
                  <SkeletonBlock key={k} className="h-12 w-full" />
                ))}
              </div>
            ) : recent.length === 0 ? (
              <p className="text-sm text-muted">
                No events extracted yet: they appear once reports are processed.
              </p>
            ) : (
              <motion.ul
                className="space-y-1.5"
                variants={staggerContainer}
                initial="hidden"
                animate="show"
                data-testid="recent-events"
              >
                {recent.map((e) => (
                  <motion.li
                    key={e.id}
                    variants={staggerItem}
                    className="flex items-center gap-3 rounded-lg border border-border px-3 py-2"
                  >
                    <span
                      aria-hidden
                      className="h-8 w-1 rounded-full"
                      style={{
                        background:
                          e.severity === 'high'
                            ? 'var(--danger)'
                            : e.severity === 'medium'
                              ? 'var(--warn)'
                              : 'var(--text-muted)',
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-text">
                        {eventMeta(e.event_type).label}
                        {e.subtype ? ` (${e.subtype})` : ''}
                      </p>
                      <p className="truncate text-xs text-muted">
                        {e.well_name}
                        {e.md_m !== null ? ` · ${formatDepth(e.md_m, units, 'MD')}` : ''}
                        {e.formation ? ` · ${e.formation}` : ''}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="num text-xs text-muted">{e.event_date ?? '—'}</p>
                      {!e.verified && (
                        <Badge tone="neutral" title="Extracted, not yet verified by an engineer">
                          unverified
                        </Badge>
                      )}
                    </div>
                  </motion.li>
                ))}
              </motion.ul>
            )}
          </Card>
          <Card>
            <CardTitle>Live alerts</CardTitle>
            <div className="flex items-center gap-3 rounded-lg border border-dashed border-border p-4 text-sm text-muted">
              <BellOff size={20} aria-hidden />
              <p>
                Real-time alerts arrive with the replay stream and alert engine (Part 4–5). Nothing
                here is simulated in the meantime.
              </p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
