import { ArrowRight, Crosshair, Eye, EyeOff } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { lazy, Suspense, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useTheme } from '../app/themeContext'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { DataTable, type Column } from '../components/ui/DataTable'
import { SkeletonBlock } from '../components/ui/Skeleton'
import type { OffsetOut, ProximityMode } from '../lib/api/client'
import { useOffsets, useTrajectory, useWell, useWells } from '../lib/api/hooks'
import { cn } from '../lib/cn'
import { formatBearing, formatDepth, formatDistance } from '../lib/format/units'
import { panelSlide } from '../lib/motion'
import { FLUID_ORDER, FLUIDS, fluidOf, matchesFilter, type FluidType } from '../lib/wellTypes'
import { useUiStore } from '../stores/ui'

const WellMap = lazy(() => import('../components/map/WellMap'))

const MODES: { id: ProximityMode; label: string; part?: string }[] = [
  { id: 'SURFACE', label: 'Surface' },
  { id: 'AT_FORMATION', label: 'At formation', part: 'Part 3' },
  { id: 'CLOSEST_APPROACH', label: 'Closest approach', part: 'Part 3' },
]

function clampRadius(v: number): number {
  return Number.isFinite(v) ? Math.min(20, Math.max(1, v)) : 5
}

function FluidDot({ fluid }: { fluid: string | null | undefined }) {
  const f = fluidOf(fluid)
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span
        aria-hidden
        className="size-2 rounded-full"
        style={{ background: f ? FLUIDS[f].colorVar : 'var(--text-muted)' }}
      />
      {f ? FLUIDS[f].label : '—'}
    </span>
  )
}

