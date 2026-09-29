/**
 * MapLibre well map (FRONTEND_SPEC §4.3).
 *
 * - Works fully offline: with no tile URL configured there is no basemap and no glyph
 *   server, so wells and clusters are HTML markers (styled by CSS tokens) instead of
 *   symbol layers. A raster basemap is added only when /config.json names one.
 * - Clustering is MapLibre's own (GeoJSON source `cluster`), with per-cluster fluid
 *   counts drawn as a composition ring. Drilling wells pulse.
 * - The container has a fixed size before the map is created (§7 rule 7) and resizes via a
 *   ResizeObserver, never per animation frame.
 */
import type { FeatureCollection, Point, Polygon, LineString } from 'geojson'
import { useEffect, useRef } from 'react'

import { useRuntimeConfig } from '../../lib/config'
import {
  GeoJSONSource,
  LngLatBounds,
  Map as MlMap,
  Marker,
  NavigationControl,
  ScaleControl,
} from '../../lib/maplibre'
import { FLUIDS, fluidOf } from '../../lib/wellTypes'
import { useUiStore } from '../../stores/ui'

export interface MapWell {
  id: number
  name: string
  lat: number
  lon: number
  status: string
  fluid: string | null
  role: 'active' | 'offset' | 'other'
  dimmed?: boolean
}

interface Props {
  wells: MapWell[]
  active?: { lat: number; lon: number } | null
  radiusKm?: number | null
  path?: { lat: number; lon: number }[]
  onSelect?: (id: number) => void
  interactive?: boolean
  cluster?: boolean
  className?: string
  testId?: string
  label?: string
}

const DEFAULT_CENTRE: [number, number] = [95.25, 27.4]

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function circlePolygon(lat: number, lon: number, km: number, steps = 96): Polygon {
  const coords: [number, number][] = []
  const dLat = km / 110.574
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180))
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI
    coords.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)])
  }
  return { type: 'Polygon', coordinates: [coords] }
}

function wellsGeoJson(wells: MapWell[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: wells.map((w) => ({
      type: 'Feature',
      id: w.id,
      geometry: { type: 'Point', coordinates: [w.lon, w.lat] },
      properties: { id: w.id, fluid: fluidOf(w.fluid) ?? 'none' },
    })),
  }
}

const focusOf = (wells: MapWell[]) => wells.filter((w) => w.role !== 'other')
const othersOf = (wells: MapWell[]) => wells.filter((w) => w.role === 'other')

function markerColour(w: MapWell): string {
  const f = fluidOf(w.fluid)
  if (f) return FLUIDS[f].colorVar
  return w.status === 'planned' ? 'var(--accent-2)' : 'var(--text-muted)'
}

