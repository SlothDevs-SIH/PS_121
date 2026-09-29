import { pct } from '../../lib/risk'

interface Props {
  /** Point estimate (posterior mean), 0-1. */
  value: number | null
  low: number | null
  high: number | null
  /** Raw rate (successes / n), drawn as a hollow tick when it differs from the estimate. */
  raw?: number | null
  /** What the numbers are, for the accessible label, e.g. "LCM pill success". */
  label: string
  width?: number
}

/** A point with its 90 % credible-interval whisker on a 0-100 % scale (FRONTEND_PLAN §4.6). */
export function IntervalBar({ value, low, high, raw = null, label, width = 160 }: Props) {
  const h = 18
  const pad = 4
  const x = (p: number) => pad + p * (width - 2 * pad)
  const text =
    value === null
      ? `${label}: no estimate`
      : `${label}: ${pct(value)} (90% credible interval ${pct(low)} to ${pct(high)})`
  return (
    <svg
      width={width}
      height={h}
      role="img"
      aria-label={text}
      data-testid="interval-bar"
      className="block shrink-0"
    >
      <title>{text}</title>
      <line x1={x(0)} x2={x(1)} y1={h / 2} y2={h / 2} stroke="var(--border)" />
      {[0, 0.5, 1].map((t) => (
        <line key={t} x1={x(t)} x2={x(t)} y1={h / 2 - 3} y2={h / 2 + 3} stroke="var(--border)" />
      ))}
      {value !== null && low !== null && high !== null && (
        <>
          <rect
            x={x(low)}
            y={h / 2 - 3}
            width={Math.max(1, x(high) - x(low))}
            height={6}
            rx={3}
            fill="var(--accent)"
            opacity={0.3}
          />
          <line x1={x(low)} x2={x(low)} y1={h / 2 - 5} y2={h / 2 + 5} stroke="var(--accent)" />
          <line x1={x(high)} x2={x(high)} y1={h / 2 - 5} y2={h / 2 + 5} stroke="var(--accent)" />
          <circle cx={x(value)} cy={h / 2} r={4} fill="var(--accent)" />
        </>
      )}
      {raw !== null && value !== null && Math.abs(raw - value) > 0.005 && (
        <circle
          cx={x(raw)}
          cy={h / 2}
          r={3.5}
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth={1.2}
        />
      )}
    </svg>
  )
}