export function WellMapPage() {
  const { units } = useTheme()
  const [params, setParams] = useSearchParams()
  const wellType = useUiStore((s) => s.wellType)
  const setWellType = useUiStore((s) => s.setWellType)
  const setForceRail = useUiStore((s) => s.setForceRail)
  const [hidden, setHidden] = useState<Set<FluidType>>(new Set())
  const [panelOpen, setPanelOpen] = useState(true)
  const wells = useWells()
  const items = useMemo(() => wells.data?.items ?? [], [wells.data])

  // More map: the sidebar folds to a rail while this page is open (FRONTEND_SPEC §4.3).
  useEffect(() => {
    setForceRail(true)
    return () => setForceRail(false)
  }, [setForceRail])

  // Sidebar "Oil / Gas / Water wells" links arrive with ?type=.
  const typeParam = params.get('type')
  useEffect(() => {
    if (typeParam === 'oil' || typeParam === 'gas' || typeParam === 'water') setWellType(typeParam)
  }, [typeParam, setWellType])

  const defaultWell = items.find((w) => w.status === 'planned') ?? items[0]
  const wellId = Number(params.get('well')) || defaultWell?.id || null
  const radiusParam = clampRadius(Number(params.get('r') ?? 5))
  const mode: ProximityMode = 'SURFACE' // other modes land with the Part 3 map work
  const [radiusDraft, setRadiusDraft] = useState<number | null>(null)
  const radiusKm = useDeferredValue(radiusDraft ?? radiusParam)

  const well = useWell(wellId)
  const trajectory = useTrajectory(wellId)
  const offsets = useOffsets(wellId, radiusKm, mode)

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) next.set(k, v)
    setParams(next, { replace: true })
  }
  const select = (id: number) => {
    setPanelOpen(true)
    update({ well: String(id) })
  }

  const offsetIds = useMemo(
    () => new Set(offsets.data?.offsets.map((o) => o.well_id)),
    [offsets.data],
  )
  const mapWells = useMemo(
    () =>
      items
        .filter((w) => {
          const f = fluidOf(w.fluid_type)
          return w.id === wellId || !f || !hidden.has(f)
        })
        .map((w) => ({
          id: w.id,
          name: w.name,
          lat: w.lat,
          lon: w.lon,
          status: w.status,
          fluid: w.fluid_type ?? null,
          role:
            w.id === wellId
              ? ('active' as const)
              : offsetIds.has(w.id)
                ? ('offset' as const)
                : ('other' as const),
          dimmed: w.id !== wellId && !matchesFilter(w.fluid_type, wellType),
        })),
    [items, wellId, offsetIds, hidden, wellType],
  )

  const counts = useMemo(() => {
    const c: Record<FluidType, number> = { oil: 0, gas: 0, water: 0 }
    for (const w of items) {
      const f = fluidOf(w.fluid_type)
      if (f) c[f] += 1
    }
    return c
  }, [items])

  const columns: Column<OffsetOut>[] = [
    {
      key: 'name',
      header: 'Well',
      render: (o) => <span className="font-medium whitespace-nowrap">{o.name}</span>,
      sortValue: (o) => o.name,
    },
    {
      key: 'distance',
      header: 'Distance',
      render: (o) => <span className="num whitespace-nowrap">{formatDistance(o.distance_m)}</span>,
      sortValue: (o) => o.distance_m,
      align: 'right',
    },
    {
      key: 'bearing',
      header: 'Bearing',
      render: (o) => <span className="num whitespace-nowrap">{formatBearing(o.bearing_deg)}</span>,
      align: 'right',
    },
    {
      key: 'fluid',
      header: 'Fluid',
      render: (o) => <FluidDot fluid={o.fluid_type} />,
      sortValue: (o) => o.fluid_type,
    },
    { key: 'status', header: 'Status', render: (o) => o.status, sortValue: (o) => o.status },
    {
      key: 'td',
      header: 'TD',
      render: (o) => (
        <span className="num whitespace-nowrap">
          {o.td_md_m ? formatDepth(o.td_md_m, units, 'MD') : '—'}
        </span>
      ),
      sortValue: (o) => o.td_md_m,
      align: 'right',
    },
  ]

  const anySynthetic = items.some((w) => w.synthetic)
  const shownOffsets = offsets.data?.offsets ?? []

  return (
    <div className="-m-4 flex flex-col md:-m-6">
      <div className="flex flex-wrap items-center gap-2 px-4 pt-4 pb-3 md:px-6">
        <h1 className="text-2xl font-semibold tracking-tight text-text">Map Explorer</h1>
        {anySynthetic && <SyntheticBadge />}
        <span className="text-sm text-muted">
          Offset wells around the active well · click any well to fly to it
        </span>
      </div>
      {wells.isError && <p className="px-6 text-danger">Wells could not be loaded.</p>}
      {wells.data && items.length === 0 && (
        <p className="px-6 text-muted">
          No wells yet. Load the synthetic field with <code>make seed</code>.
        </p>
      )}

      <div className="grid min-h-0 gap-0 border-t border-border lg:h-[calc(100dvh-8.5rem)] lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="relative h-[60vh] min-h-[24rem] min-w-0 lg:h-full" data-testid="map-panel">
          <Suspense fallback={<SkeletonBlock className="h-full w-full rounded-none" />}>
            <WellMap
              wells={mapWells}
              active={well.data ? { lat: well.data.lat, lon: well.data.lon } : null}
              radiusKm={radiusKm}
              path={trajectory.data?.path ?? []}
              onSelect={select}
              className="rounded-none"
            />
          </Suspense>

          {/* Radius control, floating top-left over the map. */}
          <div className="absolute top-3 left-3 z-(--z-map-overlay) w-[min(20rem,calc(100%-1.5rem))] rounded-xl border border-border bg-glass p-3 shadow-card backdrop-blur-md">
            <label className="mb-1 block text-xs font-medium text-muted" htmlFor="well-select">
              Active well
            </label>
            <select
              id="well-select"
              className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-text"
              value={wellId ?? ''}
              onChange={(e) => select(Number(e.target.value))}
            >
              {items.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} ({w.status})
                </option>
              ))}
            </select>
            <label
              className="mt-3 mb-1 flex items-center justify-between text-xs font-medium text-muted"
              htmlFor="radius"
            >
              <span>
                Radius:{' '}
                <span className="num text-text" data-testid="radius-value">
                  {radiusDraft ?? radiusParam}
                </span>{' '}
                km
              </span>
              <Crosshair size={14} aria-hidden />
            </label>
            <input
              id="radius"
              type="range"
              min={1}
              max={20}
              step={0.5}
              value={radiusDraft ?? radiusParam}
              onChange={(e) => setRadiusDraft(Number(e.target.value))}
              onPointerUp={() => radiusDraft !== null && update({ r: String(radiusDraft) })}
              onKeyUp={() => radiusDraft !== null && update({ r: String(radiusDraft) })}
              className="w-full accent-[var(--accent)]"
            />
            <fieldset className="mt-2">
              <legend className="mb-1 text-xs font-medium text-muted">Distance measured</legend>
              <div className="flex flex-wrap gap-1" role="radiogroup">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="radio"
                    aria-checked={mode === m.id}
                    disabled={Boolean(m.part)}
                    title={
                      m.part ? `On the map in ${m.part} (the API already supports it)` : undefined
                    }
                    className={cn(
                      'rounded-md border border-border px-2 py-0.5 text-xs',
                      mode === m.id ? 'bg-accent text-accent-contrast' : 'text-text',
                      m.part && 'opacity-55',
                    )}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>

          {/* Legend with per-fluid visibility, bottom-left. */}
          <div
            className="absolute bottom-3 left-3 z-(--z-map-overlay) flex flex-wrap items-center gap-1 rounded-xl border border-border bg-glass p-1.5 shadow-card backdrop-blur-md"
            data-testid="well-legend"
          >
            {FLUID_ORDER.map((f) => {
              const off = hidden.has(f)
              const meta = FLUIDS[f]
              return (
                <button
                  key={f}
                  type="button"
                  aria-pressed={!off}
                  aria-label={`${off ? 'Show' : 'Hide'} ${meta.plural.toLowerCase()}`}
                  onClick={() =>
                    setHidden((h) => {
                      const n = new Set(h)
                      if (n.has(f)) n.delete(f)
                      else n.add(f)
                      return n
                    })
                  }
                  className={cn(
                    'flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs',
                    off ? 'text-muted line-through opacity-60' : 'text-text hover:bg-surface-2',
                  )}
                >
                  <span
                    aria-hidden
                    className="size-2.5 rounded-full"
                    style={{ background: meta.colorVar }}
                  />
                  {meta.label}
                  <span className="num text-muted">{counts[f]}</span>
                  {off ? <EyeOff size={12} aria-hidden /> : <Eye size={12} aria-hidden />}
                </button>
              )
            })}
            <span className="flex items-center gap-1.5 px-2 text-xs text-muted">
              <span aria-hidden className="size-2.5 rounded-full ring-2 ring-accent-2" />
              drilling (pulsing)
            </span>
          </div>
        </div>

        <AnimatePresence initial={false}>
          {panelOpen && (
            <motion.aside
              key="panel"
              {...panelSlide}
              className="flex min-h-0 w-full flex-col gap-3 overflow-y-auto border-l border-border bg-surface p-4 lg:w-[27rem]"
              aria-label="Selected well"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs text-muted">Selected well</p>
                  <h2 className="truncate text-lg font-semibold text-text">
                    {well.data?.name ?? '…'}
                  </h2>
                </div>
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2"
                  onClick={() => setPanelOpen(false)}
                >
                  Hide
                </button>
              </div>
              {well.data ? (
                <>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="neutral">
                      <FluidDot fluid={well.data.fluid_type} />
                    </Badge>
                    <Badge tone={well.data.status === 'drilling' ? 'warn' : 'neutral'}>
                      {well.data.status}
                    </Badge>
                    {well.data.synthetic && <SyntheticBadge label="SYNTHETIC" />}
                  </div>
                  <p className="text-sm text-muted" data-testid="active-well-summary">
                    {well.data.status} · {well.data.profile ?? '—'} profile
                    {well.data.td_md_m
                      ? ` · TD ${formatDepth(well.data.td_md_m, units, 'MD')}`
                      : ''}{' '}
                    · data quality {Math.round(well.data.data_quality.score * 100)}%
                  </p>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    {[
                      ['Events', Object.values(well.data.event_counts).reduce((a, b) => a + b, 0)],
                      ['Documents', well.data.documents.total],
                      ['Casing strings', well.data.casing.length],
                    ].map(([k, v]) => (
                      <div key={k} className="rounded-lg bg-surface-2 p-2">
                        <div className="num text-lg font-semibold text-text">{v}</div>
                        <div className="text-[0.7rem] text-muted">{k}</div>
                      </div>
                    ))}
                  </div>
                  <Link
                    to={`/wells/${well.data.id}`}
                    className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
                  >
                    Well 360 (Part 3) <ArrowRight size={14} aria-hidden />
                  </Link>
                </>
              ) : (
                <SkeletonBlock className="h-24 w-full" />
              )}

              <div className="mt-1 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text">Offset wells</h3>
                {offsets.data && (
                  <Badge tone="info" data-testid="offset-count">
                    {shownOffsets.length} within {radiusKm} km
                  </Badge>
                )}
              </div>
              {offsets.isError && (
                <p className="text-sm text-danger">Offsets could not be loaded.</p>
              )}
              {offsets.data ? (
                <DataTable
                  testId="offset-table"
                  caption="Offset wells"
                  columns={columns}
                  rows={shownOffsets}
                  rowKey={(o) => o.well_id}
                  initialSort={{ key: 'distance', dir: 'asc' }}
                  onRowClick={(o) => select(o.well_id)}
                  empty={`No offset wells within ${radiusKm} km — widen the radius.`}
                />
              ) : (
                <SkeletonBlock className="h-40 w-full" />
              )}
              <p className="text-xs text-muted">{offsets.data?.distance_label}</p>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
