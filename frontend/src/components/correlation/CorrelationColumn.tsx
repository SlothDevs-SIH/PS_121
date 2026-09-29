import { memo, type KeyboardEvent } from 'react'

import type { CorrelationWell, EventMarker } from '../../lib/api/client'
import { eventMeta, markerPath, markerRadius } from '../../lib/eventTypes'
import {
  formatInches,
  formatMudWeight,
  formatNumber,
  type UnitSystem,
} from '../../lib/format/units'
import { COLUMN_WIDTH, TRACK, type TrackToggles } from '../../lib/correlation'
import { lithologyOf } from '../../lib/lithology'

const X_CASING = TRACK.fm + TRACK.gap
const X_MUD = X_CASING + TRACK.casing + TRACK.gap
const X_EVENTS = X_MUD + TRACK.mud + TRACK.gap

interface Props {
  well: CorrelationWell
  y: (v: number) => number
  height: number
  axisMin: number
  axisMax: number
  mw: [number, number]
  show: TrackToggles
  units: UnitSystem
  selectedEventId: number | null
  onSelectEvent: (well: CorrelationWell, e: EventMarker) => void
  onZoomTo: (lo: number, hi: number) => void
}

/** Spread markers that would overlap: alternate left/right within the event track. */
function layoutEvents(events: EventMarker[], y: (v: number) => number) {
  const placed: { e: EventMarker; cy: number; dx: number }[] = []
  const sorted = [...events]
    .filter((e) => e.aligned !== null)
    .sort((a, b) => a.aligned! - b.aligned!)
  for (const e of sorted) {
    const cy = y(e.aligned!)
    const near = placed.filter((p) => Math.abs(p.cy - cy) < 14).length
    const dx = near === 0 ? 0 : (near % 2 ? -1 : 1) * Math.ceil(near / 2) * 12
    placed.push({ e, cy, dx })
  }
  return placed
}

