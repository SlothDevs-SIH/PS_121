import { Link } from 'react-router'

import { formatHours, MIN_WELLS } from '../../lib/analytics'
import { useRecurringProblems } from '../../lib/api/hooks'
import { eventMeta } from '../../lib/eventTypes'
import { formatNumber } from '../../lib/format/units'
import { SyntheticBadge } from '../SyntheticBadge'
import { Card, CardTitle } from '../ui/Card'
import { SkeletonBlock } from '../ui/Skeleton'
import { QueryProblem } from './QueryProblem'

const th = 'py-1 pr-3 font-medium'

/** Problems that keep coming back: the same problem in one formation across wells, and
 * the same problem more than once in a well. Each row links to its evidence. */
export function RecurringCard({
  minWells,
  onMinWells,
}: {
  minWells: number
  onMinWells: (n: number) => void
}) {
  const q = useRecurringProblems(minWells)
  const d = q.data
  return (
    <Card className="min-w-0" data-testid="recurring" aria-busy={q.isFetching}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="mb-0">Recurring problems</CardTitle>
        <div className="flex items-center gap-2">
          {d?.synthetic && <SyntheticBadge label="SYNTHETIC" />}
          <label className="flex items-center gap-2 text-xs text-muted">
            In at least
            <select
              className="h-9 rounded-lg border border-border bg-surface px-2 text-sm text-text"
              value={minWells}
              onChange={(e) => onMinWells(Number(e.target.value))}
              data-testid="recurring-min-wells"
            >
              {Array.from({ length: MIN_WELLS.max - MIN_WELLS.min + 1 }, (_, i) => (
                <option key={i} value={MIN_WELLS.min + i}>
                  {MIN_WELLS.min + i}
                </option>
              ))}
            </select>
            wells
          </label>
        </div>
      </div>
      {q.isError ? (
        <QueryProblem error={q.error} what="recurring problems" />
      ) : !d ? (
        <SkeletonBlock className="h-48 w-full" />
      ) : (
        <div className="space-y-4">
          <section aria-labelledby="recurring-across">
            <h3 id="recurring-across" className="mb-1 text-sm font-semibold text-text">
              Same problem, same formation, {d.min_wells}+ wells
            </h3>
            {d.across_wells.length === 0 ? (
              <p className="text-sm text-muted" data-testid="recurring-empty">
                No problem recurs in {d.min_wells} or more wells in one formation. Lower the number
                of wells to see smaller patterns.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table
                  className="w-full min-w-[34rem] text-left text-sm"
                  data-testid="recurring-across"
                >
                  <caption className="sr-only">
                    Problems recurring in the same formation across {d.min_wells} or more wells
                  </caption>
                  <thead className="text-xs text-muted">
                    <tr>
                      <th scope="col" className={th}>
                        Problem
                      </th>
                      <th scope="col" className={th}>
                        Formation
                      </th>
                      <th scope="col" className={`${th} text-right`}>
                        Wells
                      </th>
                      <th scope="col" className={`${th} text-right`}>
                        Events
                      </th>
                      <th scope="col" className={`${th} text-right`}>
                        NPT
                      </th>
                      <th scope="col" className={th}>
                        Years
                      </th>
                      <th scope="col" className={th}>
                        <span className="sr-only">Links</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.across_wells.map((r) => (
                      <tr
                        key={`${r.event_type}|${r.formation}`}
                        className="border-t border-border"
                        data-testid="recurring-row"
                      >
                        <th scope="row" className="py-1.5 pr-3 font-medium text-text">
                          {eventMeta(r.event_type).label}
                        </th>
                        <td className="py-1.5 pr-3">{r.formation}</td>
                        <td className="num py-1.5 pr-3 text-right">{formatNumber(r.wells)}</td>
                        <td className="num py-1.5 pr-3 text-right">{formatNumber(r.events)}</td>
                        <td className="num py-1.5 pr-3 text-right">{formatHours(r.npt_hours)}</td>
                        <td className="num py-1.5 pr-3 whitespace-nowrap text-muted">
                          {r.first_year === null
                            ? '—'
                            : r.first_year === r.last_year
                              ? r.first_year
                              : `${r.first_year}–${r.last_year}`}
                        </td>
                        <td className="py-1.5 whitespace-nowrap">
                          <Link
                            to={`/ledger?type=${encodeURIComponent(r.event_type)}&fm=${encodeURIComponent(r.formation)}`}
                            className="text-accent hover:underline"
                          >
                            What worked
                          </Link>
                          <span className="text-muted"> · </span>
                          <Link
                            to={`/search?q=${encodeURIComponent(eventMeta(r.event_type).label)}&type=${encodeURIComponent(r.event_type)}&fm=${encodeURIComponent(r.formation)}`}
                            className="text-accent hover:underline"
                          >
                            Reports
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <section aria-labelledby="recurring-within">
            <h3 id="recurring-within" className="mb-1 text-sm font-semibold text-text">
              Same problem twice or more in one well
            </h3>
            {d.within_wells.length === 0 ? (
              <p className="text-sm text-muted">No well had the same problem twice.</p>
            ) : (
              <ul className="grid gap-1 sm:grid-cols-2" data-testid="recurring-within">
                {d.within_wells.slice(0, 12).map((r) => (
                  <li
                    key={`${r.well_id}|${r.event_type}`}
                    className="flex flex-wrap items-center gap-x-2 rounded-lg border border-border px-3 py-1.5 text-sm"
                  >
                    <Link
                      to={`/wells/${r.well_id}?tab=events`}
                      className="font-medium text-accent hover:underline"
                    >
                      {r.well_name}
                    </Link>
                    <span className="text-text">{eventMeta(r.event_type).label}</span>
                    <span className="num ml-auto text-xs text-muted">
                      {r.events}× · {formatHours(r.npt_hours)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {d.within_wells.length > 12 && (
              <p className="mt-1 text-xs text-muted">
                and {d.within_wells.length - 12} more wells with a repeated problem
              </p>
            )}
          </section>
        </div>
      )}
    </Card>
  )
}
