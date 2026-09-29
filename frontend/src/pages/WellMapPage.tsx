import { ArrowRight, Crosshair, Eye, EyeOff } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { lazy, Suspense, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useTheme } from '../app/themeContext'
import { RiskCurve } from '../components/risk/RiskCurve'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { DataTable, type Column } from '../components/ui/DataTable'
import { SkeletonBlock } from '../components/ui/Skeleton'
import type { OffsetOut, ProximityMode } from '../lib/api/client'
import { useOffsets, useRiskProfile, useTrajectory, useWell, useWells } from '../lib/api/hooks'
import { cn } from '../lib/cn'
import { formatBearing, formatDepth, formatDistance } from '../lib/format/units'
import { panelSlide } from '../lib/motion'
import { FLUID_ORDER, FLUIDS, fluidOf, matchesFilter, type FluidType } from '../lib/wellTypes'
import { useUiStore } from '../stores/ui'

const WellMap = lazy(() => import('../components/map/WellMap'))

const MODES: { id: ProximityMode; label: string; hint: string }[] = [
  { id: 'SURFACE', label: 'Surface', hint: 'Wellhead to wellhead' },
  {
    id: 'AT_FORMATION',
    label: 'At formation',
    hint: 'Between the points where both wells enter the chosen formation',
  },
  {
    id: 'CLOSEST_APPROACH',
    label: 'Closest approach',
    hint: 'Closest 3D distance between the two well paths',
  },
]

function parseMode(raw: string | null): ProximityMode {
  return raw === 'AT_FORMATION' || raw === 'CLOSEST_APPROACH' ? raw : 'SURFACE'
}

