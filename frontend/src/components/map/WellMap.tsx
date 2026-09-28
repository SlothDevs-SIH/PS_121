import 'leaflet/dist/leaflet.css'

import type { LatLngBoundsExpression, LatLngExpression } from 'leaflet'
import { useEffect } from 'react'
import {
  Circle,
  CircleMarker,
  MapContainer,
  Polyline,
  ScaleControl,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'

import type { WellSummary } from '../../lib/api/client'
import { useRuntimeConfig } from '../../lib/config'

export interface MapWell extends Pick<WellSummary, 'id' | 'name' | 'lat' | 'lon' | 'status'> {
  role: 'active' | 'offset' | 'other'
}

interface Props {
  wells: MapWell[]
  active: { lat: number; lon: number } | null
  radiusKm: number
  path: { lat: number; lon: number }[]
  onSelect: (id: number) => void
}

// Token colours are CSS variables; Leaflet needs literal values, so read them at render.
function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

const STATUS_COLOUR: Record<string, [string, string]> = {
  completed: ['--accent', '#0b6bcb'],
  drilling: ['--warn', '#8a5a00'],
  planned: ['--info', '#3b4b9e'],
}

function FitToRadius({
  center,
  radiusKm,
}: {
  center: { lat: number; lon: number }
  radiusKm: number
}) {
  const map = useMap()
  useEffect(() => {
    const dLat = radiusKm / 111.32
    const dLon = radiusKm / (111.32 * Math.cos((center.lat * Math.PI) / 180))
    const bounds: LatLngBoundsExpression = [
      [center.lat - dLat, center.lon - dLon],
      [center.lat + dLat, center.lon + dLon],
    ]
    map.fitBounds(bounds, { padding: [16, 16] })
  }, [map, center.lat, center.lon, radiusKm])
  return null
}

export default function WellMap({ wells, active, radiusKm, path, onSelect }: Props) {
  const { data: config } = useRuntimeConfig()
  const centre: LatLngExpression = active ? [active.lat, active.lon] : [27.4, 95.25]
  const accent = cssVar('--accent', '#0b6bcb')
  const muted = cssVar('--text-muted', '#5a6778')

  return (
    <MapContainer
      center={centre}
      zoom={12}
      className="smriti-map h-full min-h-[22rem] w-full rounded-lg border border-border"
      attributionControl={Boolean(config?.mapTileUrl)}
    >
      {config?.mapTileUrl ? (
        <TileLayer url={config.mapTileUrl} attribution={config.mapTileAttribution} />
      ) : null}
      <ScaleControl position="bottomleft" imperial={false} />
      {active && (
        <>
          <FitToRadius center={active} radiusKm={radiusKm} />
          <Circle
            center={[active.lat, active.lon]}
            radius={radiusKm * 1000}
            pathOptions={{ color: accent, weight: 1.5, dashArray: '6 6', fillOpacity: 0.05 }}
          />
        </>
      )}
      {path.length > 1 && (
        <Polyline
          positions={path.map((p) => [p.lat, p.lon] as [number, number])}
          pathOptions={{ color: accent, weight: 3, opacity: 0.8 }}
        />
      )}
      {wells.map((w) => {
        const [v, fb] = STATUS_COLOUR[w.status] ?? ['--text-muted', muted]
        const colour = w.role === 'other' ? muted : cssVar(v, fb)
        return (
          <CircleMarker
            key={w.id}
            center={[w.lat, w.lon]}
            radius={w.role === 'active' ? 9 : w.role === 'offset' ? 6 : 4}
            pathOptions={{
              color: w.role === 'active' ? accent : colour,
              weight: w.role === 'active' ? 3 : 1,
              fillColor: colour,
              fillOpacity: w.role === 'other' ? 0.25 : 0.85,
            }}
            eventHandlers={{ click: () => onSelect(w.id) }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              {w.name} · {w.status}
            </Tooltip>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
