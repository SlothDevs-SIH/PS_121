import type { EventSummary, WellDetail } from '../../lib/api/client'
import { niceTicks } from '../../lib/correlation'
import { eventMeta, markerPath, markerRadius } from '../../lib/eventTypes'
import {
  formatInches,
  formatMudWeight,
  formatNumber,
  type UnitSystem,
} from '../../lib/format/units'

const H = 560
const COL = { axis: 46, fm: 96, hole: 132, mw: 118, events: 44 }
const X_FM = COL.axis
const X_HOLE = X_FM + COL.fm + 6
const X_MW = X_HOLE + COL.hole + 6
const X_EV = X_MW + COL.mw + 6
const WIDTH = X_EV + COL.events
const MAX_HOLE_IN = 26

/**
 * Wellbore sketch on one MD axis: formations, hole sections, casing strings with their shoes
 * and cement, the mud-weight programme, and events. Unverified values are dashed (P7).
 */
export function WellSchematic({
  well,
  events,
  units,
  onSelectEvent,
}: {
  well: WellDetail
  events: EventSummary[]
  units: UnitSystem
  onSelectEvent?: (id: number) => void
}) {
  const tdCandidates = [
    well.td_md_m ?? 0,
    ...well.mud.map((m) => m.md_to_m),
    ...well.casing.map((c) => c.shoe_md_m ?? 0),
    ...well.formation_tops.map((t) => t.top_md_m),
  ]
  const td = Math.max(100, ...tdCandidates)
  const y = (md: number) => 14 + (md / td) * (H - 28)
  const cx = X_HOLE + COL.hole / 2
  const half = (inches: number) => (inches / MAX_HOLE_IN) * (COL.hole / 2 - 4)
  const mws = well.mud.flatMap((m) => [m.mw_sg, m.ecd_sg]).filter((v): v is number => v !== null)
  const mwLo = mws.length ? Math.min(...mws) - 0.05 : 1
  const mwHi = mws.length ? Math.max(...mws) + 0.05 : 2
  const xMw = (v: number) => X_MW + 6 + ((v - mwLo) / (mwHi - mwLo || 1)) * (COL.mw - 12)
  const tops = [...well.formation_tops].sort((a, b) => a.top_md_m - b.top_md_m)
  const casing = [...well.casing].sort((a, b) => (b.od_in ?? 0) - (a.od_in ?? 0))

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${H}`}
      className="h-auto w-full max-w-[34rem]"
      role="group"
      aria-label={`Wellbore sketch of ${well.name} against measured depth`}
      data-testid="well-schematic"
    >
      <text x={X_FM} y={10} fontSize={9} fill="var(--text-muted)">
        FORMATION
      </text>
      <text x={X_HOLE} y={10} fontSize={9} fill="var(--text-muted)">
        HOLE · CASING · CEMENT
      </text>
      <text x={X_MW} y={10} fontSize={9} fill="var(--text-muted)">
        MW {formatMudWeight(mwLo, units)}–{formatMudWeight(mwHi, units)}
      </text>

      {niceTicks(0, td, 8).map((t) => (
        <g key={t}>
          <line x1={COL.axis - 5} x2={COL.axis} y1={y(t)} y2={y(t)} stroke="var(--text-muted)" />
          <text
            x={COL.axis - 7}
            y={y(t) + 3}
            fontSize={9}
            textAnchor="end"
            fill="var(--text-muted)"
            className="num"
          >
            {formatNumber(units === 'metric' ? t : t / 0.3048)}
          </text>
        </g>
      ))}
      <text x={2} y={H - 2} fontSize={9} fill="var(--text-muted)">
        {units === 'metric' ? 'm' : 'ft'} MD
      </text>

      {tops.map((t, i) => {
        const next = tops[i + 1]?.top_md_m ?? td
        return (
          <g key={t.formation}>
            <title>{`${t.formation}: top ${formatNumber(t.top_md_m)} m MD / ${formatNumber(t.top_tvdss_m)} m TVDSS`}</title>
            <rect
              x={X_FM}
              y={y(t.top_md_m)}
              width={COL.fm}
              height={Math.max(0, y(next) - y(t.top_md_m))}
              fill={`var(--fm-${Math.min(9, t.strat_order)})`}
            />
            <line
              x1={X_FM}
              x2={X_MW + COL.mw}
              y1={y(t.top_md_m)}
              y2={y(t.top_md_m)}
              stroke="var(--border)"
              strokeDasharray="2 3"
            />
            {y(next) - y(t.top_md_m) > 14 && (
              <text x={X_FM + 4} y={y(t.top_md_m) + 11} fontSize={9.5} fill="var(--text)">
                {t.formation}
              </text>
            )}
          </g>
        )
      })}

      {/* Open hole by section, from the mud programme */}
      {well.mud.map((m) =>
        m.hole_size_in ? (
          <rect
            key={`hole-${m.id}`}
            x={cx - half(m.hole_size_in)}
            y={y(m.md_from_m)}
            width={half(m.hole_size_in) * 2}
            height={Math.max(0, y(m.md_to_m) - y(m.md_from_m))}
            fill="var(--surface-2)"
            stroke="var(--border)"
          >
            <title>{`${formatInches(m.hole_size_in)} hole, ${formatNumber(m.md_from_m)}–${formatNumber(m.md_to_m)} m MD`}</title>
          </rect>
        ) : null,
      )}

      {/* Cement between casing and hole wall, then the casing strings */}
      {casing.map((c) => {
        const od = c.od_in
        const shoe = c.shoe_md_m
        if (!od || !shoe) return null
        const hole = c.hole_size_in ?? od + 2
        return c.cement.map((j) => {
          const toc = j.toc_md_m
          if (toc === null || toc >= shoe) return null
          return (
            <g key={`cmt-${j.id}`} opacity={0.85}>
              <title>{`Cement ${formatNumber(toc)}–${formatNumber(shoe)} m MD${j.returns ? `, ${j.returns} returns` : ''}${j.verified ? '' : ' (unverified)'}`}</title>
              {[-1, 1].map((side) => (
                <rect
                  key={side}
                  x={side < 0 ? cx - half(hole) : cx + half(od)}
                  y={y(toc)}
                  width={Math.max(1.5, half(hole) - half(od))}
                  height={Math.max(0, y(shoe) - y(toc))}
                  fill={j.returns && j.returns !== 'full' ? 'var(--warn)' : 'var(--text-muted)'}
                  fillOpacity={0.45}
                  stroke={j.verified ? 'none' : 'var(--text-muted)'}
                  strokeDasharray="2 2"
                />
              ))}
            </g>
          )
        })
      })}
      {casing.map((c) =>
        c.od_in && c.shoe_md_m ? (
          <g key={`csg-${c.id}`}>
            <title>{`${formatInches(c.od_in)} casing to ${formatNumber(c.shoe_md_m)} m MD${c.shoe_tvdss_m !== null ? ` (${formatNumber(c.shoe_tvdss_m)} m TVDSS)` : ''}${c.verified ? '' : ' (unverified)'}`}</title>
            {[-1, 1].map((side) => (
              <line
                key={side}
                x1={cx + side * half(c.od_in!)}
                x2={cx + side * half(c.od_in!)}
                y1={y(0)}
                y2={y(c.shoe_md_m!)}
                stroke="var(--text)"
                strokeWidth={2}
                strokeDasharray={c.verified ? undefined : '6 3'}
              />
            ))}
            <path
              d={`M ${cx - half(c.od_in)} ${y(c.shoe_md_m)} l -7 0 l 7 -8 Z`}
              fill="var(--text)"
            />
            <path
              d={`M ${cx + half(c.od_in)} ${y(c.shoe_md_m)} l 7 0 l -7 -8 Z`}
              fill="var(--text)"
            />
            <text
              x={cx + half(c.od_in) + 10}
              y={y(c.shoe_md_m) - 2}
              fontSize={9.5}
              fill="var(--text)"
            >
              {formatInches(c.od_in)}
            </text>
          </g>
        ) : null,
      )}

      {/* Mud weight programme */}
      <rect x={X_MW} y={14} width={COL.mw} height={H - 28} fill="var(--surface-2)" opacity={0.4} />
      {well.mud.map((m) =>
        m.mw_sg !== null ? (
          <g key={`mw-${m.id}`}>
            <title>{`${m.mud_type ?? 'Mud'} ${formatMudWeight(m.mw_sg, units)}, ${formatNumber(m.md_from_m)}–${formatNumber(m.md_to_m)} m MD${m.verified ? '' : ' (unverified)'}`}</title>
            <line
              x1={xMw(m.mw_sg)}
              x2={xMw(m.mw_sg)}
              y1={y(m.md_from_m)}
              y2={y(m.md_to_m)}
              stroke="var(--accent)"
              strokeWidth={2.5}
              strokeDasharray={m.verified ? undefined : '5 3'}
            />
            <text
              x={xMw(m.mw_sg) + 4}
              y={y((m.md_from_m + m.md_to_m) / 2)}
              fontSize={9}
              fill="var(--text)"
            >
              {formatMudWeight(m.mw_sg, units)}
            </text>
            {m.ecd_sg !== null && (
              <line
                x1={xMw(m.ecd_sg)}
                x2={xMw(m.ecd_sg)}
                y1={y(m.md_from_m)}
                y2={y(m.md_to_m)}
                stroke="var(--info)"
                strokeDasharray="2 3"
              />
            )}
          </g>
        ) : null,
      )}

      {/* Events by MD */}
      {events
        .filter((e) => e.md_m !== null)
        .map((e) => {
          const meta = eventMeta(e.event_type)
          return (
            <g
              key={e.id}
              transform={`translate(${X_EV + COL.events / 2}, ${y(e.md_m!)})`}
              role="button"
              tabIndex={0}
              aria-label={`${meta.label} at ${formatNumber(e.md_m!)} m MD`}
              className="cursor-pointer"
              onClick={() => onSelectEvent?.(e.id)}
              onKeyDown={(ev) => {
                if (ev.key === 'Enter' || ev.key === ' ') {
                  ev.preventDefault()
                  onSelectEvent?.(e.id)
                }
              }}
            >
              <title>{`${meta.label} at ${formatNumber(e.md_m!)} m MD${e.npt_hours ? `, ${formatNumber(e.npt_hours, 1)} h NPT` : ''}`}</title>
              <path
                d={markerPath(meta.shape, markerRadius(e.npt_hours))}
                fill={meta.colorVar}
                stroke="var(--surface)"
                strokeDasharray={e.verified ? undefined : '2 1.5'}
              />
            </g>
          )
        })}
      {well.td_md_m !== null && (
        <g>
          <line
            x1={X_FM}
            x2={WIDTH}
            y1={y(well.td_md_m)}
            y2={y(well.td_md_m)}
            stroke="var(--text-muted)"
            strokeDasharray="4 3"
          />
          <text
            x={WIDTH - 2}
            y={y(well.td_md_m) - 3}
            fontSize={9}
            textAnchor="end"
            fill="var(--text-muted)"
          >
            TD {formatNumber(well.td_md_m)} m MD
          </text>
        </g>
      )}
    </svg>
  )
}