/** One well's depth tracks: formations, casing & cement, mud weight, events (static part). */
export const CorrelationColumn = memo(function CorrelationColumn({
  well,
  y,
  height,
  axisMin,
  axisMax,
  mw,
  show,
  units,
  selectedEventId,
  onSelectEvent,
  onZoomTo,
}: Props) {
  const t = well.tracks
  const bottom = well.td_aligned ?? axisMax
  const xMw = (v: number) => X_MUD + 4 + ((v - mw[0]) / (mw[1] - mw[0] || 1)) * (TRACK.mud - 8)
  const clip = `clip-${well.well_id}`
  const events = show.events ? layoutEvents(t.events, y) : []
  const key = (e: EventMarker) => (ev: KeyboardEvent) => {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault()
      onSelectEvent(well, e)
    }
  }

  return (
    <svg
      width={COLUMN_WIDTH}
      height={height}
      role="group"
      aria-label={`${well.name} depth tracks`}
      data-testid={`corr-column-${well.well_id}`}
      className="block overflow-visible"
    >
      <defs>
        <clipPath id={clip}>
          <rect x={-20} y={0} width={COLUMN_WIDTH + 40} height={height} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clip})`}>
        {/* Track backgrounds */}
        <rect x={0} y={0} width={TRACK.fm} height={height} fill="var(--surface-2)" opacity={0.5} />
        {show.mud && (
          <rect
            x={X_MUD}
            y={0}
            width={TRACK.mud}
            height={height}
            fill="var(--surface-2)"
            opacity={0.35}
          />
        )}

        {/* Formations with lithology fill; double-click zooms to the formation */}
        {t.formations.map((f) => {
          const y0 = y(f.top)
          const y1 = y(f.base ?? bottom)
          const h = Math.max(0, y1 - y0)
          const lith = lithologyOf(f.lithology)
          return (
            <g
              key={f.name}
              onDoubleClick={() => onZoomTo(f.top, f.base ?? bottom)}
              data-formation={f.name}
            >
              <title>
                {`${f.name}${f.lithology ? ` (${f.lithology})` : ''}: top ${formatNumber(f.top_tvdss_m)} m TVDSS${
                  f.base_tvdss_m !== null ? `, base ${formatNumber(f.base_tvdss_m)} m TVDSS` : ''
                } · double-click to zoom`}
              </title>
              <rect
                x={0}
                y={y0}
                width={TRACK.fm}
                height={h}
                fill={`var(--fm-${Math.min(9, f.strat_order)})`}
              />
              {lith !== 'none' && (
                <rect x={0} y={y0} width={TRACK.fm} height={h} fill={`url(#lith-${lith})`} />
              )}
              <line x1={0} x2={TRACK.fm} y1={y0} y2={y0} stroke="var(--border)" />
              {h > 16 && (
                <text x={4} y={y0 + 12} fontSize={10} fill="var(--text)" className="select-none">
                  {f.name.length > 13 ? `${f.name.slice(0, 12)}…` : f.name}
                </text>
              )}
            </g>
          )
        })}

        {/* Casing shoes (◣ with OD) and cement tops (TOC tick) */}
        {show.casing &&
          t.casing_shoes.map((c) =>
            c.aligned === null ? null : (
              <g key={`shoe-${c.casing_id}`} transform={`translate(${X_CASING}, ${y(c.aligned)})`}>
                <title>
                  {`${formatInches(c.od_in)} casing shoe at ${formatNumber(c.shoe_md_m ?? 0)} m MD${
                    c.shoe_tvdss_m !== null ? ` / ${formatNumber(c.shoe_tvdss_m)} m TVDSS` : ''
                  }${c.hole_size_in ? ` in ${formatInches(c.hole_size_in)} hole` : ''}${c.verified ? '' : ' (unverified)'}`}
                </title>
                <line
                  x1={2}
                  x2={2}
                  y1={-Math.min(40, y(c.aligned))}
                  y2={0}
                  stroke="var(--text-muted)"
                  strokeWidth={2}
                />
                <path
                  d="M 2 0 L 14 0 L 2 -11 Z"
                  fill="var(--text)"
                  stroke="var(--text)"
                  strokeDasharray={c.verified ? undefined : '2.5 1.5'}
                  strokeWidth={1.2}
                  fillOpacity={c.verified ? 0.9 : 0.45}
                />
                <text x={16} y={-2} fontSize={9} fill="var(--text)">
                  {formatInches(c.od_in)}
                </text>
              </g>
            ),
          )}
        {show.casing &&
          t.cement_tops.map((c) =>
            c.aligned === null ? null : (
              <g
                key={`toc-${c.cement_job_id}`}
                transform={`translate(${X_CASING}, ${y(c.aligned)})`}
              >
                <title>
                  {`Top of cement at ${formatNumber(c.toc_md_m ?? 0)} m MD${
                    c.returns ? `, ${c.returns} returns` : ''
                  }${c.verified ? '' : ' (unverified)'}`}
                </title>
                <line
                  x1={0}
                  x2={TRACK.casing - 4}
                  y1={0}
                  y2={0}
                  stroke={c.returns && c.returns !== 'full' ? 'var(--warn)' : 'var(--accent-2)'}
                  strokeWidth={2}
                  strokeDasharray={c.verified ? undefined : '3 2'}
                />
              </g>
            ),
          )}

        {/* Mud weight (solid) and ECD (dashed) as step curves on a shared SG scale */}
        {show.mud &&
          t.mud.map((m) => {
            const y0 = y(m.top ?? axisMin)
            const y1 = y(m.base ?? bottom)
            if (m.mw_sg === null || y1 <= y0) return null
            return (
              <g key={`mud-${m.mud_interval_id}`}>
                <title>
                  {`${m.mud_type ?? 'Mud'} ${formatMudWeight(m.mw_sg, units)}${
                    m.ecd_sg !== null ? `, ECD ${formatMudWeight(m.ecd_sg, units)}` : ''
                  } from ${formatNumber(m.md_from_m)} to ${formatNumber(m.md_to_m)} m MD${m.verified ? '' : ' (unverified)'}`}
                </title>
                <line
                  x1={xMw(m.mw_sg)}
                  x2={xMw(m.mw_sg)}
                  y1={y0}
                  y2={y1}
                  stroke="var(--accent)"
                  strokeWidth={2.5}
                  strokeDasharray={m.verified ? undefined : '5 3'}
                />
                <line
                  x1={X_MUD}
                  x2={xMw(m.mw_sg)}
                  y1={y0}
                  y2={y0}
                  stroke="var(--accent)"
                  strokeOpacity={0.5}
                />
                {m.ecd_sg !== null && (
                  <line
                    x1={xMw(m.ecd_sg)}
                    x2={xMw(m.ecd_sg)}
                    y1={y0}
                    y2={y1}
                    stroke="var(--info)"
                    strokeWidth={1.5}
                    strokeDasharray="2 3"
                  />
                )}
              </g>
            )
          })}

        {/* TD line */}
        {well.td_aligned !== null && (
          <g>
            <line
              x1={0}
              x2={COLUMN_WIDTH}
              y1={y(well.td_aligned)}
              y2={y(well.td_aligned)}
              stroke="var(--text-muted)"
              strokeDasharray="4 3"
            />
            <text
              x={COLUMN_WIDTH - 2}
              y={y(well.td_aligned) - 3}
              fontSize={9}
              textAnchor="end"
              fill="var(--text-muted)"
            >
              TD
            </text>
          </g>
        )}

        {/* Events: shape + colour + code by type, size by NPT, dashed when unverified */}
        {events.map(({ e, cy, dx }) => {
          const meta = eventMeta(e.event_type)
          const r = markerRadius(e.npt_hours)
          const selected = e.event_id === selectedEventId
          const label = `${meta.label}${e.severity ? `, ${e.severity} severity` : ''} in ${well.name}${
            e.md_m !== null ? ` at ${formatNumber(e.md_m)} m MD` : ''
          }${e.tvdss_m !== null ? ` / ${formatNumber(e.tvdss_m)} m TVDSS` : ''}${
            e.npt_hours ? `, ${formatNumber(e.npt_hours, 1)} h NPT` : ''
          }${e.verified ? '' : ' (unverified)'}`
          return (
            <g
              key={`ev-${e.event_id}`}
              transform={`translate(${X_EVENTS + TRACK.events / 2 + dx}, ${cy})`}
              role="button"
              tabIndex={0}
              aria-label={label}
              aria-pressed={selected}
              data-testid="event-marker"
              data-event-type={e.event_type}
              className="cursor-pointer outline-none [&:focus-visible>circle.ring]:opacity-100"
              onClick={() => onSelectEvent(well, e)}
              onKeyDown={key(e)}
            >
              <title>{label}</title>
              <circle
                className="ring"
                r={r + 4}
                fill="none"
                stroke="var(--accent)"
                strokeWidth={2}
                opacity={selected ? 1 : 0}
              />
              <path
                d={markerPath(meta.shape, r)}
                fill={meta.colorVar}
                stroke={e.severity === 'high' ? 'var(--text)' : 'var(--surface)'}
                strokeWidth={e.severity === 'high' ? 1.6 : 1}
                strokeDasharray={e.verified ? undefined : '2 1.5'}
              />
            </g>
          )
        })}
      </g>
    </svg>
  )
})
