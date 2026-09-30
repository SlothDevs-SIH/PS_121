/**
 * Downloaded well packs on this device (FRONTEND_PLAN §12): list, remove and clean up. Kept
 * apart from the downloader (./pack.ts, loaded only when a download starts) so the shell's
 * offline banner stays light.
 */
import { isCurrentPackCache, isStalePackCache, PACK_META_PATH, parsePackCacheName } from './keys'

export interface PackMeta {
  version: number
  wellId: number
  wellName: string
  /** When the download finished (ISO 8601). */
  createdAt: string
  bytes: number
  entries: number
  /** Reads the server did not answer (e.g. no risk profile yet): offline they fail as online. */
  missing: number
  /** Page images left out to stay under the cap. */
  imagesSkipped: number
  capBytes: number
}

export interface PackEnv {
  fetch: typeof fetch
  caches: CacheStorage
  origin: string
  now: () => number
  /** Shrinks a report page image to a small thumbnail (identity where unsupported). */
  thumbnail: (blob: Blob) => Promise<Blob>
}

const THUMB_WIDTH = 900
const INCOMPLETE_TTL_MS = 60 * 60_000

/** Packs need Cache Storage (secure context) and a service worker to serve them offline. */
export function packSupported(): boolean {
  return (
    typeof caches !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator
  )
}

/** A page image at most THUMB_WIDTH wide, as WebP where the browser can encode it. */
export async function shrinkImage(blob: Blob, maxWidth = THUMB_WIDTH): Promise<Blob> {
  if (typeof createImageBitmap !== 'function' || typeof OffscreenCanvas === 'undefined') return blob
  const bitmap = await createImageBitmap(blob)
  try {
    if (bitmap.width <= maxWidth) return blob
    const height = Math.round((bitmap.height * maxWidth) / bitmap.width)
    const canvas = new OffscreenCanvas(maxWidth, height)
    const ctx = canvas.getContext('2d')
    if (!ctx) return blob
    ctx.drawImage(bitmap, 0, 0, maxWidth, height)
    const out = await canvas.convertToBlob({ type: 'image/webp', quality: 0.75 })
    return out.size < blob.size ? out : blob
  } finally {
    bitmap.close()
  }
}

export function browserEnv(): PackEnv {
  return {
    fetch: (input, init) => fetch(input, init),
    caches,
    origin: window.location.origin,
    now: () => Date.now(),
    thumbnail: (b) => shrinkImage(b),
  }
}

/** "just now", "12 min ago", "3 h ago", "2 d ago": how old a pack's data is. */
export function packAge(createdAt: string, now = Date.now()): string {
  const min = Math.max(0, Math.floor((now - Date.parse(createdAt)) / 60_000))
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  if (min < 48 * 60) return `${Math.floor(min / 60)} h ago`
  return `${Math.floor(min / 1440)} d ago`
}

async function readMeta(cache: Cache, origin: string): Promise<PackMeta | null> {
  const hit = await cache.match(new URL(PACK_META_PATH, origin).href)
  if (!hit) return null
  try {
    return (await hit.json()) as PackMeta
  } catch {
    return null
  }
}

/** Complete packs of the current format, one per well (the newest), by well name. */
export async function listPacks(env: PackEnv = browserEnv()): Promise<PackMeta[]> {
  const byWell = new Map<number, PackMeta>()
  for (const name of await env.caches.keys()) {
    if (!isCurrentPackCache(name)) continue
    const meta = await readMeta(await env.caches.open(name), env.origin)
    if (!meta) continue
    const prev = byWell.get(meta.wellId)
    if (!prev || prev.createdAt < meta.createdAt) byWell.set(meta.wellId, meta)
  }
  return [...byWell.values()].sort((a, b) => a.wellName.localeCompare(b.wellName))
}

export async function removePack(wellId: number, env: PackEnv = browserEnv()): Promise<void> {
  for (const name of await env.caches.keys())
    if (parsePackCacheName(name)?.wellId === wellId) await env.caches.delete(name)
}

/**
 * Deletes packs of another format version, downloads that never finished (no meta after an
 * hour) and older duplicates of a well. Returns how many caches were deleted.
 */
export async function cleanupPacks(env: PackEnv = browserEnv()): Promise<number> {
  let deleted = 0
  const newest = new Map<number, number>()
  const complete: { name: string; wellId: number; stamp: number }[] = []
  for (const name of await env.caches.keys()) {
    if (isStalePackCache(name)) {
      await env.caches.delete(name)
      deleted += 1
      continue
    }
    const parsed = parsePackCacheName(name)
    if (!parsed) continue
    if (!(await readMeta(await env.caches.open(name), env.origin))) {
      if (env.now() - parsed.stamp > INCOMPLETE_TTL_MS) {
        await env.caches.delete(name)
        deleted += 1
      }
      continue
    }
    complete.push({ name, ...parsed })
    newest.set(parsed.wellId, Math.max(newest.get(parsed.wellId) ?? 0, parsed.stamp))
  }
  for (const c of complete)
    if (c.stamp < (newest.get(c.wellId) ?? 0)) {
      await env.caches.delete(c.name)
      deleted += 1
    }
  return deleted
}
