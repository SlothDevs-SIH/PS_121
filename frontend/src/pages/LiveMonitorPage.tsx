import { Activity, Pause, Play, Radio, Square, WifiOff } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { ChannelStrip } from '../components/live/ChannelStrip'
import { LookAheadBar } from '../components/live/LookAheadBar'
import { RigRibbon } from '../components/live/RigRibbon'
import { RiskGauges } from '../components/live/RiskGauges'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardTitle } from '../components/ui/Card'
import { SkeletonBlock } from '../components/ui/Skeleton'
import { useLiveWell, useNow, type LiveFrame, type LiveWell } from '../hooks/useLive'
import type { AlertOut } from '../lib/api/client'
import {
  useAlerts,
  useMe,
  useRealtimeWindow,
  useReplayControl,
  useRiskProfile,
  useWells,
} from '../lib/api/hooks'
import { eventMeta } from '../lib/eventTypes'
import { ago, formatValue, lookAhead, mergeSeries } from '../lib/liveView'

const STRIPS = [
  'hookload_kn',
  'torque_knm',
  'spp_kpa',
  'flow_in_lpm',
  'flow_out_lpm',
  'pit_volume_m3',
  'rop_m_h',
  'gas_pct',
]
const WINDOW_MIN = 60
const SPEEDS = [60, 300, 1500]
const SEVERITY_TONE = { critical: 'danger', warning: 'warn', info: 'info' } as const

function ConnectionPill({ live }: { live: LiveWell }) {
  const now = useNow()
  if (live.closedCode === 4401 || live.closedCode === 4403)
    return (
      <Badge tone="danger">
        {live.closedCode === 4401 ? 'Log in to see live data' : 'Your role cannot see live data'}
      </Badge>
    )
  if (live.state !== 'open')
    return (
      <Badge tone="warn" data-testid="live-connection">
        <WifiOff size={12} aria-hidden />{' '}
        {live.state === 'connecting' ? 'Connecting…' : 'Reconnecting…'}
      </Badge>
    )
  return (
    <Badge tone={live.stale ? 'warn' : 'ok'} data-testid="live-connection">
      <Radio size={12} aria-hidden /> {live.stale ? 'Stale' : 'Live'}
      {live.receivedAt !== null && (
        <span className="text-muted">· updated {ago(now - live.receivedAt)}</span>
      )}
    </Badge>
  )
}

function Tile({
  label,
  value,
  unit,
  testId,
}: {
  label: string
  value: string
  unit?: string
  testId?: string
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3" data-testid={testId}>
      <div className="text-xs text-muted">{label}</div>
      <div className="num text-2xl font-semibold text-text">
        {value} {unit && <span className="text-sm font-normal text-muted">{unit}</span>}
      </div>
    </div>
  )
}

function ReplayControls({ wellId, live }: { wellId: number; live: LiveWell }) {
  const control = useReplayControl()
  const [speed, setSpeed] = useState(60)
  const status = live.replay?.status
  const running = status === 'running' || status === 'pending'
  const act = (action: 'start' | 'pause' | 'resume' | 'stop') =>
    control.mutate({ wellId, action, speed: action === 'start' ? speed : undefined })
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="replay-controls">
      <label className="text-xs text-muted" htmlFor="replay-speed">
        Speed
      </label>
      <select
        id="replay-speed"
        value={speed}
        onChange={(e) => setSpeed(Number(e.target.value))}
        className="rounded-md border border-border bg-surface px-2 py-1 text-sm"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            ×{s}
          </option>
        ))}
      </select>
      {!running && status !== 'paused' && (
        <Button variant="primary" onClick={() => act('start')} disabled={control.isPending}>
          <Play size={14} aria-hidden /> Start replay
        </Button>
      )}
      {running && (
        <Button onClick={() => act('pause')} disabled={control.isPending}>
          <Pause size={14} aria-hidden /> Pause
        </Button>
      )}
      {status === 'paused' && (
        <Button onClick={() => act('resume')} disabled={control.isPending}>
          <Play size={14} aria-hidden /> Resume
        </Button>
      )}
      {(running || status === 'paused') && (
        <Button onClick={() => act('stop')} disabled={control.isPending}>
          <Square size={14} aria-hidden /> Stop
        </Button>
      )}
      {control.isError && <span className="text-sm text-danger">{control.error.message}</span>}
    </div>
  )
}

