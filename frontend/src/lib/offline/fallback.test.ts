import { FakeCacheStorage } from './fakeCaches'
import { lookupPack, networkThenPack } from './fallback'
import { PACK_META_PATH, packCacheName } from './keys'

const ORIGIN = 'http://localhost:8080'
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

async function withPack(
  storage: FakeCacheStorage,
  entries: Record<string, unknown>,
  { complete = true, wellId = 3, stamp = 1 } = {},
) {
  const cache = await storage.open(packCacheName(wellId, stamp))
  for (const [key, body] of Object.entries(entries)) await cache.put(ORIGIN + key, json(body))
  if (complete) await cache.put(ORIGIN + PACK_META_PATH, json({ wellId }))
}

function deps(storage: FakeCacheStorage, fetch: (r: Request) => Promise<Response>) {
  return { fetch, caches: storage.asCacheStorage(), origin: ORIGIN, networkTimeoutMs: 50 }
}

const request = (path: string) => new Request(ORIGIN + path)
const down = async (): Promise<Response> => {
  throw new TypeError('Failed to fetch')
}

describe('network first, well pack when the network cannot answer', () => {
  it('returns the network answer when there is one, without touching the pack', async () => {
    const storage = new FakeCacheStorage()
    await withPack(storage, { '/api/v1/wells/3': { name: 'packed' } })
    const res = await networkThenPack(
      request('/api/v1/wells/3'),
      deps(storage, async () => json({ name: 'live' })),
    )
    expect(await res.json()).toEqual({ name: 'live' })
  })

  it('serves the packed copy when the network fails, matching the query in any order', async () => {
    const storage = new FakeCacheStorage()
    await withPack(storage, { '/api/v1/documents?limit=500&well_id=3': { total: 2 } })
    const res = await networkThenPack(
      request('/api/v1/documents?well_id=3&limit=500'),
      deps(storage, down),
    )
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ total: 2 })
  })

  it('serves the pack when the web server says the API behind it is down', async () => {
    const storage = new FakeCacheStorage()
    await withPack(storage, { '/api/v1/wells/3': { name: 'packed' } })
    const res = await networkThenPack(
      request('/api/v1/wells/3'),
      deps(storage, async () => json({}, 502)),
    )
    expect(await res.json()).toEqual({ name: 'packed' })
    // No pack for this one: the proxy's own answer comes through.
    const other = await networkThenPack(
      request('/api/v1/wells/9'),
      deps(storage, async () => json({}, 502)),
    )
    expect(other.status).toBe(502)
  })

  it('answers with the offline error envelope when nothing is packed', async () => {
    const storage = new FakeCacheStorage()
    const res = await networkThenPack(request('/api/v1/wells/3'), deps(storage, down))
    expect(res.status).toBe(503)
    const body = (await res.json()) as { error: { code: string; details: { path: string } } }
    expect(body.error.code).toBe('offline')
    expect(body.error.details.path).toBe('/api/v1/wells/3')
  })

  it('ignores a download that never finished (no meta entry)', async () => {
    const storage = new FakeCacheStorage()
    await withPack(storage, { '/api/v1/wells/3': { name: 'half' } }, { complete: false })
    expect(await lookupPack(ORIGIN + '/api/v1/wells/3', storage.asCacheStorage(), ORIGIN)).toBe(
      null,
    )
  })

  it('cuts a smaller-radius surface offsets answer from the packed 20 km one', async () => {
    const storage = new FakeCacheStorage()
    await withPack(storage, {
      '/api/v1/wells/3/offsets?mode=SURFACE&radius_km=20': {
        radius_km: 20,
        offsets: [
          { well_id: 4, distance_m: 2500 },
          { well_id: 5, distance_m: 8000 },
        ],
      },
    })
    const res = await networkThenPack(
      request('/api/v1/wells/3/offsets?radius_km=3&mode=SURFACE'),
      deps(storage, down),
    )
    const body = (await res.json()) as { radius_km: number; offsets: { well_id: number }[] }
    expect(body.radius_km).toBe(3)
    expect(body.offsets.map((o) => o.well_id)).toEqual([4])
  })

  it('gives way to the pack when the network hangs, and waits for it otherwise', async () => {
    const storage = new FakeCacheStorage()
    await withPack(storage, { '/api/v1/wells/3': { name: 'packed' } })
    const hang = () => new Promise<Response>(() => {})
    const res = await networkThenPack(request('/api/v1/wells/3'), deps(storage, hang))
    expect(await res.json()).toEqual({ name: 'packed' })

    let resolve: (r: Response) => void = () => {}
    const slow = () => new Promise<Response>((r) => (resolve = r))
    const pending = networkThenPack(request('/api/v1/wells/9'), deps(storage, slow))
    setTimeout(() => resolve(json({ name: 'slow but live' })), 80)
    expect(await (await pending).json()).toEqual({ name: 'slow but live' })
  })

  it('prefers the newest pack when two hold the same read', async () => {
    const storage = new FakeCacheStorage()
    await withPack(storage, { '/api/v1/formations': ['old'] }, { stamp: 1 })
    await withPack(storage, { '/api/v1/formations': ['new'] }, { stamp: 2, wellId: 4 })
    const res = await networkThenPack(request('/api/v1/formations'), deps(storage, down))
    expect(await res.json()).toEqual(['new'])
  })
})