export default function WellMap({
  wells,
  active = null,
  radiusKm = null,
  path = [],
  onSelect,
  interactive = true,
  cluster = true,
  className,
  testId = 'well-map',
  label = 'Map of wells',
}: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const markers = useRef(new globalThis.Map<string, Marker>())
  const wellsRef = useRef(wells)
  const onSelectRef = useRef(onSelect)
  const loaded = useRef(false)
  const onLoad = useRef<(() => void)[]>([])
  const theme = useUiStore((s) => s.theme)
  const { data: config } = useRuntimeConfig()
  const tileUrl = config?.mapTileUrl ?? ''

  wellsRef.current = wells
  onSelectRef.current = onSelect

  // Create the map once (per basemap setting).
  useEffect(() => {
    const el = container.current
    if (!el) return
    const map = new MlMap({
      container: el,
      style: {
        version: 8,
        sources: tileUrl
          ? {
              basemap: {
                type: 'raster',
                tiles: [tileUrl],
                tileSize: 256,
                attribution: config?.mapTileAttribution ?? '',
              },
            }
          : {},
        layers: tileUrl ? [{ id: 'basemap', type: 'raster', source: 'basemap' }] : [],
      },
      center: DEFAULT_CENTRE,
      zoom: 10,
      attributionControl: tileUrl ? { compact: true } : false,
      interactive,
      dragRotate: false,
      pitchWithRotate: false,
    })
    mapRef.current = map
    if (interactive) {
      map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    }
    map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-right')
    map.on('load', () => {
      loaded.current = true
      // The active well and its offsets never disappear into a cluster.
      map.addSource('focus', { type: 'geojson', data: wellsGeoJson(focusOf(wellsRef.current)) })
      map.addLayer({
        id: 'focus-hit',
        type: 'circle',
        source: 'focus',
        paint: { 'circle-radius': 1, 'circle-opacity': 0 },
      })
      map.addSource('wells', {
        type: 'geojson',
        data: wellsGeoJson(othersOf(wellsRef.current)),
        cluster,
        clusterRadius: 44,
        clusterMaxZoom: 13,
        clusterProperties: {
          oil: ['+', ['case', ['==', ['get', 'fluid'], 'oil'], 1, 0]],
          gas: ['+', ['case', ['==', ['get', 'fluid'], 'gas'], 1, 0]],
          water: ['+', ['case', ['==', ['get', 'fluid'], 'water'], 1, 0]],
        },
      })
      // Invisible layer: keeps the source's tiles loaded so markers can be read from it.
      map.addLayer({
        id: 'wells-hit',
        type: 'circle',
        source: 'wells',
        paint: { 'circle-radius': 1, 'circle-opacity': 0 },
      })
      map.addSource('radius', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({ id: 'radius-fill', type: 'fill', source: 'radius', paint: {} })
      map.addLayer({ id: 'radius-line', type: 'line', source: 'radius', paint: {} })
      map.addSource('path', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addLayer({
        id: 'path-line',
        type: 'line',
        source: 'path',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {},
      })
      applyPaint(map)
      for (const fn of onLoad.current.splice(0)) fn()
    })
    let frame = 0
    const sync = () => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        syncMarkers(map)
      })
    }
    map.on('render', sync)
    const ro = new ResizeObserver(() => map.resize())
    ro.observe(el)
    const current = markers.current
    return () => {
      ro.disconnect()
      cancelAnimationFrame(frame)
      for (const m of current.values()) m.remove()
      current.clear()
      loaded.current = false
      map.remove()
      mapRef.current = null
    }
    // eslint-style exhaustive deps are intentional: data flows in through refs/effects below.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [tileUrl, interactive, cluster])

  function syncMarkers(map: MlMap) {
    if (!loaded.current || !map.getSource('wells') || !map.getSource('focus')) return
    const byId = new globalThis.Map(wellsRef.current.map((w) => [w.id, w]))
    const seen = new Set<string>()
    const features = [...map.querySourceFeatures('focus'), ...map.querySourceFeatures('wells')]
    for (const f of features) {
      const p = f.properties ?? {}
      const [lon, lat] = (f.geometry as Point).coordinates as [number, number]
      if (p.cluster) {
        const key = `c${p.cluster_id}`
        if (seen.has(key)) continue
        seen.add(key)
        const n = Number(p.point_count) || 1
        let m = markers.current.get(key)
        if (!m) {
          const el = document.createElement('button')
          el.type = 'button'
          el.className = 'cluster-marker'
          el.addEventListener('click', async (e) => {
            e.stopPropagation()
            const src = map.getSource('wells') as GeoJSONSource
            const zoom = await src.getClusterExpansionZoom(Number(p.cluster_id))
            map.easeTo({ center: [lon, lat], zoom, duration: 600 })
          })
          m = new Marker({ element: el }).setLngLat([lon, lat]).addTo(map)
          markers.current.set(key, m)
        }
        const el = m.getElement()
        const oil = (Number(p.oil) / n) * 100
        const gas = oil + (Number(p.gas) / n) * 100
        el.style.setProperty('--oil', `${oil}%`)
        el.style.setProperty('--gas', `${gas}%`)
        el.style.setProperty('--size', `${Math.min(56, 30 + Math.sqrt(n) * 4)}px`)
        el.setAttribute('aria-label', `${n} wells here; zoom in`)
        el.innerHTML = `<span>${n}</span>`
        continue
      }
      const w = byId.get(Number(p.id))
      if (!w) continue
      const key = `w${w.id}`
      seen.add(key)
      let m = markers.current.get(key)
      if (!m) {
        const el = document.createElement('button')
        el.type = 'button'
        el.className = 'well-marker'
        el.dataset.wellId = String(w.id)
        el.addEventListener('click', (e) => {
          e.stopPropagation()
          onSelectRef.current?.(Number(el.dataset.wellId))
        })
        m = new Marker({ element: el }).setLngLat([w.lon, w.lat]).addTo(map)
        markers.current.set(key, m)
      }
      const el = m.getElement()
      el.style.setProperty('--c', markerColour(w))
      el.dataset.role = w.role
      el.dataset.live = String(w.status === 'drilling')
      el.dataset.dimmed = String(Boolean(w.dimmed))
      el.title = `${w.name} · ${w.status}${fluidOf(w.fluid) ? ` · ${w.fluid}` : ''}`
      el.setAttribute('aria-label', el.title)
      el.style.zIndex = w.role === 'active' ? '3' : w.role === 'offset' ? '2' : '1'
    }
    for (const [key, m] of markers.current) {
      if (!seen.has(key)) {
        m.remove()
        markers.current.delete(key)
      }
    }
  }

  function applyPaint(map: MlMap) {
    if (!loaded.current) return
    const accent = cssVar('--accent', '#ff6b35')
    map.setPaintProperty('radius-fill', 'fill-color', accent)
    map.setPaintProperty('radius-fill', 'fill-opacity', 0.07)
    map.setPaintProperty('radius-line', 'line-color', accent)
    map.setPaintProperty('radius-line', 'line-width', 1.5)
    map.setPaintProperty('radius-line', 'line-dasharray', [3, 3])
    map.setPaintProperty('path-line', 'line-color', accent)
    map.setPaintProperty('path-line', 'line-width', 3)
    map.setPaintProperty('path-line', 'line-opacity', 0.85)
  }

  // Well data.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const push = () => {
      ;(map.getSource('focus') as GeoJSONSource | undefined)?.setData(wellsGeoJson(focusOf(wells)))
      ;(map.getSource('wells') as GeoJSONSource | undefined)?.setData(wellsGeoJson(othersOf(wells)))
      syncMarkers(map)
    }
    if (loaded.current) push()
    else onLoad.current.push(push)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [wells])

  // Radius circle, trajectory path and camera.
  const pathKey = path.map((p) => `${p.lat.toFixed(5)},${p.lon.toFixed(5)}`).join(';')
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => {
      const radius = map.getSource('radius') as GeoJSONSource | undefined
      radius?.setData({
        type: 'FeatureCollection',
        features:
          active && radiusKm
            ? [
                {
                  type: 'Feature',
                  geometry: circlePolygon(active.lat, active.lon, radiusKm),
                  properties: {},
                },
              ]
            : [],
      })
      const line = map.getSource('path') as GeoJSONSource | undefined
      const lineGeom: LineString = {
        type: 'LineString',
        coordinates: path.map((p) => [p.lon, p.lat]),
      }
      line?.setData({
        type: 'FeatureCollection',
        features: path.length > 1 ? [{ type: 'Feature', geometry: lineGeom, properties: {} }] : [],
      })
      const bounds = new LngLatBounds()
      if (active && radiusKm) {
        const dLat = radiusKm / 110.574
        const dLon = radiusKm / (111.32 * Math.cos((active.lat * Math.PI) / 180))
        bounds.extend([active.lon - dLon, active.lat - dLat])
        bounds.extend([active.lon + dLon, active.lat + dLat])
      } else {
        for (const w of wellsRef.current) bounds.extend([w.lon, w.lat])
      }
      if (bounds.isEmpty()) return
      const camera = map.cameraForBounds(bounds, { padding: 32, maxZoom: 15 })
      if (camera) map.flyTo({ ...camera, duration: interactive ? 1400 : 0, essential: true })
    }
    if (loaded.current) apply()
    else onLoad.current.push(apply)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.lat, active?.lon, radiusKm, pathKey, wells.length === 0])

  // Theme: re-read the tokens.
  useEffect(() => {
    const map = mapRef.current
    if (map) applyPaint(map)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [theme])

  return (
    <div
      ref={container}
      role="region"
      aria-label={label}
      data-testid={testId}
      className={['smriti-map relative h-full w-full overflow-hidden rounded-xl', className]
        .filter(Boolean)
        .join(' ')}
    />
  )
}
