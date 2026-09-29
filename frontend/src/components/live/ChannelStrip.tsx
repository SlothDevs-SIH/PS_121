import { channelMeta, extent, formatValue, linePath } from '../../lib/liveView'

const W = 1000

interface Props {
  channel: string
  /** Sample times (ms since epoch), ascending. */
  times: number[]
  values: (number | null)[]
  /** Shared time domain so strips line up. */
  domain: [number, number]
  /** Vertical markers (e.g. alert times), ms. */
  markers?: { t: number; label: string }[]
  height?: number
}

/**
 * One stream channel as a strip (ADR-F19: SVG, not a chart library, so a 1 Hz update is a
 * path string). The latest value, its unit and the strip's range are text beside it;
 * gaps break the line rather than being drawn as zero.
 */
export function ChannelStrip({ channel, times, values, domain, markers = [], height = 56 }: Props) {
  const m = channelMeta(channel)
  const [lo, hi] = extent(values)
  const [t0, t1] = domain
  const x = (t: number) => ((t - t0) / (t1 - t0 || 1)) * W
  const y = (v: number) => height - ((v - lo) / (hi - lo)) * height
  const last = [...values].reverse().find((v) => v !== null && v !== undefined) ?? null
  const label = `${m.label}: latest ${formatValue(last, m.digits)} ${m.unit}, range ${formatValue(lo, m.digits)} to ${formatValue(hi, m.digits)}`
  return (
    <div className="grid grid-cols-[8.5rem_1fr] items-center gap-2" data-testid="channel-strip">
      <div className="min-w-0 text-right">
        <div className="truncate text-xs text-muted">{m.label}</div>
        <div className="num text-sm font-semibold text-text" data-testid={`latest-${channel}`}>
          {formatValue(last, m.digits)}{' '}
          <span className="text-xs font-normal text-muted">{m.unit}</span>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        preserveAspectRatio="none"
        width="100%"
        height={height}
        role="img"
        aria-label={label}
        className="block rounded-md bg-surface-2"
      >
        <title>{label}</title>
        {markers.map((mk) => (
          <line
            key={`${mk.t}-${mk.label}`}
            x1={x(mk.t)}
            x2={x(mk.t)}
            y1={0}
            y2={height}
            stroke="var(--danger)"
            strokeDasharray="4 3"
            vectorEffect="non-scaling-stroke"
          >
            <title>{mk.label}</title>
          </line>
        ))}
        <path
          d={linePath(times, values, x, y)}
          fill="none"
          stroke={m.color}
          strokeWidth={1.5}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  )
}