function num(raw: string | null): number | null {
  if (raw === null || raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

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
  const mode = parseMode(params.get('mode'))
  const [radiusDraft, setRadiusDraft] = useState<number | null>(null)
  const radiusKm = useDeferredValue(radiusDraft ?? radiusParam)

  const well = useWell(wellId)
  const risk = useRiskProfile(wellId)
  const trajectory = useTrajectory(wellId)
  const tops = well.data?.formation_tops ?? []
  const fmParam = params.get('fm')
  const formation =
    mode === 'AT_FORMATION'
      ? (tops.find((t) => t.formation === fmParam)?.formation ??
        tops[Math.floor(tops.length / 2)]?.formation ??
        null)
      : null
  const tvdssFrom = mode === 'CLOSEST_APPROACH' ? num(params.get('from')) : null
  const tvdssTo = mode === 'CLOSEST_APPROACH' ? num(params.get('to')) : null
  const windowError = tvdssFrom !== null && tvdssTo !== null && tvdssFrom >= tvdssTo
  const offsets = useOffsets(
    wellId,
    radiusKm,
    mode,
    { formation, tvdssFrom, tvdssTo },
    (mode !== 'AT_FORMATION' || formation !== null) && !windowError,
  )

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
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
      render: (o) => (
        <span className="font-medium whitespace-nowrap">
          {o.name}
          {o.status === 'planned' && <span className="font-normal text-muted"> · planned</span>}
        </span>
      ),
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
    ...(mode === 'AT_FORMATION'
      ? [
          {
            key: 'entry',
            header: 'Enters formation',
            render: (o: OffsetOut) => (
              <span className="num whitespace-nowrap">
                {o.entry_tvdss_m !== null && o.entry_tvdss_m !== undefined
                  ? formatDepth(o.entry_tvdss_m, units, 'TVDSS')
                  : '—'}
              </span>
            ),
            sortValue: (o: OffsetOut) => o.entry_tvdss_m,
            align: 'right' as const,
          },
        ]
      : []),
    ...(mode === 'CLOSEST_APPROACH'
      ? [
          {
            key: 'closest',
            header: 'Closest at',
            render: (o: OffsetOut) => (
              <span className="num whitespace-nowrap">
                {o.closest_tvdss_m !== null && o.closest_tvdss_m !== undefined
                  ? formatDepth(o.closest_tvdss_m, units, 'TVDSS')
                  : '—'}
              </span>
            ),
            sortValue: (o: OffsetOut) => o.closest_tvdss_m,
            align: 'right' as const,
          },
        ]
      : []),
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

  // Bearing and TD describe wellheads; in the subsurface modes the depth column replaces them.
  const shownColumns =
    mode === 'SURFACE'
      ? columns
      : columns.filter((c) => !['bearing', 'td', 'status'].includes(c.key))
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
              <div
                className="flex flex-wrap gap-1"
                role="radiogroup"
                aria-label="Distance measured"
                data-testid="proximity-mode"
              >
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="radio"
                    aria-checked={mode === m.id}
                    title={m.hint}
                    onClick={() => update({ mode: m.id === 'SURFACE' ? null : m.id })}
                    className={cn(
                      'rounded-md border border-border px-2 py-0.5 text-xs',
                      mode === m.id ? 'bg-accent text-accent-contrast' : 'text-text',
                    )}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </fieldset>
            {mode === 'AT_FORMATION' && (
              <label className="mt-2 block text-xs font-medium text-muted">
                Formation
                <select
                  className="mt-1 w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-text"
                  value={formation ?? ''}
                  onChange={(e) => update({ fm: e.target.value })}
                  data-testid="formation-select"
                  disabled={tops.length === 0}
                >
                  {tops.length === 0 && <option value="">no formation tops for this well</option>}
                  {tops.map((t) => (
                    <option key={t.formation} value={t.formation}>
                      {t.formation}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {mode === 'CLOSEST_APPROACH' && (
              <fieldset className="mt-2">
                <legend className="mb-1 text-xs font-medium text-muted">
                  TVDSS window (optional, m)
                </legend>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    aria-label="TVDSS window from (m)"
                    placeholder="from"
                    defaultValue={params.get('from') ?? ''}
                    onBlur={(e) => update({ from: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && update({ from: e.currentTarget.value })}
                    className="w-full rounded-lg border border-border bg-surface px-2 py-1 text-sm text-text"
                    data-testid="tvdss-from"
                  />
                  <span className="text-muted">–</span>
                  <input
                    type="number"
                    aria-label="TVDSS window to (m)"
                    placeholder="to"
                    defaultValue={params.get('to') ?? ''}
                    onBlur={(e) => update({ to: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && update({ to: e.currentTarget.value })}
                    className="w-full rounded-lg border border-border bg-surface px-2 py-1 text-sm text-text"
                    data-testid="tvdss-to"
                  />
                </div>
                {windowError && (
                  <p className="mt-1 text-xs text-danger" role="alert">
                    The window's top must be shallower than its base.
                  </p>
                )}
              </fieldset>
            )}
            {mode !== 'SURFACE' && (
              <p className="mt-2 text-[0.7rem] text-muted">
                The radius bounds this 3D distance; the circle on the map is drawn at the surface.
              </p>
            )}
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
                    Open Well 360 <ArrowRight size={14} aria-hidden />
                  </Link>
                  <details className="rounded-lg border border-border px-3 py-2" open>
                    <summary className="cursor-pointer text-sm font-semibold text-text">
                      Offset prior risk by depth
                    </summary>
                    {risk.data ? (
                      <div className="mt-2">
                        <RiskCurve profile={risk.data} compact width={370} height={280} />
                        <Link
                          to={`/wells/${well.data.id}?tab=risk`}
                          className="mt-1 inline-flex items-center gap-1 text-xs text-accent hover:underline"
                        >
                          Numbers and mitigations <ArrowRight size={12} aria-hidden />
                        </Link>
                      </div>
                    ) : risk.isError ? (
                      <p className="mt-2 text-sm text-muted">No risk profile for this well.</p>
                    ) : (
                      <SkeletonBlock className="mt-2 h-40 w-full" />
                    )}
                  </details>
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
                  columns={shownColumns}
                  rows={shownOffsets}
                  rowKey={(o) => o.well_id}
                  initialSort={{ key: 'distance', dir: 'asc' }}
                  onRowClick={(o) => select(o.well_id)}
                  empty={`No offset wells within ${radiusKm} km — widen the radius.`}
                />
              ) : (
                <SkeletonBlock className="h-40 w-full" />
              )}
              <p className="text-xs text-muted" data-testid="distance-label">
                {offsets.data?.distance_label}
              </p>
              {offsets.data && offsets.data.excluded.length > 0 && (
                <details className="text-xs text-muted" data-testid="excluded-wells">
                  <summary className="cursor-pointer">
                    {offsets.data.excluded.length === 1
                      ? '1 well within reach was left out'
                      : `${offsets.data.excluded.length} wells within reach were left out`}{' '}
                    — why?
                  </summary>
                  <ul className="mt-1 space-y-0.5">
                    {offsets.data.excluded.map((x) => (
                      <li key={x.well_id}>
                        <span className="text-text">{x.name}</span>: {x.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
