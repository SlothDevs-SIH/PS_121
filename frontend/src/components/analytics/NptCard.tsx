import { chronological, formatHours, type NptGroupBy } from '../../lib/analytics'
import { useNptBreakdown } from '../../lib/api/hooks'
import { eventMeta, markerPath } from '../../lib/eventTypes'
import { formatNumber } from '../../lib/format/units'
import { pct } from '../../lib/risk'
import { Card, CardTitle } from '../ui/Card'
import { SkeletonBlock } from '../ui/Skeleton'
import { BarList, type BarDatum } from './BarList'
import { ColumnChart } from './ColumnChart'
import { NptTable } from './NptTable'
import { QueryProblem } from './QueryProblem'

const TITLES: Record<NptGroupBy, { title: string; key: string }> = {
  event_type: { title: 'NPT by problem', key: 'Problem' },
  formation: { title: 'NPT by formation', key: 'Formation' },
  field: { title: 'NPT by field', key: 'Field' },
  year: { title: 'NPT by year', key: 'Year' },
  well: { title: 'NPT by well', key: 'Well' },
}

/** Bars shown before "and N more" (the table always has every row). */
const MAX_BARS = 10

function EventIcon({ type }: { type: string }) {
  const m = eventMeta(type)
  return (
    <svg width={12} height={12} aria-hidden className="shrink-0">
      <path d={markerPath(m.shape, 4.5)} transform="translate(6 6)" fill={m.colorVar} />
    </svg>
  )
}

/** One NPT breakdown: bars largest first (a column per year for the year view). */
export function NptCard({
  groupBy,
  eventType,
  formation,
}: {
  groupBy: NptGroupBy
  eventType: string | null
  formation: string | null
}) {
  const q = useNptBreakdown({ group_by: groupBy, event_type: eventType, formation })
  const t = TITLES[groupBy]
  const d = q.data
  const labelOf = (k: string) =>
    groupBy === 'event_type' ? eventMeta(k).label : k === 'unknown' ? 'not recorded' : k

  let body
  if (q.isError) body = <QueryProblem error={q.error} what="the NPT breakdown" />
  else if (!d) body = <SkeletonBlock className="h-40 w-full" />
  else if (d.rows.length === 0)
    body = (
      <p className="text-sm text-muted" data-testid="npt-empty">
        No events match these filters. Choose “any” problem or formation to widen them.
      </p>
    )
  else if (groupBy === 'year') {
    const rows = chronological(d.rows)
    body = (
      <ColumnChart
        data={rows.map((r) => ({
          key: r.key,
          value: r.npt_hours,
          title: `${labelOf(r.key)}: ${formatHours(r.npt_hours)} NPT, ${r.events} events`,
        }))}
        label={`${t.title}, ${rows[0]?.key}–${rows[rows.length - 1]?.key}: peak ${formatHours(
          Math.max(...rows.map((r) => r.npt_hours)),
        )}`}
        testId={`npt-chart-${groupBy}`}
      />
    )
  } else {
    const bars: BarDatum[] = d.rows.slice(0, MAX_BARS).map((r) => ({
      key: r.key,
      label: labelOf(r.key),
      value: r.npt_hours,
      valueText: formatHours(r.npt_hours),
      detail: `${pct(r.share_of_npt)} · ${formatNumber(r.events)} events`,
      colorVar: groupBy === 'event_type' ? eventMeta(r.key).colorVar : undefined,
      icon: groupBy === 'event_type' ? <EventIcon type={r.key} /> : undefined,
    }))
    body = (
      <>
        <BarList data={bars} label={t.title} testId={`npt-chart-${groupBy}`} />
        {d.rows.length > MAX_BARS && (
          <p className="mt-1 text-xs text-muted">
            and {d.rows.length - MAX_BARS} more in the table
          </p>
        )}
      </>
    )
  }

  return (
    <Card className="min-w-0" data-testid={`npt-${groupBy}`} aria-busy={q.isFetching}>
      <CardTitle>{t.title}</CardTitle>
      {body}
      {d && d.rows.length > 0 && (
        <>
          {d.events_without_npt > 0 && (
            <p className="mt-2 text-xs text-muted">
              {formatNumber(d.events_without_npt)} of {formatNumber(d.total_events)} events have no
              recorded NPT: counted as events, not as zero hours.
            </p>
          )}
          <NptTable rows={d.rows} caption={t.title} keyLabel={t.key} labelOf={labelOf} />
        </>
      )}
    </Card>
  )
}
