import { useMemo } from 'react'

import {
  cellKey,
  formatHours,
  heatmapFormations,
  heatmapGrid,
  HEATMAP_ROWS,
} from '../../lib/analytics'
import { useNptBreakdown, useNptByYearFor } from '../../lib/api/hooks'
import { Card, CardTitle } from '../ui/Card'
import { SkeletonBlock } from '../ui/Skeleton'
import { NptHeatmap } from './NptHeatmap'
import { QueryProblem } from './QueryProblem'

/** Formation × year NPT: the formations with the most NPT, one by-year breakdown each. */
export function HeatmapCard({
  eventType,
  formation,
}: {
  eventType: string | null
  formation: string | null
}) {
  const byFormation = useNptBreakdown({ group_by: 'formation', event_type: eventType, formation })
  const formations = useMemo(() => heatmapFormations(byFormation.data), [byFormation.data])
  const years = useNptByYearFor(formations, eventType)
  const failed = years.find((r) => r.isError)
  const ready = years.length > 0 && years.every((r) => r.data)
  // A few dozen rows at most: cheap enough to rebuild on every render.
  const grid = ready
    ? heatmapGrid(formations.map((fm, i) => ({ formation: fm, byYear: years[i]!.data! })))
    : null

  let body
  if (byFormation.isError) body = <QueryProblem error={byFormation.error} what="the heatmap" />
  else if (failed) body = <QueryProblem error={failed.error} what="the heatmap" />
  else if (byFormation.data && formations.length === 0)
    body = (
      <p className="text-sm text-muted" data-testid="heatmap-empty">
        No events with a recorded formation match these filters.
      </p>
    )
  else if (!grid) body = <SkeletonBlock className="h-48 w-full" />
  else
    body = (
      <>
        <NptHeatmap grid={grid} />
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted">Show as table</summary>
          <div className="mt-1 overflow-x-auto">
            <table className="text-left">
              <caption className="sr-only">NPT hours by formation and year</caption>
              <thead className="text-muted">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Formation
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    NPT by year
                  </th>
                </tr>
              </thead>
              <tbody>
                {grid.formations.map((fm) => (
                  <tr key={fm} className="border-t border-border align-top">
                    <th scope="row" className="py-1 pr-3 font-normal text-text">
                      {fm}
                    </th>
                    <td className="num py-1">
                      {grid.years
                        .flatMap((y) => {
                          const c = grid.cells.get(cellKey(fm, y))
                          return c ? [`${y}: ${formatHours(c.hours)} (${c.events})`] : []
                        })
                        .join(' · ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </>
    )

  return (
    <Card className="min-w-0" data-testid="npt-heatmap-card">
      <CardTitle>NPT by formation and year</CardTitle>
      <p className="mb-2 text-xs text-muted">
        The {HEATMAP_ROWS} formations with the most NPT; darker is more hours, and every cell states
        its hours.
      </p>
      {body}
    </Card>
  )
}
