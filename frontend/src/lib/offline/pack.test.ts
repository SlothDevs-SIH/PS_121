import { FakeCacheStorage } from './fakeCaches'
import { lookupPack } from './fallback'
import { PACK_META_PATH, PACK_VERSION, packCacheName, packKey } from './keys'
import { downloadWellPack, PackError, type PackProgress } from './pack'
import { cleanupPacks, listPacks, packAge, removePack, type PackEnv } from './packStore'
import { wellUrls } from './plan'

const ORIGIN = 'http://localhost:8080'
const ev = (document_id: number, page_no: number) => ({ document_id, page_no, span_ids: [] })

/** A small synthetic backend for well 3 with one offset (4) and one cited report page. */
function backend(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const panel = {
    wells: [
      {
        well_id: 3,
        tracks: { formations: [{ name: 'Tipam', strat_order: 1 }], events: [] },
      },
    ],
  }
  const table: Record<string, unknown> = {
    [wellUrls.wells()]: { total: 2, items: [] },
    [wellUrls.well(3)]: {
      id: 3,
      name: 'SYN-ASM-03',
      formation_tops: [{ formation: 'Tipam' }],
      event_counts: { LOSS: 1 },
      recent_events: [],
      lessons: [{ event_id: 11, evidence: [ev(9, 1)] }],
    },
    [wellUrls.timeline(3)]: {
      events: [{ id: 11, evidence: [ev(9, 1)] }],
      counts_by_type: { LOSS: 1 },
    },
    [wellUrls.offsets(3, 20)]: {
      offsets: [{ well_id: 4, status: 'completed', distance_m: 2000 }],
    },
    [wellUrls.correlation([3, 4], 'TVDSS')]: panel,
    [wellUrls.event(11)]: { id: 11, evidence: [ev(9, 1)] },
    [wellUrls.page(9, 1)]: {
      document_id: 9,
      page_no: 1,
      image_url: '/api/v1/documents/9/pages/1/image',
      spans: [],
    },
    '/api/v1/documents/9/pages/1/image': 'IMAGE',
    ...overrides,
  }
  return Object.fromEntries(Object.entries(table).map(([k, v]) => [packKey(k), v]))
}

function env(
  storage: FakeCacheStorage,
  table: Record<string, unknown>,
  opts: { failAfter?: number; now?: number } = {},
): PackEnv & { calls: string[] } {
  const calls: string[] = []
  return {
    calls,
    caches: storage.asCacheStorage(),
    origin: ORIGIN,
    now: () => opts.now ?? 1_700_000_000_000,
    thumbnail: async (b) => b,
    fetch: async (input, init) => {
      const url = String(input)
      calls.push(url)
      init?.signal?.throwIfAborted()
      if (opts.failAfter !== undefined && calls.length > opts.failAfter)
        throw new TypeError('Failed to fetch')
      const body = table[packKey(url)]
      if (body === undefined) return new Response('{}', { status: 404 })
      if (typeof body === 'string')
        return new Response(body, { headers: { 'Content-Type': 'image/png' } })
      return new Response(JSON.stringify(body), {
        headers: { 'Content-Type': 'application/json' },
      })
    },
  }
}

