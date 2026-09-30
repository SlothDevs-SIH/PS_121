import { alertsPerShift, countRows, formatHours, type AlertQuality } from '../../lib/analytics'
import { useAlertQuality, useMe } from '../../lib/api/hooks'
import { eventMeta } from '../../lib/eventTypes'
import { formatNumber } from '../../lib/format/units'
import { pct } from '../../lib/risk'
import { IntervalBar } from '../risk/IntervalBar'
import { Card, CardTitle } from '../ui/Card'
import { SkeletonBlock } from '../ui/Skeleton'
import { BarList } from './BarList'
import { QueryProblem } from './QueryProblem'

type Proportion = AlertQuality['precision']

const VERDICTS: Record<string, string> = {
  useful: 'Useful',
  not_useful: 'Not useful',
  false_alarm: 'False alarm',
}

function Rate({ title, p, what }: { title: string; p: Proportion; what: string }) {
  return (
    <div className="space-y-1 rounded-lg bg-surface-2 p-3" data-testid={`rate-${what}`}>
      <div className="text-xs text-muted">{title}</div>
      {p.n === 0 || p.mean === null ? (
        <p className="text-sm text-muted">No {what === 'precision' ? 'feedback' : 'alerts'} yet</p>
      ) : (
        <>
          <div className="num text-xl font-semibold text-text">
            {pct(p.mean)}{' '}
            <span className="text-xs font-normal text-muted">
              ({pct(p.ci90_low)}–{pct(p.ci90_high)})
            </span>
          </div>
          <IntervalBar
            value={p.mean}
            low={p.ci90_low}
            high={p.ci90_high}
            raw={p.k / p.n}
            label={title}
          />
          <div className="num text-xs text-muted">
            {formatNumber(p.k)} of {formatNumber(p.n)}
          </div>
        </>
      )}
    </div>
  )
}

function Counts({
  title,
  counts,
  labelOf = (k) => k,
}: {
  title: string
  counts: Record<string, number>
  labelOf?: (k: string) => string
}) {
  const rows = countRows(counts)
  return (
    <div className="min-w-0">
      <h3 className="mb-1 text-sm font-semibold text-text">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">None</p>
      ) : (
        <BarList
          label={title}
          data={rows.map((r) => ({
            key: r.key,
            label: labelOf(r.key),
            value: r.value,
            valueText: formatNumber(r.value),
          }))}
        />
      )}
    </div>
  )
}

/** Alert statistics (screen 9): precision from engineers' feedback, acknowledgement, and
 * alerts per shift of scored stream data, each with its sample size. */
export function AlertStatsCard() {
  const me = useMe()
  // Roles without read_live can't see alerts at all; say so rather than ask and fail.
  const denied = me.data ? !me.data.permissions.includes('read_live') : false
  const q = useAlertQuality(null, !denied && !me.isPending)
  const d = q.data
  return (
    <Card className="min-w-0" data-testid="alert-stats" aria-busy={q.isFetching}>
      <CardTitle>Alert statistics</CardTitle>
      {denied ? (
        <p className="text-sm text-muted" role="note" data-testid="alert-stats-denied">
          Your role does not include live alerts, so their statistics are not shown.
        </p>
      ) : q.isError ? (
        <QueryProblem error={q.error} what="live alert statistics" />
      ) : !d ? (
        <SkeletonBlock className="h-40 w-full" />
      ) : d.alerts === 0 ? (
        <p className="text-sm text-muted" data-testid="alert-stats-empty">
          No alerts have been raised yet. Alerts come only from the stream engine (start a replay on
          the Live Monitor); nothing here is simulated.
        </p>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Rate title="Precision (marked useful)" p={d.precision} what="precision" />
            <Rate title="Acknowledged" p={d.acknowledged} what="acknowledged" />
            <div className="space-y-1 rounded-lg bg-surface-2 p-3" data-testid="alerts-per-shift">
              <div className="text-xs text-muted">Alerts per shift</div>
              <div className="num text-xl font-semibold text-text">
                {d.alerts_per_12h === null ? '—' : formatNumber(d.alerts_per_12h, 2)}
              </div>
              <div className="text-xs text-muted">
                {alertsPerShift(d)}, {formatNumber(d.alerts)} alerts over{' '}
                {formatHours(d.data_hours, 2)} of stream data
              </div>
            </div>
            <div className="space-y-1 rounded-lg bg-surface-2 p-3">
              <div className="text-xs text-muted">Median time to acknowledge</div>
              <div className="num text-xl font-semibold text-text">
                {d.median_minutes_to_ack === null
                  ? '—'
                  : `${formatNumber(d.median_minutes_to_ack, 1)} min`}
              </div>
              <div className="text-xs text-muted">wall time from raised to acknowledged</div>
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Counts title="By problem" counts={d.by_type} labelOf={(k) => eventMeta(k).label} />
            <Counts title="By source" counts={d.by_source} />
            <Counts title="By severity" counts={d.by_severity} />
            <Counts
              title="Feedback (latest verdict per alert)"
              counts={d.feedback}
              labelOf={(k) => VERDICTS[k] ?? k}
            />
          </div>
          <p className="text-xs text-muted" data-testid="alert-stats-note">
            {d.note}
          </p>
        </div>
      )}
    </Card>
  )
}
