import {
  cellKey,
  formatHours,
  HEAT_STEPS,
  heatOpacity,
  heatStep,
  type HeatGrid,
} from '../../lib/analytics'
import { formatNumber } from '../../lib/format/units'

const CELL_W = 34
const CELL_H = 24
const LABEL_W = 116
const HEAD_H = 20

function short(name: string, max = 16): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name
}

/**
 * NPT hours per formation (rows) and year (columns): one accent hue, light → dark in five
 * steps, each cell labelled with its hours. Empty cells (no events that year) are outlined
 * only, never drawn as zero. Scrolls sideways on a phone; the legend reads the steps.
 */
export function NptHeatmap({ grid }: { grid: HeatGrid }) {
  const width = LABEL_W + grid.years.length * CELL_W
  const height = HEAD_H + grid.formations.length * CELL_H
  const stepMax = (s: number) => (grid.max * (s + 1)) / HEAT_STEPS
  const label = `NPT hours by formation and year: ${grid.formations.length} formations, ${grid.years.length} years, the largest cell ${formatHours(grid.max)}`
  return (
    <div className="space-y-2" data-testid="npt-heatmap">
      <div className="overflow-x-auto">
        <svg width={width} height={height} role="img" aria-label={label} className="block">
          <title>{label}</title>
          {grid.years.map((y, j) => (
            <text
              key={y}
              x={LABEL_W + j * CELL_W + CELL_W / 2}
              y={HEAD_H - 6}
              textAnchor="middle"
              fontSize={10}
              fill="var(--text-muted)"
              className="num"
            >
              {y === 'unknown' ? '?' : `’${y.slice(-2)}`}
              <title>{y}</title>
            </text>
          ))}
          {grid.formations.map((fm, i) => (
            <g key={fm} transform={`translate(0 ${HEAD_H + i * CELL_H})`}>
              <text
                x={LABEL_W - 6}
                y={CELL_H / 2 + 4}
                textAnchor="end"
                fontSize={11}
                fill="var(--text)"
              >
                {short(fm)}
                <title>{fm}</title>
              </text>
              {grid.years.map((y, j) => {
                const c = grid.cells.get(cellKey(fm, y))
                const step = c ? heatStep(c.hours, grid.max) : -1
                const x = LABEL_W + j * CELL_W
                return (
                  <g key={y} data-testid="heat-cell" data-step={step} data-key={cellKey(fm, y)}>
                    <rect
                      x={x + 1}
                      y={1}
                      width={CELL_W - 2}
                      height={CELL_H - 2}
                      rx={3}
                      fill={step >= 0 ? 'var(--accent)' : 'none'}
                      fillOpacity={heatOpacity(step)}
                      stroke={c ? 'none' : 'var(--border)'}
                    >
                      <title>
                        {c
                          ? `${fm}, ${y}: ${formatHours(c.hours)} NPT, ${c.events} events`
                          : `${fm}, ${y}: no events`}
                      </title>
                    </rect>
                    {c && (
                      <text
                        x={x + CELL_W / 2}
                        y={CELL_H / 2 + 3.5}
                        textAnchor="middle"
                        fontSize={9.5}
                        fill={step >= 3 ? 'var(--accent-contrast)' : 'var(--text)'}
                        className="num"
                        aria-hidden
                        pointerEvents="none"
                      >
                        {formatNumber(c.hours, c.hours < 10 ? 1 : 0)}
                      </text>
                    )}
                  </g>
                )
              })}
            </g>
          ))}
        </svg>
      </div>
      <ul
        className="flex flex-wrap items-center gap-3 text-xs text-muted"
        aria-label="Heatmap legend"
      >
        {Array.from({ length: HEAT_STEPS }, (_, s) => (
          <li key={s} className="flex items-center gap-1">
            <svg width={14} height={14} aria-hidden>
              <rect
                width={14}
                height={14}
                rx={3}
                fill="var(--accent)"
                fillOpacity={heatOpacity(s)}
              />
            </svg>
            <span className="num">
              {s === 0 ? '≤ ' : `${formatNumber(stepMax(s - 1), 0)}–`}
              {formatHours(stepMax(s), 0)}
            </span>
          </li>
        ))}
        <li className="flex items-center gap-1">
          <svg width={14} height={14} aria-hidden>
            <rect
              x={0.5}
              y={0.5}
              width={13}
              height={13}
              rx={3}
              fill="none"
              stroke="var(--border)"
            />
          </svg>
          no events
        </li>
      </ul>
    </div>
  )
}
