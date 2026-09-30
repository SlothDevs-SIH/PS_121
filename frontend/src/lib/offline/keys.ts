/**
 * Offline well pack (FRONTEND_PLAN §12): the names and rules shared by the page, which
 * downloads a pack, and the service worker, which serves it once the network is gone.
 * Pure functions only: this module is bundled into the service worker (./sw.ts), so it must
 * not touch the DOM, React or the API client at runtime.
 */
import type { OffsetsOut } from '../api/client'

/** Bump when the stored shape changes: packs of another version are deleted, never read. */
export const PACK_VERSION = 1
/** ~50 MB per well (FRONTEND_PLAN §12). */
export const PACK_CAP_BYTES = 50 * 1024 * 1024
/** Offsets are packed once at the widest radius the map allows; smaller radii are filtered. */
export const PACK_RADIUS_KM = 20
/** Where each pack keeps its own description (well, time, size); written last. */
export const PACK_META_PATH = '/__smriti/pack-meta.json'

const PACK_ROOT = 'smriti-pack-'
const PACK_NAME = /^smriti-pack-v(\d+)-well-(\d+)-(\d+)$/

/** One Cache Storage cache per download, so a failed download never damages the last pack. */
export function packCacheName(wellId: number, stamp: number): string {
  return `${PACK_ROOT}v${PACK_VERSION}-well-${wellId}-${stamp}`
}

export function parsePackCacheName(
  name: string,
): { version: number; wellId: number; stamp: number } | null {
  const m = PACK_NAME.exec(name)
  if (!m) return null
  return { version: Number(m[1]), wellId: Number(m[2]), stamp: Number(m[3]) }
}

export function isCurrentPackCache(name: string): boolean {
  return parsePackCacheName(name)?.version === PACK_VERSION
}

/** A pack cache from another pack format (or a malformed name): delete it. */
export function isStalePackCache(name: string): boolean {
  return name.startsWith(PACK_ROOT) && !isCurrentPackCache(name)
}

/**
 * The storage key of an API URL: path plus query parameters sorted by name. Values of a
 * repeated parameter keep their order (the correlation panel's first well is the subject).
 */
export function packKey(url: string): string {
  const u = new URL(url, 'http://pack.invalid')
  const params: [string, string][] = []
  u.searchParams.forEach((value, name) => params.push([name, value]))
  params.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
  const q = new URLSearchParams(params).toString()
  return q ? `${u.pathname}?${q}` : u.pathname
}

/**
 * Live and personal data never come from a pack, even offline, so it is never shown stale:
 * alerts, the real-time window, replay, stream status, copilot, search, sign-in and users.
 */
const NETWORK_ONLY_API = [
  /^\/api\/v1\/(alerts|analytics\/alerts|audit|auth|copilot|replay|search|stream|users)(\/|$)/,
  /^\/api\/v1\/me$/,
  /^\/api\/v1\/wells\/\d+\/realtime(\/|$)/,
]

export type RequestPolicy =
  /** SPA navigation: answered with the precached index.html. */
  | 'shell'
  /** Network first; a downloaded well pack answers when the network cannot. */
  | 'pack-fallback'
  /** Runtime configuration: network first, last good copy offline. */
  | 'runtime-config'
  /** Left to the browser (network only). */
  | 'network'

/** What the service worker does with a request it sees. Only same-origin GETs are touched. */
export function requestPolicy(
  method: string,
  url: URL,
  origin: string,
  mode: RequestMode | '' = '',
): RequestPolicy {
  if (method !== 'GET' || url.origin !== origin) return 'network'
  const p = url.pathname
  if (p.startsWith('/api/')) {
    return NETWORK_ONLY_API.some((re) => re.test(p)) ? 'network' : 'pack-fallback'
  }
  if (p === '/config.json') return 'runtime-config'
  if (p.startsWith('/ws/') || /^\/(healthz|readyz|nginx-health)$/.test(p)) return 'network'
  return mode === 'navigate' ? 'shell' : 'network'
}

/** Paths the SPA navigation route must leave to the server. */
export const NAVIGATION_DENYLIST = [
  /^\/api\//,
  /^\/ws\//,
  /^\/(healthz|readyz|nginx-health)$/,
  /^\/config\.json$/,
  /^\/__smriti\//,
]

const OFFSETS_PATH = /^\/api\/v1\/wells\/\d+\/offsets$/

/**
 * For a surface-offsets request at radius r ≤ PACK_RADIUS_KM, the key of the packed wider
 * request it can be cut from. The other proximity modes list wells they could not measure
 * without a distance, so they cannot be cut down and are only served for their exact URL.
 */
export function widerOffsetsKey(url: string): string | null {
  const u = new URL(url, 'http://pack.invalid')
  if (!OFFSETS_PATH.test(u.pathname)) return null
  if ((u.searchParams.get('mode') ?? 'SURFACE') !== 'SURFACE') return null
  const r = Number(u.searchParams.get('radius_km'))
  if (!(r > 0 && r <= PACK_RADIUS_KM)) return null
  u.searchParams.set('radius_km', String(PACK_RADIUS_KM))
  u.searchParams.set('mode', 'SURFACE')
  return packKey(`${u.pathname}${u.search}`)
}

/** The surface offsets within `radiusKm`, cut from a packed wider answer. */
export function cutOffsets(packed: OffsetsOut, radiusKm: number): OffsetsOut {
  return {
    ...packed,
    radius_km: radiusKm,
    offsets: packed.offsets.filter((o) => o.distance_m <= radiusKm * 1000),
  }
}

/** The error the API client shows for data that is neither online nor in a pack. */
export function offlineErrorBody(path: string) {
  return {
    error: {
      code: 'offline',
      message: 'Offline, and this is not in a downloaded well pack.',
      details: { path },
      request_id: null,
    },
  }
}
