import { useQueries } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { useTheme } from '../../app/themeContext'
import { api, type EventSummary, type WellDetail } from '../../lib/api/client'
import { queryKeys, useOffsets, useTrajectory } from '../../lib/api/hooks'
import { eventMeta } from '../../lib/eventTypes'
import { formatDepth, formatNumber } from '../../lib/format/units'
import { atMd, displacement, toLocal, type P3 } from '../../lib/trajectory3d'
import { EvidenceLink } from '../evidence/EvidenceLink'
import { Badge } from '../ui/Badge'
import { Card, CardTitle } from '../ui/Card'
import { SkeletonBlock } from '../ui/Skeleton'
import { Trajectory3D, type Marker3, type Path3 } from './Trajectory3D'

const OFFSET_RADIUS_KM = 3
const MAX_OFFSETS = 6

export function TrajectoryTab({ well, events }: { well: WellDetail; events: EventSummary[] }) {
  const { units } = useTheme()
  const traj = useTrajectory(well.id)
  const near = useOffsets(well.id, OFFSET_RADIUS_KM, 'SURFACE')
  const offsetIds = useMemo(
    () =>
      (near.data?.offsets ?? [])
        .filter((o) => o.status !== 'planned')
        .slice(0, MAX_OFFSETS)
        .map((o) => ({ id: o.well_id, name: o.name })),
    [near.data],
  )
  const offsetData = useQueries({
    queries: offsetIds.map((o) => ({
      queryKey: queryKeys.trajectory(o.id),
      queryFn: () => api.trajectory(o.id),
      staleTime: 300_000,
    })),
    combine: (results) => results.map((r) => r.data),
  })
  const [picked, setPicked] = useState<number | null>(null)

  const stations = useMemo(
    () =>
      (traj.data?.stations ?? []).map((s) => ({
        md_m: s.md_m,
        east_m: s.east_m,
        north_m: s.north_m,
        tvdss_m: s.tvdss_m,
      })),
    [traj.data],
  )
  const paths = useMemo<Path3[]>(() => {
    if (!traj.data) return []
    const subject: Path3 = {
      id: well.id,
      name: well.name,
      subject: true,
      assumed: traj.data.assumed,
      points: stations.map((s) => ({ east: s.east_m, north: s.north_m, tvdss: s.tvdss_m })),
    }
    const others: Path3[] = []
    offsetData.forEach((t, i) => {
      if (!t) return
      others.push({
        id: t.well_id,
        name: offsetIds[i]?.name ?? `#${t.well_id}`,
        assumed: t.assumed,
        points: t.path.map((p) => ({
          ...toLocal(well.lat, well.lon, p.lat, p.lon),
          tvdss: p.tvdss_m,
        })),
      })
    })
    return [subject, ...others]
  }, [traj.data, stations, offsetData, offsetIds, well])

  const markers = useMemo<Marker3[]>(() => {
    const out: Marker3[] = []
    for (const t of well.formation_tops) {
      const at = atMd(stations, t.top_md_m)
      if (at)
        out.push({
          key: `top-${t.formation}`,
          at,
          kind: 'top',
          label: `${t.formation}: top ${formatNumber(t.top_md_m)} m MD / ${formatNumber(t.top_tvdss_m)} m TVDSS`,
        })
    }
    for (const e of events) {
      if (e.md_m === null) continue
      const at: P3 | null = atMd(stations, e.md_m)
      if (at)
        out.push({
          key: String(e.id),
          at,
          kind: 'event',
          eventType: e.event_type,
          verified: e.verified,
          label: `${eventMeta(e.event_type).label} at ${formatNumber(e.md_m)} m MD${e.formation ? ` in ${e.formation}` : ''}`,
        })
    }
    return out
  }, [well.formation_tops, events, stations])

  if (traj.isPending) return <SkeletonBlock className="h-[30rem] w-full rounded-xl" />
  if (traj.isError || !traj.data)
    return <p className="text-sm text-muted">No trajectory is available for this well.</p>

  const st = traj.data.stations
  const disp = displacement(stations)
  const maxInc = Math.max(0, ...st.map((s) => s.inc_deg))
  const maxDls = Math.max(0, ...st.map((s) => s.dls_deg_30m))
  const kop = st.find((s) => s.inc_deg > 3)
  const pickedEvent = events.find((e) => e.id === picked) ?? null

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <Card className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="mb-0">Well path and offsets within {OFFSET_RADIUS_KM} km</CardTitle>
          {traj.data.assumed && (
            <Badge
              tone="warn"
              title="No survey loaded: drawn as a vertical well from the surface location"
            >
              assumed trajectory
            </Badge>
          )}
        </div>
        <Trajectory3D paths={paths} markers={markers} onSelectEvent={(k) => setPicked(Number(k))} />
        <p className="text-xs text-muted">
          Orange: {well.name}. Grey: offset wells ({offsetIds.length}), placed from their own
          surveys. Ticks mark formation tops; shapes mark events (dashed = unverified). Horizontal
          and vertical scales are equal.
        </p>
      </Card>
      <div className="space-y-4">
        <Card className="text-sm">
          <CardTitle>Survey</CardTitle>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted">Stations</dt>
            <dd className="num">{st.length}</dd>
            <dt className="text-muted">TD</dt>
            <dd className="num">
              {st.length ? formatDepth(st[st.length - 1]!.md_m, units, 'MD') : '—'}
            </dd>
            <dt className="text-muted">Kick-off</dt>
            <dd className="num">{kop ? formatDepth(kop.md_m, units, 'MD') : 'vertical'}</dd>
            <dt className="text-muted">Max inclination</dt>
            <dd className="num">{formatNumber(maxInc, 1)}°</dd>
            <dt className="text-muted">Max dogleg</dt>
            <dd className="num">{formatNumber(maxDls, 2)}°/30 m</dd>
            <dt className="text-muted">Displacement</dt>
            <dd className="num">
              {formatNumber(disp.distance)} m at {formatNumber(disp.azimuth)}°
            </dd>
            <dt className="text-muted">Datum</dt>
            <dd>
              RKB {well.rkb_elev_m !== null ? `${formatNumber(well.rkb_elev_m, 1)} m` : '—'}
              {well.datum_assumed && (
                <Badge tone="warn" className="ml-1">
                  assumed
                </Badge>
              )}
            </dd>
          </dl>
        </Card>
        {pickedEvent && (
          <Card className="space-y-1 text-sm" data-testid="trajectory-event-card">
            <CardTitle className="mb-0">{eventMeta(pickedEvent.event_type).label}</CardTitle>
            <p className="text-xs text-muted">
              {pickedEvent.md_m !== null ? formatDepth(pickedEvent.md_m, units, 'MD') : ''}
              {pickedEvent.tvdss_m !== null
                ? ` · ${formatDepth(pickedEvent.tvdss_m, units, 'TVDSS')}`
                : ''}
              {pickedEvent.formation ? ` · ${pickedEvent.formation}` : ''}
            </p>
            {pickedEvent.evidence.map((ev) => (
              <EvidenceLink
                key={`${ev.document_id}-${ev.page_no}`}
                documentId={ev.document_id}
                pageNo={ev.page_no}
                spanIds={ev.span_ids}
                title={ev.filename ?? undefined}
              >
                {ev.filename ?? `doc ${ev.document_id}`} p.{ev.page_no}
              </EvidenceLink>
            ))}
          </Card>
        )}
        <details className="rounded-xl border border-border bg-surface p-3 text-sm">
          <summary className="cursor-pointer font-medium text-text">
            Survey stations ({st.length})
          </summary>
          <div className="mt-2 max-h-80 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface text-muted">
                <tr>
                  {['MD', 'Inc', 'Azi', 'TVDSS', 'N', 'E'].map((h) => (
                    <th key={h} className="px-1 py-1 text-right font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="num">
                {st.map((s) => (
                  <tr key={s.md_m} className="border-t border-border">
                    <td className="px-1 text-right">{formatNumber(s.md_m, 1)}</td>
                    <td className="px-1 text-right">{formatNumber(s.inc_deg, 2)}</td>
                    <td className="px-1 text-right">{formatNumber(s.azi_deg, 1)}</td>
                    <td className="px-1 text-right">{formatNumber(s.tvdss_m, 1)}</td>
                    <td className="px-1 text-right">{formatNumber(s.north_m, 1)}</td>
                    <td className="px-1 text-right">{formatNumber(s.east_m, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </div>
  )
}
