import { bandScale, linearScale } from '../../lib/analytics'
import { formatNumber } from '../../lib/format/units'

const W = 1000
const H = 150

export interface ColumnDatum {
  key: string
  value: number
  /** Tooltip text for the column, e.g. "2019: 212.0 h NPT, 14 events". */
  title: string
}

interface Props {
  data: ColumnDatum[]
  /** Accessible summary of the whole chart (the table beside it has every number). */
  label: string
  tickFormat?: (v: number) => string
  testId?: string
}

/**
 * Vertical columns over an ordered axis (years), React SVG on our own band and linear
 * scales. The SVG stretches with its card; axis labels are HTML so text never distorts,
 * and they thin out (every k-th) when there are more columns than fit.
 */
export function ColumnChart({ data, label, tickFormat = (v) => formatNumber(v), testId }: Props) {
  const y = linearScale(Math.max(0, ...data.map((d) => d.value)), H, 0)
  const bands = bandScale(
    data.map((d) => d.key),
    0,
    W,
    data.length > 20 ? 4 : 10,
  )
  const every = Math.max(1, Math.ceil(data.length / 8))
  const pct = (px: number) => `${(px / W) * 100}%`
  return (
    <figure className="min-w-0" data-testid={testId}>
      <div className="grid grid-cols-[2.5rem_1fr] gap-1">
        <div aria-hidden className="relative text-[0.65rem] text-muted" style={{ height: H }}>
          {y.ticks.map((t) => (
            <span
              key={t}
              className="num absolute right-0 -translate-y-1/2 whitespace-nowrap"
              style={{ top: `${(y.at(t) / H) * 100}%` }}
            >
              {tickFormat(t)}
            </span>
          ))}
        </div>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          width="100%"
          height={H}
          role="img"
          aria-label={label}
          className="block overflow-visible"
        >
          <title>{label}</title>
          {y.ticks.map((t) => (
            <line
              key={t}
              x1={0}
              x2={W}
              y1={y.at(t)}
              y2={y.at(t)}
              stroke="var(--border)"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {data.map((d, i) => {
            const b = bands[i]!
            const top = y.at(d.value)
            return (
              <rect
                key={d.key}
                x={b.start}
                y={top}
                width={b.size}
                height={Math.max(0, H - top)}
                fill="var(--accent)"
                data-testid="column"
              >
                <title>{d.title}</title>
              </rect>
            )
          })}
        </svg>
        <span aria-hidden />
        <div aria-hidden className="relative h-4 text-[0.65rem] text-muted">
          {data.map((d, i) =>
            i % every === 0 ? (
              <span
                key={d.key}
                className="num absolute top-0 -translate-x-1/2 whitespace-nowrap"
                style={{ left: pct(bands[i]!.start + bands[i]!.size / 2) }}
              >
                {d.key}
              </span>
            ) : null,
          )}
        </div>
      </div>
    </figure>
  )
}