function WellAlerts({ alerts }: { alerts: AlertOut[] }) {
  if (alerts.length === 0) return <p className="text-sm text-muted">No open alerts on this well.</p>
  return (
    <ul className="space-y-2" data-testid="live-alerts">
      {alerts.slice(0, 8).map((a) => (
        <li key={a.id}>
          <Link
            to={`/alerts?id=${a.id}`}
            className="block rounded-lg border border-border px-3 py-2 hover:bg-surface-2"
          >
            <div className="flex items-center gap-2">
              <Badge tone={SEVERITY_TONE[a.severity]}>{a.severity}</Badge>
              <span className="truncate text-sm font-medium text-text">{a.title}</span>
            </div>
            <div className="mt-0.5 text-xs text-muted">
              {eventMeta(a.event_type).label} · {a.formation ?? 'formation —'} ·{' '}
              {new Date(a.t_data).toISOString().slice(11, 16)} data time
            </div>
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function LiveMonitorPage() {
  const [params, setParams] = useSearchParams()
  const wells = useWells()
  const drilling = (wells.data?.items ?? []).filter((w) => w.status === 'drilling')
  const wellId = Number(params.get('well')) || drilling[0]?.id || null
  const well = wells.data?.items.find((w) => w.id === wellId)
  const me = useMe()
  const canControl = me.data?.permissions.includes('control_replay') ?? false
  const win = useRealtimeWindow(wellId, { minutes: WINDOW_MIN, max_points: 720 })
  const live = useLiveWell(wellId)
  const profile = useRiskProfile(wellId)
  const alerts = useAlerts({ well_id: wellId, status: ['new', 'ack'] }, wellId !== null)

  const series = useMemo(
    () => mergeSeries(win.data, live.frames, STRIPS, WINDOW_MIN),
    [win.data, live.frames],
  )
  const latest: LiveFrame | null =
    live.latest ?? (win.data?.latest as unknown as LiveFrame | null | undefined) ?? null
  const la = lookAhead(profile.data, latest?.bit_tvdss_m)
  const domain: [number, number] = series.times.length
    ? [
        series.times[series.times.length - 1]! - WINDOW_MIN * 60_000,
        series.times[series.times.length - 1]!,
      ]
    : [0, 1]
  const scores = latest?.latest_scores ?? latest?.scores ?? win.data?.latest?.['scores'] ?? {}
  const history = useMemo(() => {
    const h: Record<string, (number | null)[]> = {}
    const recent = live.frames.filter((f) => f.scores).slice(-5)
    for (const f of recent)
      for (const [k, v] of Object.entries(f.scores ?? {})) (h[k] ??= []).push(v)
    if (Object.keys(h).length === 0 && win.data)
      for (const [k, vs] of Object.entries(win.data.scores)) h[k] = vs.slice(-5)
    return h
  }, [live.frames, win.data])
  const markers = (alerts.data?.items ?? []).map((a) => ({
    t: Date.parse(a.t_data),
    label: a.title,
  }))
  const v = latest?.values ?? {}
  const replay = live.replay ?? (win.data?.session ? { ...win.data.session } : null)

  if (wells.isLoading)
    return (
      <div className="space-y-4" aria-busy="true">
        <SkeletonBlock className="h-8 w-56" />
        <SkeletonBlock className="h-64 w-full" />
      </div>
    )
  if (wellId === null)
    return (
      <Card>
        <CardTitle>Live Well Monitor</CardTitle>
        <p className="text-sm text-muted">
          No well is drilling. Pick a well with a replay file from the Map.
        </p>
      </Card>
    )

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <Activity className="text-accent" aria-hidden />
        <h1 className="text-xl font-semibold text-text">Live Well Monitor</h1>
        <label className="sr-only" htmlFor="live-well">
          Well
        </label>
        <select
          id="live-well"
          value={wellId}
          onChange={(e) => setParams({ well: e.target.value })}
          className="rounded-md border border-border bg-surface px-2 py-1 text-sm"
        >
          {(drilling.length ? drilling : (wells.data?.items ?? [])).map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        {well?.synthetic && <SyntheticBadge />}
        <ConnectionPill live={live} />
        {replay && (replay.status === 'running' || replay.status === 'paused') && (
          <Badge tone="info" data-testid="replay-banner">
            REPLAY ×{replay.speed} {replay.status === 'paused' ? '(paused)' : ''} · row{' '}
            {replay.position}
            {replay.total_rows ? ` of ${replay.total_rows}` : ''}
          </Badge>
        )}
        <div className="ml-auto">
          {canControl && <ReplayControls wellId={wellId} live={live} />}
        </div>
      </header>

      {live.stale && live.state === 'open' && (
        <div
          role="status"
          className="rounded-lg border border-warn bg-warn-bg px-3 py-2 text-sm text-warn"
          data-testid="stale-banner"
        >
          No new data for a while: values below are the last received, not current.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Tile
          label="Bit depth"
          value={formatValue(latest?.bit_depth_m, 1)}
          unit="m MD"
          testId="tile-bit"
        />
        <Tile label="Bit TVDSS" value={formatValue(latest?.bit_tvdss_m, 1)} unit="m" />
        <Tile label="ROP" value={formatValue(v['rop_m_h'], 1)} unit="m/h" />
        <Tile
          label="Flow out − in"
          value={formatValue(latest?.indicators['flow_imbalance_pct'], 1)}
          unit="%"
        />
        <Tile
          label="Pit change (15 min)"
          value={formatValue(latest?.indicators['pit_change_15min_m3'], 2)}
          unit="m³"
        />
        <Tile
          label="Data time"
          value={latest ? new Date(latest.ts).toISOString().slice(11, 19) : '—'}
          unit="UTC"
          testId="tile-time"
        />
      </div>

      <LookAheadBar la={la} formationNow={latest?.formation ?? null} />

      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <Card className="min-w-0 space-y-2">
          <CardTitle>Channels (last {WINDOW_MIN} min of data)</CardTitle>
          {win.isLoading ? (
            <SkeletonBlock className="h-80 w-full" />
          ) : series.times.length === 0 ? (
            <p className="text-sm text-muted">
              No stream data yet.{' '}
              {canControl ? 'Start a replay.' : 'Ask an RTMAC engineer to start a replay.'}
            </p>
          ) : (
            <>
              <RigRibbon times={series.times} states={series.rig} domain={domain} />
              {STRIPS.map((c) => (
                <ChannelStrip
                  key={c}
                  channel={c}
                  times={series.times}
                  values={series.values[c] ?? []}
                  domain={domain}
                  markers={markers}
                />
              ))}
            </>
          )}
        </Card>
        <div className="space-y-4">
          <Card>
            <CardTitle>Next-30-min risk</CardTitle>
            <RiskGauges
              scores={scores as Record<string, number>}
              thresholds={win.data?.thresholds ?? {}}
              history={history}
            />
            <p className="mt-2 text-xs text-muted">
              Classifier probabilities trained on SYNTHETIC data; the bar marks each alert
              threshold. Advisory only.
            </p>
            {latest?.dejavu?.matches[0] && (
              <p className="mt-2 text-xs text-muted" data-testid="dejavu-now">
                Closest past run-up: {eventMeta(latest.dejavu.matches[0].event_type).label},
                similarity{' '}
                <span className="num">{latest.dejavu.matches[0].similarity.toFixed(2)}</span> (not a
                probability; alerts at 0.80).
              </p>
            )}
          </Card>
          <Card>
            <CardTitle>Open alerts</CardTitle>
            <WellAlerts alerts={alerts.data?.items ?? []} />
          </Card>
        </div>
      </div>
    </div>
  )
}
