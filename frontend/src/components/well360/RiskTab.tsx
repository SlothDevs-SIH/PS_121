import { Link } from 'react-router'

import type { WellDetail } from '../../lib/api/client'
import { useRiskProfile } from '../../lib/api/hooks'
import { eventMeta } from '../../lib/eventTypes'
import { peakRisk, pct, riskColor } from '../../lib/risk'
import { Card, CardTitle } from '../ui/Card'
import { SkeletonBlock } from '../ui/Skeleton'
import { RiskCurve } from '../risk/RiskCurve'

/** Well 360 → Risk: the offset prior by formation (S7a) with the ledger one click away. */
export function RiskTab({ well }: { well: WellDetail }) {
  const risk = useRiskProfile(well.id)
  if (risk.isError)
    return (
      <p className="text-danger" role="alert">
        The risk profile could not be loaded.
      </p>
    )
  if (!risk.data) return <SkeletonBlock className="h-[26rem] w-full" />
  const p = risk.data
  const tdTvdss = well.status === 'drilling' ? p.td_tvdss_m : null
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <Card>
        <CardTitle>Risk by depth</CardTitle>
        <RiskCurve profile={p} bitTvdss={tdTvdss} width={560} height={460} />
      </Card>
      <Card>
        <CardTitle>Highest risk per formation</CardTitle>
        <ul className="space-y-2" data-testid="risk-peaks">
          {p.intervals.map((iv) => {
            const r = peakRisk(iv)
            return (
              <li key={iv.formation} className="flex items-start gap-3 text-sm">
                <span
                  aria-hidden
                  className="mt-1 size-3 shrink-0 rounded-sm border border-border"
                  style={{ background: r ? riskColor(r.probability) : 'transparent' }}
                />
                <span className="min-w-0 flex-1">
                  <span className="font-medium text-text">{iv.formation}</span>
                  {iv.prognosed && <span className="text-muted"> (prognosed)</span>}
                  <span className="block text-muted">{r ? r.label : 'no offsets reached it'}</span>
                  {r && r.probability >= 0.15 && (
                    <Link
                      to={`/ledger?type=${r.event_type}&fm=${encodeURIComponent(iv.formation)}`}
                      className="text-xs text-accent hover:underline"
                    >
                      What worked for {eventMeta(r.event_type).label.toLowerCase()} (
                      {pct(r.probability)} risk) →
                    </Link>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
        <p className="mt-3 text-xs text-muted">{p.method}</p>
      </Card>
    </div>
  )
}
