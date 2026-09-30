import { BarChart3, Clock, Info, ListChecks, TriangleAlert } from 'lucide-react'
import { motion } from 'motion/react'
import { useSearchParams } from 'react-router'

import { AlertStatsCard } from '../components/analytics/AlertStatsCard'
import { HeatmapCard } from '../components/analytics/HeatmapCard'
import { NptCard } from '../components/analytics/NptCard'
import { QueryProblem } from '../components/analytics/QueryProblem'
import { RecurringCard } from '../components/analytics/RecurringCard'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { KpiCard } from '../components/ui/KpiCard'
import { filtersToParams, parseFilters, type AnalyticsFilters } from '../lib/analytics'
import { useFormations, useNptBreakdown } from '../lib/api/hooks'
import { EVENT_TYPES, eventMeta } from '../lib/eventTypes'
import { pct } from '../lib/risk'
import { staggerContainer } from '../lib/motion'
import { FLUIDS } from '../lib/wellTypes'
import { useUiStore } from '../stores/ui'

/**
 * Analytics (screen 9, FRONTEND_PLAN §4.9) for drilling managers: where the NPT went (by
 * problem, formation, field and year, and formation × year), which problems recur, and how
 * useful the live alerts have been. Filters live in the URL (?type=&fm=&min=).
 */
export function AnalyticsPage() {
  const [params, setParams] = useSearchParams()
  const filters = parseFilters(params)
  const { type, fm } = filters
  const formations = useFormations()
  const wellType = useUiStore((s) => s.wellType)
  const byType = useNptBreakdown({ group_by: 'event_type', event_type: type, formation: fm })
  const set = (patch: Partial<AnalyticsFilters>) =>
    setParams(filtersToParams(params, patch), { replace: true })
  const select = 'h-9 max-w-full rounded-lg border border-border bg-surface px-2 text-sm text-text'
  const d = byType.data
  const top = d?.rows[0]

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-text">
            <BarChart3 size={22} aria-hidden className="text-accent" /> Analytics
          </h1>
          <p className="text-sm text-muted">
            Non-productive time and recurring problems from the drilling reports, and how the live
            alerts have fared.
          </p>
        </div>
        {d?.synthetic && <SyntheticBadge />}
      </div>

      <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Analytics filters">
        <label className="flex min-w-0 items-center gap-2 text-xs text-muted">
          Problem
          <select
            className={select}
            value={type ?? ''}
            onChange={(e) => set({ type: e.target.value || null })}
            data-testid="analytics-type"
          >
            <option value="">any</option>
            {Object.entries(EVENT_TYPES).map(([code, m]) => (
              <option key={code} value={code}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-0 items-center gap-2 text-xs text-muted">
          Formation
          <select
            className={select}
            value={fm ?? ''}
            onChange={(e) => set({ fm: e.target.value || null })}
            data-testid="analytics-formation"
          >
            <option value="">any</option>
            {(formations.data ?? []).map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        {(type || fm) && (
          <button
            type="button"
            className="h-9 rounded-lg px-2 text-sm text-accent hover:underline"
            onClick={() => set({ type: null, fm: null })}
          >
            Clear filters
          </button>
        )}
      </div>

      {wellType !== 'all' && (
        <p
          className="flex items-start gap-2 rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm text-muted"
          role="note"
          data-testid="analytics-well-type-note"
        >
          <Info size={16} aria-hidden className="mt-0.5 shrink-0" />
          These figures cover every well: the analytics service has no well-type filter, so the{' '}
          {FLUIDS[wellType].plural.toLowerCase()} filter does not apply here.
        </p>
      )}

      <section aria-labelledby="npt-heading" className="space-y-4">
        <h2 id="npt-heading" className="text-lg font-semibold text-text">
          Non-productive time
          {(type || fm) && (
            <span className="text-sm font-normal text-muted">
              {' '}
              · {type ? eventMeta(type).label : 'any problem'}
              {fm ? ` in ${fm}` : ''}
            </span>
          )}
        </h2>
        {byType.isError ? (
          <QueryProblem error={byType.error} what="the NPT summary" />
        ) : (
          <motion.div
            className="grid grid-cols-1 gap-4 sm:grid-cols-3"
            variants={staggerContainer}
            initial="hidden"
            animate="show"
          >
            <KpiCard
              testId="kpi-npt"
              label="NPT recorded"
              value={d ? d.total_npt_hours : null}
              suffix="h"
              icon={<Clock size={18} />}
              hint={top ? `Most from ${eventMeta(top.key).label} (${pct(top.share_of_npt)})` : ' '}
            />
            <KpiCard
              testId="kpi-events"
              label="Events"
              value={d ? d.total_events : null}
              icon={<TriangleAlert size={18} />}
              hint="Each cites the report lines it came from"
            />
            <KpiCard
              testId="kpi-no-npt"
              label="Events without recorded NPT"
              value={d ? d.events_without_npt : null}
              icon={<ListChecks size={18} />}
              hint="Counted as events, never as zero hours"
            />
          </motion.div>
        )}
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
          <NptCard groupBy="event_type" eventType={type} formation={fm} />
          <NptCard groupBy="formation" eventType={type} formation={fm} />
          <NptCard groupBy="field" eventType={type} formation={fm} />
          <NptCard groupBy="year" eventType={type} formation={fm} />
        </div>
        <HeatmapCard eventType={type} formation={fm} />
      </section>

      <section aria-label="Recurring problems">
        <RecurringCard minWells={filters.minWells} onMinWells={(n) => set({ minWells: n })} />
      </section>

      <section aria-label="Alert statistics">
        <AlertStatsCard />
      </section>
    </div>
  )
}
