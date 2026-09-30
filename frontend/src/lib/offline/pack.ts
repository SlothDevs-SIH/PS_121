/**
 * Well pack downloader (FRONTEND_PLAN §12): fetches one well's knowledge reads into its own
 * Cache Storage cache, with progress, a size cap and a format version. The service worker
 * (./sw.ts via ./fallback.ts) serves them when the network is gone; ./packStore.ts lists and
 * removes them.
 *
 * A download writes a fresh cache and its meta entry last, then deletes the well's older
 * pack: a failed or cancelled download leaves the previous pack untouched.
 */
import type {
  CorrelationPanel,
  EventDetail,
  EventTimeline,
  OffsetsOut,
  PageOut,
  WellDetail,
} from '../api/client'
import { formatBytes } from '../format/units'
import {
  PACK_CAP_BYTES,
  PACK_META_PATH,
  PACK_RADIUS_KM,
  PACK_VERSION,
  packCacheName,
  packKey,
  parsePackCacheName,
} from './keys'
import { browserEnv, type PackEnv, type PackMeta } from './packStore'
import {
  coreUrls,
  correlationSets,
  correlationUrls,
  evidencePages,
  imageUrls,
  knowledgeUrls,
  wellUrls,
} from './plan'

export type PackPhase = 'well' | 'knowledge' | 'correlation' | 'evidence' | 'images'

export interface PackProgress {
  phase: PackPhase
  done: number
  /** Grows as each stage reveals the next reads. */
  total: number
  bytes: number
}

export type PackErrorKind = 'too-large' | 'network' | 'storage' | 'not-found' | 'aborted'

export class PackError extends Error {
  readonly kind: PackErrorKind
  constructor(kind: PackErrorKind, message: string) {
    super(message)
    this.name = 'PackError'
    this.kind = kind
  }
}

const CONCURRENCY = 4

async function pool<T>(items: T[], n: number, fn: (item: T) => Promise<void>): Promise<void> {
  let next = 0
  const worker = async () => {
    while (next < items.length) await fn(items[next++] as T)
  }
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, worker))
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

export interface DownloadOptions {
  onProgress?: (p: PackProgress) => void
  signal?: AbortSignal
  capBytes?: number
  env?: PackEnv
}

