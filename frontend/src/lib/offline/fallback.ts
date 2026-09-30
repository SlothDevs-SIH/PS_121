/**
 * The service worker's answer for API reads (policy 'pack-fallback', see ./keys.ts): the
 * network first, and a downloaded well pack when the network cannot answer. Nothing here
 * writes to a cache: API responses are stored only by an explicit "Download well pack".
 * Kept free of service-worker globals so it runs under unit tests with fakes.
 */
import type { OffsetsOut } from '../api/client'
import {
  cutOffsets,
  isCurrentPackCache,
  offlineErrorBody,
  PACK_META_PATH,
  packKey,
  parsePackCacheName,
  widerOffsetsKey,
} from './keys'

export interface FallbackDeps {
  fetch: (request: Request) => Promise<Response>
  caches: CacheStorage
  origin: string
  /** A hanging request on a poor rig link gives way to the pack after this long. */
  networkTimeoutMs?: number
}

/** Proxy errors mean the API behind the web server is down: the pack may still answer. */
const UPSTREAM_DOWN = new Set([502, 503, 504])
const DEFAULT_TIMEOUT_MS = 6000

/** Complete packs of the current format, newest first (a pack is complete once it has meta). */
async function completePacks(caches: CacheStorage, origin: string): Promise<Cache[]> {
  const names = (await caches.keys())
    .filter(isCurrentPackCache)
    .sort((a, b) => (parsePackCacheName(b)?.stamp ?? 0) - (parsePackCacheName(a)?.stamp ?? 0))
  const out: Cache[] = []
  for (const name of names) {
    const cache = await caches.open(name)
    if (await cache.match(new URL(PACK_META_PATH, origin).href)) out.push(cache)
  }
  return out
}

/** The packed answer for `url`, exact or cut from a wider offsets answer; null if none. */
export async function lookupPack(
  url: string,
  caches: CacheStorage,
  origin: string,
): Promise<Response | null> {
  const packs = await completePacks(caches, origin)
  if (packs.length === 0) return null
  const key = new URL(packKey(url), origin).href
  for (const cache of packs) {
    const hit = await cache.match(key, { ignoreVary: true })
    if (hit) return hit
  }
  const wider = widerOffsetsKey(url)
  if (!wider) return null
  const radius = Number(new URL(url, origin).searchParams.get('radius_km'))
  for (const cache of packs) {
    const hit = await cache.match(new URL(wider, origin).href, { ignoreVary: true })
    if (!hit) continue
    const body = cutOffsets((await hit.json()) as OffsetsOut, radius)
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  return null
}

function offlineResponse(url: string): Response {
  return new Response(JSON.stringify(offlineErrorBody(new URL(url).pathname)), {
    status: 503,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  })
}

export async function networkThenPack(request: Request, deps: FallbackDeps): Promise<Response> {
  const timeoutMs = deps.networkTimeoutMs ?? DEFAULT_TIMEOUT_MS
  const network = deps.fetch(request)
  // If the pack answers first, a later network failure must not surface as unhandled.
  network.catch(() => undefined)
  let timer: ReturnType<typeof setTimeout> | undefined
  const slow = new Promise<'slow'>((resolve) => {
    timer = setTimeout(() => resolve('slow'), timeoutMs)
  })
  try {
    const first = await Promise.race([network, slow])
    if (first === 'slow') {
      const packed = await lookupPack(request.url, deps.caches, deps.origin)
      if (packed) return packed
      return await network
    }
    if (UPSTREAM_DOWN.has(first.status)) {
      return (await lookupPack(request.url, deps.caches, deps.origin)) ?? first
    }
    return first
  } catch {
    return (await lookupPack(request.url, deps.caches, deps.origin)) ?? offlineResponse(request.url)
  } finally {
    clearTimeout(timer)
  }
}
