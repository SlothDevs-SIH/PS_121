import { ArrowDown, TriangleAlert } from 'lucide-react'

import { eventMeta } from '../../lib/eventTypes'
import { formatValue, type LookAhead } from '../../lib/liveView'
import { pct } from '../../lib/risk'
import { Badge } from '../ui/Badge'

/** Formation now → next, with the TVD to the next top and its biggest offset hazard (the
 * prior from offsets, S7a). Prognosed tops are labelled estimates, with their spread. */
export function LookAheadBar({ la, formationNow }: { la: LookAhead; formationNow: string | null }) {
  const next = la.next
  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-surface px-4 py-3"
      data-testid="look-ahead"
    >
      <div>
        <div className="text-xs text-muted">Formation now</div>
        <div className="font-semibold text-text">
          {formationNow ?? la.current?.formation ?? '—'}
        </div>
      </div>
      <ArrowDown size={18} className="text-muted" aria-hidden />
      <div>
        <div className="text-xs text-muted">Next</div>
        <div className="font-semibold text-text" data-testid="look-ahead-next">
          {next ? next.formation : 'No deeper interval in the profile'}
        </div>
      </div>
      {next && la.distanceM !== null && (
        <div>
          <div className="text-xs text-muted">Top in</div>
          <div className="num font-semibold text-text" data-testid="look-ahead-distance">
            {formatValue(la.distanceM, 0)} m TVD
            {next.prognosed && (
              <span className="ml-1 text-xs font-normal text-muted">
                {' '}
                (prognosed
                {next.prognosis_spread_m !== null
                  ? ` ±${formatValue(next.prognosis_spread_m, 0)} m`
                  : ''}
                )
              </span>
            )}
          </div>
        </div>
      )}
      {la.hazard ? (
        <Badge
          tone={la.hazard.probability >= 0.3 ? 'danger' : 'warn'}
          data-testid="look-ahead-hazard"
        >
          <TriangleAlert size={12} aria-hidden />
          {eventMeta(la.hazard.event_type).label} {pct(la.hazard.probability)} in offsets
        </Badge>
      ) : next ? (
        <Badge tone="neutral">No offset hazard ≥ 10% next</Badge>
      ) : null}
    </div>
  )
}
