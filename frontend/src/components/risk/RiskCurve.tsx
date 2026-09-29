import { useMemo, useState } from 'react'

import { useTheme } from '../../app/themeContext'
import { eventMeta, markerPath } from '../../lib/eventTypes'
import { formatDepth } from '../../lib/format/units'
import { curveSteps, intervalBase, pct, topTypes, type RiskProfile } from '../../lib/risk'

interface Props {
  profile: RiskProfile
  /** Event types to draw; default: the three with the highest peak probability. */
  types?: string[]
  height?: number
  width?: number
  /** Compact: no per-interval table under the chart (map panel). */
  compact?: boolean
  /** Bit TVDSS to mark (a drilling well's current depth). */
  bitTvdss?: number | null
}

const AXIS_W = 92
const PAD_TOP = 10
const PAD_BOTTOM = 22

/**
 * Offset prior risk against depth (S7a): per formation interval, each event type's
 * probability as a step with its 90 % credible interval as a band. Prognosed intervals
 * (below a drilling well's TD, tops estimated from offsets) are dashed. The numbers are
 * always in the table beneath and in each step's tooltip: colour is never the only cue.
 */
export function RiskCurve({
  profile,
  types,
  height = 420,
  width = 460,
  compact = false,
  bitTvdss = null,
}: Props) {
  const { units } = useTheme()
  const drawn = useMemo(() => types ?? topTypes(profile), [types, profile])
  const [focus, setFocus] = useState<string | null>(null)
  const ivs = profile.intervals
  if (ivs.length === 0)
    return <p className="text-sm text-muted">No formation tops: no interval to score.</p>

  const lo = ivs[0]!.top_tvdss_m
  const hi = Math.max(...ivs.map((iv) => intervalBase(iv)))
  const series = drawn.map((t) => ({ type: t, steps: curveSteps(profile, t) }))
  const peak = Math.max(0.2, ...series.flatMap((s) => s.steps.map((st) => st.hi)))
  const pMax = Math.min(1, Math.ceil((peak * 1.02) / 0.1) * 0.1)
  const tickStep = pMax <= 0.5 ? 0.1 : 0.25
  const plotW = width - AXIS_W - 12
  const plotH = height - PAD_TOP - PAD_BOTTOM
  const y = (v: number) => PAD_TOP + ((v - lo) / (hi - lo || 1)) * plotH
  const x = (p: number) => AXIS_W + (p / pMax) * plotW
  const ticks = Array.from(
    { length: Math.floor(pMax / tickStep + 1e-9) + 1 },
    (_, i) => i * tickStep,
  )

  return (
    <figure className="min-w-0 space-y-2" data-testid="risk-curve">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <ul className="flex flex-wrap items-center gap-2" aria-label="Event types (click to focus)">
          {series.map(({ type }) => {
            const m = eventMeta(type)
            const on = focus === null || focus === type
            return (
              <li key={type}>
                <button
                  type="button"
                  aria-pressed={focus === type}
                  onClick={() => setFocus(focus === type ? null : type)}
                  className={`inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 ${on ? 'text-text' : 'text-muted opacity-60'}`}
                >
                  <svg width={12} height={12} aria-hidden>
                    <path
                      d={markerPath(m.shape, 4.5)}
                      transform="translate(6 6)"
                      fill={m.colorVar}
                    />
                  </svg>
                  {m.label}
                </button>
              </li>
            )
          })}
        </ul>
        {ivs.some((iv) => iv.prognosed) && (
          <span className="text-muted">- - - prognosed from offsets (below TD)</span>
        )}
      </div>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Offset prior risk by depth for ${profile.name}: ${series
          .map(({ type, steps }) => {
            const peak = steps.reduce((a, s) => (s.p > a.p ? s : a), steps[0]!)
            return peak
              ? `${eventMeta(type).label} peaks at ${pct(peak.p)} in ${peak.formation}`
              : ''
          })
          .filter(Boolean)
          .join('; ')}`}
        className="block max-w-full"
        viewBox={`0 0 ${width} ${height}`}
      >
        {/* formation bands and labels */}
        {ivs.map((iv) => {
          const y0 = y(iv.top_tvdss_m)
          const y1 = y(intervalBase(iv))
          return (
            <g key={iv.formation}>
              <rect
                x={0}
                y={y0}
                width={AXIS_W - 6}
                height={Math.max(0, y1 - y0)}
                fill={`var(--fm-${Math.min(9, iv.strat_order)})`}
                strokeDasharray={iv.prognosed ? '3 3' : undefined}
                stroke={iv.prognosed ? 'var(--text-muted)' : 'none'}
              />
              <line x1={0} x2={width} y1={y0} y2={y0} stroke="var(--border)" />
              {y1 - y0 > 14 && (
                <text x={4} y={y0 + 12} fontSize={10} fill="var(--text)">
                  {iv.formation.length > 13 ? `${iv.formation.slice(0, 12)}…` : iv.formation}
                </text>
              )}
              {y1 - y0 > 28 && (
                <text x={4} y={y0 + 24} fontSize={9} fill="var(--text-muted)" className="num">
                  {formatDepth(iv.top_tvdss_m, units, 'TVDSS')}
                </text>
              )}
            </g>
          )
        })}
        {/* probability grid */}
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={x(t)}
              x2={x(t)}
              y1={PAD_TOP}
              y2={height - PAD_BOTTOM}
              stroke="var(--border)"
              strokeDasharray="2 4"
            />
            <text
              x={x(t)}
              y={height - 6}
              fontSize={10}
              textAnchor="middle"
              fill="var(--text-muted)"
              className="num"
            >
              {pct(t)}
            </text>
          </g>
        ))}
        {/* CI bands, then step lines */}
        {series.map(({ type, steps }) => {
          const m = eventMeta(type)
          const dim = focus !== null && focus !== type
          return (
            <g key={type} opacity={dim ? 0.15 : 1} data-testid={`risk-series-${type}`}>
              {steps.map((s) => (
                <rect
                  key={`band-${s.formation}`}
                  x={x(s.lo)}
                  y={y(s.top)}
                  width={Math.max(1, x(s.hi) - x(s.lo))}
                  height={Math.max(0, y(s.base) - y(s.top))}
                  fill={m.colorVar}
                  opacity={0.12}
                />
              ))}
              {steps.map((s, i) => {
                const next = steps[i + 1]
                return (
                  <g key={`step-${s.formation}`}>
                    <line
                      x1={x(s.p)}
                      x2={x(s.p)}
                      y1={y(s.top)}
                      y2={y(s.base)}
                      stroke={m.colorVar}
                      strokeWidth={2.5}
                      strokeDasharray={s.prognosed ? '5 4' : undefined}
                    >
                      <title>
                        {`${m.label} in ${s.formation}${s.prognosed ? ' (prognosed)' : ''}: ${s.risk.label}`}
                      </title>
                    </line>
                    {next && next.top === s.base && (
                      <line
                        x1={x(s.p)}
                        x2={x(next.p)}
                        y1={y(s.base)}
                        y2={y(s.base)}
                        stroke={m.colorVar}
                        strokeWidth={1.5}
                        opacity={0.7}
                      />
                    )}
                  </g>
                )
              })}
            </g>
          )
        })}
        {bitTvdss !== null && bitTvdss >= lo && bitTvdss <= hi && (
          <g data-testid="risk-bit">
            <line
              x1={AXIS_W - 6}
              x2={width}
              y1={y(bitTvdss)}
              y2={y(bitTvdss)}
              stroke="var(--accent)"
              strokeWidth={1.5}
            />
            <text
              x={width - 4}
              y={y(bitTvdss) - 3}
              fontSize={10}
              textAnchor="end"
              fill="var(--accent)"
            >
              bit (TD)
            </text>
          </g>
        )}
      </svg>
      <figcaption className="text-xs text-muted">
        Probability of each problem in each formation from offsets within {profile.radius_km} km
        (weighted by distance and similarity; bands = 90% credible interval). A prior from history,
        not a prediction for this well{profile.synthetic ? ' · SYNTHETIC data' : ''}.
      </figcaption>
      {!compact && (
        <details className="text-sm" data-testid="risk-table">
          <summary className="cursor-pointer text-muted">Numbers per interval</summary>
          <div className="overflow-x-auto">
            <table className="mt-2 w-full text-left text-xs">
              <caption className="sr-only">Offset prior risk per interval</caption>
              <thead className="text-muted">
                <tr>
                  <th scope="col" className="py-1 pr-3">
                    Formation
                  </th>
                  {drawn.map((t) => (
                    <th key={t} scope="col" className="py-1 pr-3">
                      {eventMeta(t).label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ivs.map((iv) => (
                  <tr key={iv.formation} className="border-t border-border">
                    <th scope="row" className="py-1 pr-3 font-medium text-text">
                      {iv.formation}
                      {iv.prognosed && (
                        <span className="block font-normal text-muted">
                          prognosed ±{iv.prognosis_spread_m ?? '—'} m
                        </span>
                      )}
                    </th>
                    {drawn.map((t) => {
                      const r = iv.risks.find((x) => x.event_type === t)
                      return (
                        <td key={t} className="num py-1 pr-3">
                          {r ? (
                            <>
                              {pct(r.probability)}{' '}
                              <span className="text-muted">
                                ({pct(r.ci90_low)}–{pct(r.ci90_high)}) · {r.offsets_with_event}/
                                {r.offsets_total} offsets
                              </span>
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  )
}
