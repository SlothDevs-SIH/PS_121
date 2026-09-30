import { formatHours, type NptRow } from '../../lib/analytics'
import { formatNumber } from '../../lib/format/units'
import { pct } from '../../lib/risk'

/** Every number behind an NPT chart, in a disclosure: the chart's text alternative. */
export function NptTable({
  rows,
  caption,
  keyLabel,
  labelOf = (k) => k,
}: {
  rows: NptRow[]
  caption: string
  keyLabel: string
  labelOf?: (key: string) => string
}) {
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-muted">Show as table</summary>
      <div className="mt-1 overflow-x-auto">
        <table className="w-full text-left">
          <caption className="sr-only">{caption}</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1 pr-3 font-medium">
                {keyLabel}
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                NPT
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                Share
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                Median per event
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                Events
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                Wells
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-border">
                <th scope="row" className="py-1 pr-3 font-normal text-text">
                  {labelOf(r.key)}
                </th>
                <td className="num py-1 pr-3 text-right">{formatHours(r.npt_hours)}</td>
                <td className="num py-1 pr-3 text-right">{pct(r.share_of_npt, 1)}</td>
                <td className="num py-1 pr-3 text-right">{formatHours(r.median_npt_hours)}</td>
                <td className="num py-1 pr-3 text-right">{formatNumber(r.events)}</td>
                <td className="num py-1 text-right">{formatNumber(r.wells)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
