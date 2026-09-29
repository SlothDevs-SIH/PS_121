import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react'

import { eventMeta } from '../../lib/eventTypes'
import { trend, type Trend } from '../../lib/liveView'
import { pct } from '../../lib/risk'

const TREND_ICON: Record<Trend, typeof ArrowRight> = {
  up: ArrowUpRight,
  down: ArrowDownRight,
  flat: ArrowRight,
}
const TREND_WORD: Record<Trend, string> = { up: 'rising', down: 'falling', flat: 'steady' }

interface Props {
  /** Latest classifier probability per event type. */
  scores: Record<string, number>
  thresholds: Record<string, number>
  /** Recent values per type (oldest first) for the trend arrow. */
  history?: Record<string, (number | null)[]>
}

/**
 * Classifier probabilities against each type's alert threshold (S7b). Trained on
 * SYNTHETIC data: the caption says so, and the numbers are probabilities of the event in
 * the next 30 min under that model, nothing more.
 */
export function RiskGauges({ scores, thresholds, history = {} }: Props) {
  const types = Object.keys(thresholds).length ? Object.keys(thresholds) : Object.keys(scores)
  if (types.length === 0)
    return (
      <p className="text-sm text-muted">
        No classifier scores yet (they start after 30 min of data).
      </p>
    )
  const sorted = [...types].sort((a, b) => (scores[b] ?? 0) - (scores[a] ?? 0))
  return (
    <ul className="space-y-2" data-testid="risk-gauges">
      {sorted.map((t) => {
        const p = scores[t]
        const thr = thresholds[t]
        const tr = trend(history[t] ?? [])
        const Icon = TREND_ICON[tr]
        const over = p !== undefined && thr !== undefined && p >= thr
        const m = eventMeta(t)
        return (
          <li
            key={t}
            className="grid grid-cols-[7.5rem_1fr_4.5rem] items-center gap-2 text-sm"
            data-testid="risk-gauge"
            data-type={t}
          >
            <span className="truncate" title={m.label}>
              {m.label}
            </span>
            <span
              className="relative block h-2.5 rounded-full bg-surface-2"
              role="meter"
              aria-label={`${m.label} probability`}
              aria-valuemin={0}
              aria-valuemax={1}
              aria-valuenow={p ?? 0}
              aria-valuetext={
                p === undefined
                  ? 'not scored yet'
                  : `${pct(p)}, alert threshold ${pct(thr)}, ${TREND_WORD[tr]}`
              }
            >
              <span
                className="absolute inset-y-0 left-0 rounded-full"
                style={{
                  width: `${Math.min(100, (p ?? 0) * 100)}%`,
                  background: over ? 'var(--danger)' : m.colorVar,
                }}
              />
              {thr !== undefined && (
                <span
                  className="absolute -inset-y-1 w-0.5 bg-text"
                  style={{ left: `${thr * 100}%` }}
                  title={`Alert threshold ${pct(thr)}`}
                />
              )}
            </span>
            <span
              className={`num inline-flex items-center justify-end gap-0.5 ${over ? 'font-semibold text-danger' : ''}`}
            >
              {p === undefined ? '—' : pct(p)}
              <Icon size={14} aria-hidden className="text-muted" />
            </span>
          </li>
        )
      })}
    </ul>
  )
}