export async function downloadWellPack(
  wellId: number,
  { onProgress, signal, capBytes = PACK_CAP_BYTES, env = browserEnv() }: DownloadOptions = {},
): Promise<PackMeta> {
  const name = packCacheName(wellId, env.now())
  const cache = await env.caches.open(name)
  const answers = new Map<string, unknown>()
  const stored = new Set<string>()
  const progress: PackProgress = { phase: 'well', done: 0, total: 0, bytes: 0 }
  let entries = 0
  let missing = 0
  let imagesSkipped = 0
  const report = () => onProgress?.({ ...progress })
  const key = (url: string) => new URL(packKey(url), env.origin).href
  const tooLarge = () =>
    new PackError(
      'too-large',
      `This well's pack would pass the ${formatBytes(capBytes)} limit ` +
        `(${formatBytes(progress.bytes)} stored before stopping). Nothing was saved; ` +
        'any earlier pack for this well is kept.',
    )

  const get = async (url: string, image: boolean): Promise<Blob | null> => {
    signal?.throwIfAborted()
    let res: Response
    try {
      res = await env.fetch(url, {
        headers: image ? {} : { Accept: 'application/json' },
        credentials: 'same-origin',
        signal,
      })
    } catch (err) {
      if (isAbort(err) || signal?.aborted) throw err
      throw new PackError(
        'network',
        'The connection dropped while downloading. Nothing was saved; any earlier pack is kept.',
      )
    }
    if (!res.ok) {
      missing += 1
      return null
    }
    const blob = await res.blob()
    return image ? env.thumbnail(blob).catch(() => blob) : blob
  }

  /** False when the blob would pass the cap (nothing is written then). */
  const put = async (url: string, blob: Blob, contentType: string): Promise<boolean> => {
    if (progress.bytes + blob.size > capBytes) return false
    const headers = { 'Content-Type': blob.type || contentType }
    try {
      await cache.put(key(url), new Response(await blob.arrayBuffer(), { headers }))
    } catch {
      throw new PackError(
        'storage',
        'This device has no room left for the pack. Free some space or remove another pack.',
      )
    }
    progress.bytes += blob.size
    entries += 1
    return true
  }

  const stage = async (phase: PackPhase, urls: string[]) => {
    const fresh = [...new Set(urls)].filter((u) => !stored.has(packKey(u)))
    for (const u of fresh) stored.add(packKey(u))
    progress.phase = phase
    progress.total += fresh.length
    report()
    await pool(fresh, CONCURRENCY, async (url) => {
      const blob = await get(url, false)
      if (blob) {
        if (!(await put(url, blob, 'application/json'))) throw tooLarge()
        try {
          answers.set(packKey(url), JSON.parse(await blob.text()))
        } catch {
          // Stored as the server sent it; only planning needed it parsed.
        }
      }
      progress.done += 1
      report()
    })
  }
  const answer = <T>(url: string) => (answers.get(packKey(url)) as T | undefined) ?? null
  const answersUnder = <T>(prefix: string) =>
    [...answers.entries()].filter(([k]) => k.startsWith(prefix)).map(([, v]) => v as T)

  try {
    await stage('well', coreUrls(wellId))
    const well = answer<WellDetail>(wellUrls.well(wellId))
    if (!well)
      throw new PackError('not-found', 'This well could not be loaded, so no pack was made.')
    const offsets = answer<OffsetsOut>(wellUrls.offsets(wellId, PACK_RADIUS_KM))
    const timeline = answer<EventTimeline>(wellUrls.timeline(wellId))

    await stage('knowledge', knowledgeUrls(wellId, { well, offsets, timeline }))
    const tvdssPanels = correlationSets(wellId, offsets).flatMap((wells) => {
      const panel = answer<CorrelationPanel>(wellUrls.correlation(wells, 'TVDSS'))
      return panel ? [{ wells, panel }] : []
    })
    await stage('correlation', correlationUrls(tvdssPanels, stored))

    const pages = evidencePages({
      well,
      timeline,
      events: answersUnder<EventDetail>('/api/v1/events/'),
      panels: answersUnder<CorrelationPanel>('/api/v1/correlation?'),
    })
    await stage(
      'evidence',
      pages.map((p) => wellUrls.page(p.documentId, p.pageNo)),
    )

    // Page images are the bulk: once the cap is reached the rest are left out, not fatal.
    const images = imageUrls(answersUnder<PageOut>('/api/v1/documents/').filter((p) => p.image_url))
    progress.phase = 'images'
    progress.total += images.length
    report()
    for (const [i, url] of images.entries()) {
      const blob = await get(url, true)
      if (blob && !(await put(url, blob, 'image/png'))) {
        imagesSkipped = images.length - i
        progress.done += imagesSkipped
        report()
        break
      }
      progress.done += 1
      report()
    }

    const meta: PackMeta = {
      version: PACK_VERSION,
      wellId,
      wellName: well.name,
      createdAt: new Date(env.now()).toISOString(),
      bytes: progress.bytes,
      entries,
      missing,
      imagesSkipped,
      capBytes,
    }
    await cache.put(
      key(PACK_META_PATH),
      new Response(JSON.stringify(meta), { headers: { 'Content-Type': 'application/json' } }),
    )
    for (const other of await env.caches.keys())
      if (other !== name && parsePackCacheName(other)?.wellId === wellId)
        await env.caches.delete(other)
    return meta
  } catch (err) {
    await env.caches.delete(name)
    if (isAbort(err) || (signal?.aborted && !(err instanceof PackError)))
      throw new PackError('aborted', 'Download cancelled. Any earlier pack for this well is kept.')
    throw err
  }
}
