/**
 * 3D trajectory view maths (Well 360, FRONTEND_PLAN §4.3): an orthographic camera that
 * turns about the vertical (yaw) and tilts (pitch), so plan and section views are just two
 * camera presets. Pure functions, unit-tested; drawing lives in Trajectory3D.tsx.
 *
 * Coordinates: east and north in metres from the subject wellhead, TVDSS in metres
 * (positive down). Offsets are placed from their lat/lon path with toLocal().
 */

export interface P3 {
  east: number
  north: number
  tvdss: number
}

export interface View {
  /** Degrees; 0 = looking north. */
  yaw: number
  /** Degrees; 0 = horizontal (section view), 90 = from above (plan view). */
  pitch: number
}

export const VIEWS = {
  perspective: { yaw: 35, pitch: 28 },
  plan: { yaw: 0, pitch: 90 },
  section: { yaw: 0, pitch: 0 },
} satisfies Record<string, View>

const R_EARTH_M = 6_371_008.8
const rad = (deg: number) => (deg * Math.PI) / 180

/** East/north (m) of lat/lon from an origin; equirectangular, well under 0.1% error at 20 km. */
export function toLocal(lat0: number, lon0: number, lat: number, lon: number) {
  const north = rad(lat - lat0) * R_EARTH_M
  const east = rad(lon - lon0) * R_EARTH_M * Math.cos(rad((lat + lat0) / 2))
  return { east, north }
}

/** Screen x (right), y (down) and z (away from the viewer) of a point for a view. */
export function project(p: P3, v: View): { x: number; y: number; z: number } {
  const a = rad(v.yaw)
  const b = rad(v.pitch)
  const x = p.east * Math.cos(a) - p.north * Math.sin(a)
  const into = p.east * Math.sin(a) + p.north * Math.cos(a)
  return {
    x,
    y: p.tvdss * Math.cos(b) - into * Math.sin(b),
    z: p.tvdss * Math.sin(b) + into * Math.cos(b),
  }
}

/** Centre and radius of the scene: the scale fitted from them does not change as it turns. */
export function bounds(points: P3[]) {
  if (points.length === 0) return { centre: { east: 0, north: 0, tvdss: 0 }, radius: 1 }
  const lo = { east: Infinity, north: Infinity, tvdss: Infinity }
  const hi = { east: -Infinity, north: -Infinity, tvdss: -Infinity }
  for (const p of points)
    for (const k of ['east', 'north', 'tvdss'] as const) {
      lo[k] = Math.min(lo[k], p[k])
      hi[k] = Math.max(hi[k], p[k])
    }
  const centre = {
    east: (lo.east + hi.east) / 2,
    north: (lo.north + hi.north) / 2,
    tvdss: (lo.tvdss + hi.tvdss) / 2,
  }
  const radius = Math.max(
    1,
    Math.hypot(hi.east - lo.east, hi.north - lo.north, hi.tvdss - lo.tvdss) / 2,
  )
  return { centre, radius, lo, hi }
}

/** Screen mapping for a viewport: the scene's bounding sphere fits the smaller side. */
export function viewport(points: P3[], width: number, height: number, pad = 24) {
  const { centre, radius } = bounds(points)
  const scale = (Math.min(width, height) / 2 - pad) / radius
  return (p: P3, v: View) => {
    const q = project(
      { east: p.east - centre.east, north: p.north - centre.north, tvdss: p.tvdss - centre.tvdss },
      v,
    )
    return { x: width / 2 + q.x * scale, y: height / 2 + q.y * scale, z: q.z }
  }
}

interface Station {
  md_m: number
  east_m: number
  north_m: number
  tvdss_m: number
}

/** Position at a measured depth, linear between stations (for markers along the path). */
export function atMd(stations: Station[], md: number): P3 | null {
  if (stations.length === 0) return null
  const first = stations[0]!
  const last = stations[stations.length - 1]!
  if (md <= first.md_m) return { east: first.east_m, north: first.north_m, tvdss: first.tvdss_m }
  if (md >= last.md_m) return { east: last.east_m, north: last.north_m, tvdss: last.tvdss_m }
  let i = 1
  while (i < stations.length - 1 && stations[i]!.md_m < md) i++
  const a = stations[i - 1]!
  const b = stations[i]!
  const f = (md - a.md_m) / (b.md_m - a.md_m || 1)
  return {
    east: a.east_m + f * (b.east_m - a.east_m),
    north: a.north_m + f * (b.north_m - a.north_m),
    tvdss: a.tvdss_m + f * (b.tvdss_m - a.tvdss_m),
  }
}

/** Horizontal displacement at the last station and its azimuth (degrees from north). */
export function displacement(stations: Station[]) {
  const last = stations[stations.length - 1]
  if (!last) return { distance: 0, azimuth: 0 }
  const azimuth = ((Math.atan2(last.east_m, last.north_m) * 180) / Math.PI + 360) % 360
  return { distance: Math.hypot(last.east_m, last.north_m), azimuth }
}
