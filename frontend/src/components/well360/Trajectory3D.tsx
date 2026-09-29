import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'

import { eventMeta, markerPath } from '../../lib/eventTypes'
import { formatNumber } from '../../lib/format/units'
import { niceTicks } from '../../lib/correlation'
import { bounds, viewport, VIEWS, type P3, type View } from '../../lib/trajectory3d'
import { Segmented } from '../ui/Segmented'

export interface Path3 {
  id: number
  name: string
  points: P3[]
  subject?: boolean
  assumed?: boolean
}

export interface Marker3 {
  key: string
  at: P3
  kind: 'top' | 'event'
  label: string
  eventType?: string
  verified?: boolean
}

const W = 820
const H = 560
type Preset = 'perspective' | 'plan' | 'section' | 'custom'

function presetOf(v: View): Preset {
  for (const k of ['perspective', 'plan', 'section'] as const)
    if (VIEWS[k].yaw === v.yaw && VIEWS[k].pitch === v.pitch) return k
  return 'custom'
}

/**
 * Orthographic 3D view of the well path with its offsets, formation tops and events.
 * Plain SVG (no WebGL): drag or use the arrow keys to turn it; Plan and Section are presets.
 */
export function Trajectory3D({
  paths,
  markers,
  onSelectEvent,
}: {
  paths: Path3[]
  markers: Marker3[]
  onSelectEvent?: (key: string) => void
}) {
  const [view, setView] = useState<View>(VIEWS.perspective)
  const drag = useRef<{ x: number; y: number; view: View } | null>(null)
  const all = useMemo(() => paths.flatMap((p) => p.points), [paths])
  const map = useMemo(() => viewport(all, W, H, 36), [all])
  const box = useMemo(() => bounds(all), [all])

  const turn = (dYaw: number, dPitch: number, from: View = view) =>
    setView({
      yaw: Math.round((((from.yaw + dYaw) % 360) + 360) % 360),
      pitch: Math.round(Math.min(90, Math.max(0, from.pitch + dPitch))),
    })
  const onDown = (e: PointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, view }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const d = drag.current
    if (d) turn((e.clientX - d.x) * 0.4, (e.clientY - d.y) * 0.3, d.view)
  }
  const onKey = (e: KeyboardEvent) => {
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-10, 0],
      ArrowRight: [10, 0],
      ArrowUp: [0, 5],
      ArrowDown: [0, -5],
    }
    const m = moves[e.key]
    if (!m) return
    e.preventDefault()
    turn(m[0], m[1])
  }

  // Wireframe box and a depth scale on one vertical edge give the eye its 3D cues.
  const lo = box.lo ?? { east: 0, north: 0, tvdss: 0 }
  const hi = box.hi ?? { east: 0, north: 0, tvdss: 0 }
  const corners: P3[] = []
  for (const e of [lo.east, hi.east])
    for (const n of [lo.north, hi.north])
      for (const t of [lo.tvdss, hi.tvdss]) corners.push({ east: e, north: n, tvdss: t })
  const edges: [number, number][] = [
    [0, 1],
    [2, 3],
    [4, 5],
    [6, 7], // verticals
    [0, 2],
    [2, 6],
    [6, 4],
    [4, 0], // top (shallow) face
    [1, 3],
    [3, 7],
    [7, 5],
    [5, 1], // bottom (deep) face
  ]
  const proj = corners.map((c) => map(c, view))
  const depthTicks = niceTicks(lo.tvdss, hi.tvdss, 6)
  const north = map(
    { east: lo.east, north: lo.north + (hi.north - lo.north || 1) * 0.25, tvdss: lo.tvdss },
    view,
  )
  const northFrom = map({ east: lo.east, north: lo.north, tvdss: lo.tvdss }, view)

  const line = (pts: P3[]) =>
    pts
      .map((p, i) => {
        const q = map(p, view)
        return `${i ? 'L' : 'M'} ${q.x.toFixed(1)} ${q.y.toFixed(1)}`
      })
      .join(' ')

  const ordered = [...paths].sort((a, b) => Number(Boolean(a.subject)) - Number(Boolean(b.subject)))
  const preset = presetOf(view)

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          label="Camera"
          options={[
            { id: 'perspective', label: '3D' },
            { id: 'plan', label: 'Plan' },
            { id: 'section', label: 'Section' },
          ]}
          value={preset === 'custom' ? 'perspective' : preset}
          onChange={(k) => setView(VIEWS[k])}
          testId="camera-presets"
        />
        <label className="flex items-center gap-2 text-xs text-muted">
          Turn
          <input
            type="range"
            min={0}
            max={359}
            value={view.yaw}
            onChange={(e) => setView((v) => ({ ...v, yaw: Number(e.target.value) }))}
            className="w-28 accent-[var(--accent)]"
            aria-label="Turn (degrees from north)"
          />
          <span className="num w-9">{view.yaw}°</span>
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          Tilt
          <input
            type="range"
            min={0}
            max={90}
            value={view.pitch}
            onChange={(e) => setView((v) => ({ ...v, pitch: Number(e.target.value) }))}
            className="w-24 accent-[var(--accent)]"
            aria-label="Tilt (0 = section, 90 = plan)"
          />
          <span className="num w-9">{view.pitch}°</span>
        </label>
        <span className="text-xs text-muted">Drag to turn · arrow keys when focused</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full cursor-grab touch-none rounded-xl border border-border bg-surface-2 select-none active:cursor-grabbing"
        role="group"
        aria-roledescription="3D view"
        aria-label={`3D well paths: ${paths.map((p) => p.name).join(', ')}. Turn ${view.yaw}°, tilt ${view.pitch}°.`}
        tabIndex={0}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
        onKeyDown={onKey}
        data-testid="trajectory-3d"
        data-yaw={view.yaw}
        data-pitch={view.pitch}
      >
        {edges.map(([a, b]) => (
          <line
            key={`${a}-${b}`}
            x1={proj[a]!.x}
            y1={proj[a]!.y}
            x2={proj[b]!.x}
            y2={proj[b]!.y}
            stroke="var(--border)"
            strokeDasharray={a % 2 || b % 2 ? '4 4' : undefined}
          />
        ))}
        {depthTicks.map((t) => {
          const q = map({ east: lo.east, north: lo.north, tvdss: t }, view)
          return (
            <g key={t}>
              <line x1={q.x - 5} x2={q.x} y1={q.y} y2={q.y} stroke="var(--text-muted)" />
              <text
                x={q.x - 8}
                y={q.y + 3}
                fontSize={10}
                textAnchor="end"
                fill="var(--text-muted)"
                className="num"
              >
                {formatNumber(t)}
              </text>
            </g>
          )
        })}
        <text x={12} y={18} fontSize={10} fill="var(--text-muted)">
          m TVDSS · box {formatNumber(hi.east - lo.east)} × {formatNumber(hi.north - lo.north)} m
        </text>
        {Math.hypot(north.x - northFrom.x, north.y - northFrom.y) > 10 && (
          <g>
            <line
              x1={northFrom.x}
              y1={northFrom.y}
              x2={north.x}
              y2={north.y}
              stroke="var(--accent-2)"
              strokeWidth={2}
              markerEnd="url(#arrow)"
            />
            <text
              x={north.x + 4}
              y={north.y - 4}
              fontSize={11}
              fontWeight={600}
              fill="var(--accent-2)"
            >
              N
            </text>
          </g>
        )}
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent-2)" />
          </marker>
        </defs>

        {ordered.map((p) => {
          // The subject is labelled at its wellhead; offsets at TD, where pad wells fan apart.
          const at = p.subject ? p.points[0] : p.points[p.points.length - 1]
          const head = at ? map(at, view) : null
          return (
            <g key={p.id} data-testid={p.subject ? 'path-subject' : 'path-offset'}>
              <path
                d={line(p.points)}
                fill="none"
                stroke={p.subject ? 'var(--accent)' : 'var(--text-muted)'}
                strokeWidth={p.subject ? 3.2 : 1.6}
                strokeOpacity={p.subject ? 1 : 0.75}
                strokeDasharray={p.assumed ? '6 4' : undefined}
                strokeLinecap="round"
              >
                <title>{`${p.name}${p.assumed ? ' (assumed trajectory)' : ''}`}</title>
              </path>
              {head && (
                <text
                  x={head.x}
                  y={p.subject ? head.y - 8 : head.y + 14}
                  fontSize={p.subject ? 12 : 10}
                  fontWeight={p.subject ? 600 : 400}
                  textAnchor="middle"
                  fill={p.subject ? 'var(--text)' : 'var(--text-muted)'}
                >
                  {p.name}
                </text>
              )}
            </g>
          )
        })}

        {markers.map((m) => {
          const q = map(m.at, view)
          if (m.kind === 'top')
            return (
              <g key={m.key} transform={`translate(${q.x}, ${q.y})`}>
                <title>{m.label}</title>
                <line x1={-7} x2={7} y1={0} y2={0} stroke="var(--text)" strokeWidth={1.5} />
                <text x={10} y={3} fontSize={9.5} fill="var(--text)">
                  {m.label.split(':')[0]}
                </text>
              </g>
            )
          const meta = eventMeta(m.eventType ?? '')
          return (
            <g
              key={m.key}
              transform={`translate(${q.x}, ${q.y})`}
              role="button"
              tabIndex={0}
              aria-label={m.label}
              className="cursor-pointer"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => onSelectEvent?.(m.key)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelectEvent?.(m.key)
                }
              }}
              data-testid="trajectory-event"
            >
              <title>{m.label}</title>
              <path
                d={markerPath(meta.shape, 6)}
                fill={meta.colorVar}
                stroke="var(--surface)"
                strokeWidth={1.2}
                strokeDasharray={m.verified ? undefined : '2 1.5'}
              />
            </g>
          )
        })}
      </svg>
    </div>
  )
}
