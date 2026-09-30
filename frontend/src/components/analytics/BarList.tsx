import type { ReactNode } from 'react'

import { linearScale } from '../../lib/analytics'
import { formatNumber } from '../../lib/format/units'

const W = 1000

export interface BarDatum {
  key: string
  label: string
  value: number
  /** The value as read aloud and printed at the bar's end, e.g. "412.5 h". */
  valueText: string
  /** Secondary text after the value (events, wells…). */
  detail?: string
  /** Colour of an entity (event types); the accent otherwise. */
  colorVar?: string
  /** Shape marker beside the label, so colour is never the only cue. */
  icon?: ReactNode
}

interface Props {
  data: BarDatum[]
  /** What the bars are, for the list's accessible name. */
  label: string
  tickFormat?: (v: number) => string
  testId?: string
}

/**
 * Horizontal bars in the given order (ADR-F16/F18: React SVG on our own linear scale). The
 * label and value of every bar are text in the list itself, so the list is its own text
 * alternative; the SVG is decoration. Each bar stretches with its row, down to a phone.
 */
export function BarList({ data, label, tickFormat = (v) => formatNumber(v), testId }: Props) {
  const scale = linearScale(Math.max(0, ...data.map((d) => d.value)), 0, W)
  const pos = (v: number) => `${(scale.at(v) / W) * 100}%`
  return (
    <div className="min-w-0" data-testid={testId}>
      <div className="grid grid-cols-[minmax(0,8rem)_1fr] gap-2 sm:grid-cols-[minmax(0,10rem)_1fr]">
        <span aria-hidden />
        <div aria-hidden className="relative h-4 text-[0.65rem] text-muted">
          {scale.ticks.map((t, i) => (
            <span
              key={t}
              className="num absolute top-0 whitespace-nowrap"
              style={{
                left: pos(t),
                transform:
                  i === 0
                    ? undefined
                    : i === scale.ticks.length - 1
                      ? 'translateX(-100%)'
                      : 'translateX(-50%)',
              }}
            >
              {tickFormat(t)}
            </span>
          ))}
        </div>
      </div>
      <ul aria-label={label} className="space-y-1">
        {data.map((d) => (
          <li
            key={d.key}
            className="grid grid-cols-[minmax(0,8rem)_1fr] items-center gap-2 text-sm sm:grid-cols-[minmax(0,10rem)_1fr]"
            data-testid="bar-row"
            data-key={d.key}
          >
            <span className="flex min-w-0 items-center gap-1.5" title={d.label}>
              {d.icon}
              <span className="truncate text-text">{d.label}</span>
            </span>
            <span className="flex min-w-0 items-center gap-2">
              <svg
                viewBox={`0 0 ${W} 16`}
                preserveAspectRatio="none"
                width="100%"
                height={16}
                aria-hidden
                className="block min-w-0 flex-1"
              >
                {scale.ticks.map((t) => (
                  <line
                    key={t}
                    x1={scale.at(t)}
                    x2={scale.at(t)}
                    y1={0}
                    y2={16}
                    stroke="var(--border)"
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
                <rect
                  x={0}
                  y={2}
                  width={Math.max(d.value > 0 ? 3 : 0, scale.at(d.value))}
                  height={12}
                  fill={d.colorVar ?? 'var(--accent)'}
                >
                  <title>{`${d.label}: ${d.valueText}${d.detail ? ` · ${d.detail}` : ''}`}</title>
                </rect>
              </svg>
              <span className="num shrink-0 text-xs whitespace-nowrap text-text">
                {d.valueText}
                {d.detail && <span className="hidden text-muted sm:inline"> · {d.detail}</span>}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