describe('well pack manager', () => {
  it('downloads the planned reads with progress and serves them back by key', async () => {
    const storage = new FakeCacheStorage()
    const e = env(storage, backend())
    const seen: PackProgress[] = []
    const meta = await downloadWellPack(3, { env: e, onProgress: (p) => seen.push(p) })

    expect(meta).toMatchObject({
      version: PACK_VERSION,
      wellId: 3,
      wellName: 'SYN-ASM-03',
      createdAt: new Date(1_700_000_000_000).toISOString(),
      imagesSkipped: 0,
    })
    expect(meta.entries).toBeGreaterThanOrEqual(8)
    expect(meta.bytes).toBeGreaterThan(0)
    // Every stage reported, done never passes total and ends equal to it.
    expect(new Set(seen.map((p) => p.phase))).toEqual(
      new Set(['well', 'knowledge', 'correlation', 'evidence', 'images']),
    )
    for (const p of seen) expect(p.done).toBeLessThanOrEqual(p.total)
    const last = seen.at(-1)!
    expect(last.done).toBe(last.total)
    expect(last.bytes).toBe(meta.bytes)
    // Planned from earlier answers: the flattened panel, the cited page and its image.
    expect(e.calls).toContain(wellUrls.correlation([3, 4], 'FLATTEN_ON_TOP', 'Tipam'))
    expect(e.calls).toContain('/api/v1/documents/9/pages/1/image')
    // No read is fetched twice.
    expect(new Set(e.calls).size).toBe(e.calls.length)

    const cs = storage.asCacheStorage()
    const well = await lookupPack(`${ORIGIN}/api/v1/wells/3`, cs, ORIGIN)
    expect(((await well!.json()) as { name: string }).name).toBe('SYN-ASM-03')
    const image = await lookupPack(`${ORIGIN}/api/v1/documents/9/pages/1/image`, cs, ORIGIN)
    expect(await image!.text()).toBe('IMAGE')
    // Reads the server could not answer are counted, not stored.
    expect(meta.missing).toBeGreaterThan(0)
    expect(await lookupPack(`${ORIGIN}${wellUrls.riskProfile(3)}`, cs, ORIGIN)).toBeNull()
  })

  it('stops with a clear message when the data alone would pass the cap, keeping the old pack', async () => {
    const storage = new FakeCacheStorage()
    const old = await downloadWellPack(3, { env: env(storage, backend(), { now: 1000 }) })
    const big = backend({ [wellUrls.well(3)]: { id: 3, name: 'x'.repeat(5000) } })
    const err = await downloadWellPack(3, {
      env: env(storage, big, { now: 2000 }),
      capBytes: 4000,
    }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(PackError)
    expect((err as PackError).kind).toBe('too-large')
    expect((err as PackError).message).toMatch(/would pass the .* limit/)
    expect(await storage.keys()).toEqual([packCacheName(3, 1000)])
    expect(await listPacks(env(storage, {}))).toEqual([old])
  })

  it('leaves page images out once the cap is reached and says how many', async () => {
    const storage = new FakeCacheStorage()
    const table = backend({ '/api/v1/documents/9/pages/1/image': 'I'.repeat(50_000) })
    const meta = await downloadWellPack(3, { env: env(storage, table), capBytes: 20_000 })
    expect(meta.imagesSkipped).toBe(1)
    expect(meta.bytes).toBeLessThanOrEqual(20_000)
  })

  it('keeps the previous pack when the connection drops mid-download', async () => {
    const storage = new FakeCacheStorage()
    await downloadWellPack(3, { env: env(storage, backend(), { now: 1000 }) })
    const err = await downloadWellPack(3, {
      env: env(storage, backend(), { now: 2000, failAfter: 5 }),
    }).catch((e: unknown) => e)
    expect((err as PackError).kind).toBe('network')
    expect(await storage.keys()).toEqual([packCacheName(3, 1000)])
  })

  it('can be cancelled, and reports a full disk plainly', async () => {
    const storage = new FakeCacheStorage()
    const controller = new AbortController()
    controller.abort()
    const cancelled = await downloadWellPack(3, {
      env: env(storage, backend()),
      signal: controller.signal,
    }).catch((e: unknown) => e)
    expect((cancelled as PackError).kind).toBe('aborted')
    expect(await storage.keys()).toEqual([])

    storage.failPuts = true
    const full = await downloadWellPack(3, { env: env(storage, backend()) }).catch(
      (e: unknown) => e,
    )
    expect((full as PackError).kind).toBe('storage')
    expect(await storage.keys()).toEqual([])
  })

  it('refuses a well the server does not know', async () => {
    const storage = new FakeCacheStorage()
    const err = await downloadWellPack(99, { env: env(storage, backend()) }).catch(
      (e: unknown) => e,
    )
    expect((err as PackError).kind).toBe('not-found')
    expect(await storage.keys()).toEqual([])
  })

  it('replaces the well’s older pack on update and removes it on request', async () => {
    const storage = new FakeCacheStorage()
    await downloadWellPack(3, { env: env(storage, backend(), { now: 1000 }) })
    const newer = await downloadWellPack(3, { env: env(storage, backend(), { now: 2000 }) })
    expect(await storage.keys()).toEqual([packCacheName(3, 2000)])
    expect(await listPacks(env(storage, {}))).toEqual([newer])

    await removePack(3, env(storage, {}))
    expect(await storage.keys()).toEqual([])
    expect(await listPacks(env(storage, {}))).toEqual([])
  })

  it('is versioned: other formats are never listed and are cleaned up with stale downloads', async () => {
    const storage = new FakeCacheStorage()
    const current = await downloadWellPack(3, { env: env(storage, backend(), { now: 1000 }) })
    const stale = await storage.open(`smriti-pack-v${PACK_VERSION + 1}-well-5-1000`)
    await stale.put(ORIGIN + PACK_META_PATH, new Response(JSON.stringify({ wellId: 5 })))
    await storage.open(packCacheName(6, 10)) // abandoned long ago, no meta
    await storage.open(packCacheName(7, 4_000_000)) // still downloading, no meta yet
    await storage.open('workbox-precache-v2-x') // not ours

    const e = env(storage, {}, { now: 4_000_000 })
    expect((await listPacks(e)).map((p) => p.wellId)).toEqual([current.wellId])
    expect(await cleanupPacks(e)).toBe(2)
    expect((await storage.keys()).sort()).toEqual(
      [packCacheName(3, 1000), packCacheName(7, 4_000_000), 'workbox-precache-v2-x'].sort(),
    )
  })

  it('describes how old a pack is', () => {
    const t = Date.parse('2026-09-30T10:00:00Z')
    expect(packAge('2026-09-30T10:00:00Z', t + 20_000)).toBe('just now')
    expect(packAge('2026-09-30T10:00:00Z', t + 12 * 60_000)).toBe('12 min ago')
    expect(packAge('2026-09-30T10:00:00Z', t + 5 * 3600_000)).toBe('5 h ago')
    expect(packAge('2026-09-30T10:00:00Z', t + 3 * 86400_000)).toBe('3 d ago')
  })
})
