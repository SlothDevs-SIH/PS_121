import { lazy, Suspense, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useTheme } from '../app/themeContext'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { Card, CardTitle } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import type { OffsetOut, ProximityMode } from '../lib/api/client'
import { useOffsets, useTrajectory, useWell, useWells } from '../lib/api/hooks'
import { cn } from '../lib/cn'
import { formatBearing, formatDepth, formatDistance } from '../lib/format/units'

const WellMap = lazy(() => import('../components/map/WellMap'))

const MODES: { id: ProximityMode; label: string; phase?: string }[] = [
  { id: 'SURFACE', label: 'Surface' },
  { id: 'AT_FORMATION', label: 'At formation', phase: 'B2' },
  { id: 'CLOSEST_APPROACH', label: 'Closest approach', phase: 'B2' },
]

function clampRadius(v: number): number {
  return Number.isFinite(v) ? Math.min(20, Math.max(1, v)) : 5
}

export function WellMapPage() {
  const { units } = useTheme()
  const [params, setParams] = useSearchParams()
  const wells = useWells()
  const items = useMemo(() => wells.data?.items ?? [], [wells.data])

  const defaultWell = items.find((w) => w.status === 'planned') ?? items[0]
  const wellId = Number(params.get('well')) || defaultWell?.id || null
  const radiusParam = clampRadius(Number(params.get('r') ?? 5))
  const mode = (params.get('mode') as ProximityMode | null) ?? 'SURFACE'
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

  const offsetIds = new Set(offsets.data?.offsets.map((o) => o.well_id))
  const mapWells = items.map((w) => ({
    id: w.id,
    name: w.name,
    lat: w.lat,
    lon: w.lon,
    status: w.status,
    role:
      w.id === wellId
        ? ('active' as const)
        : offsetIds.has(w.id)
          ? ('offset' as const)
          : ('other' as const),
  }))

  const columns: Column<OffsetOut>[] = [
    {
      key: 'name',
      header: 'Well',
      render: (o) => <span className="whitespace-nowrap">{o.name}</span>,
      sortValue: (o) => o.name,
    },
    {
      key: 'distance',
      header: 'Distance',
      render: (o) => <span className="whitespace-nowrap">{formatDistance(o.distance_m)}</span>,
      sortValue: (o) => o.distance_m,
      align: 'right',
    },
    {
      key: 'bearing',
      header: 'Bearing',
      render: (o) => formatBearing(o.bearing_deg),
      align: 'right',
    },
    { key: 'status', header: 'Status', render: (o) => o.status, sortValue: (o) => o.status },
    {
      key: 'td',
      header: 'TD',
      render: (o) => (
        <span className="whitespace-nowrap">
          {o.td_md_m ? formatDepth(o.td_md_m, units, 'MD') : '—'}
        </span>
      ),
      sortValue: (o) => o.td_md_m,
      align: 'right',
    },
  ]

  const anySynthetic = items.some((w) => w.synthetic)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold text-text">Well Map</h1>
        {anySynthetic && <SyntheticBadge />}
      </div>
      {wells.isError && <p className="text-danger">Wells could not be loaded.</p>}
      {wells.data && items.length === 0 && (
        <p className="text-muted">
          No wells yet. Load the synthetic field with <code>make seed</code>.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="h-[60vh] min-h-[22rem] min-w-0" data-testid="map-panel">
          <Suspense fallback={<p className="text-sm text-muted">Loading map…</p>}>
            <WellMap
              wells={mapWells}
              active={well.data ? { lat: well.data.lat, lon: well.data.lon } : null}
              radiusKm={radiusKm}
              path={trajectory.data?.path ?? []}
              onSelect={(id) => update({ well: String(id) })}
            />
          </Suspense>
        </div>

        <div className="min-w-0 space-y-4">
          <Card>
            <label className="mb-1 block text-sm font-medium text-text" htmlFor="well-select">
              Active well
            </label>
            <select
              id="well-select"
              className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-text"
              value={wellId ?? ''}
              onChange={(e) => update({ well: e.target.value })}
            >
              {items.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} ({w.status})
                </option>
              ))}
            </select>
            {well.data && (
              <p className="mt-2 text-sm text-muted" data-testid="active-well-summary">
                {well.data.status} · {well.data.profile ?? '—'} profile
                {well.data.td_md_m ? ` · TD ${formatDepth(well.data.td_md_m, units, 'MD')}` : ''} ·
                data quality {Math.round(well.data.data_quality.score * 100)}%
              </p>
            )}

            <label className="mt-4 mb-1 block text-sm font-medium text-text" htmlFor="radius">
              Radius: <span data-testid="radius-value">{radiusDraft ?? radiusParam}</span> km
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

            <fieldset className="mt-4">
              <legend className="mb-1 text-sm font-medium text-text">Distance measured</legend>
              <div className="flex flex-wrap gap-1" role="radiogroup">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="radio"
                    aria-checked={mode === m.id}
                    disabled={Boolean(m.phase)}
                    title={m.phase ? `Planned for backend phase ${m.phase}` : undefined}
                    onClick={() => update({ mode: m.id })}
                    className={cn(
                      'rounded-md border border-border px-2 py-1 text-sm',
                      mode === m.id ? 'bg-accent text-accent-contrast' : 'text-text',
                      m.phase && 'opacity-60',
                    )}
                  >
                    {m.label}
                    {m.phase && <span className="ml-1 text-xs">({m.phase})</span>}
                  </button>
                ))}
              </div>
            </fieldset>
          </Card>

          <Card>
            <CardTitle>
              Offset wells{' '}
              {offsets.data && (
                <Badge tone="info" data-testid="offset-count">
                  {offsets.data.offsets.length} within {radiusKm} km
                </Badge>
              )}
            </CardTitle>
            {offsets.isError && <p className="text-sm text-danger">Offsets could not be loaded.</p>}
            {offsets.data && (
              <DataTable
                testId="offset-table"
                caption="Offset wells"
                columns={columns}
                rows={offsets.data.offsets}
                rowKey={(o) => o.well_id}
                initialSort={{ key: 'distance', dir: 'asc' }}
                onRowClick={(o) => update({ well: String(o.well_id) })}
                empty={`No offset wells within ${radiusKm} km — widen the radius.`}
              />
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
