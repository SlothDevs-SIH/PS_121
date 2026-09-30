import type { OffsetsOut } from '../api/client'
import {
  cutOffsets,
  isCurrentPackCache,
  isStalePackCache,
  PACK_VERSION,
  packCacheName,
  packKey,
  parsePackCacheName,
  requestPolicy,
  widerOffsetsKey,
} from './keys'

const ORIGIN = 'http://localhost:8080'
const policy = (path: string, method = 'GET', mode: RequestMode | '' = '') =>
  requestPolicy(method, new URL(path, ORIGIN), ORIGIN, mode)

describe('pack keys', () => {
  it('sorts query parameters by name but keeps repeated values in order', () => {
    expect(packKey('/api/v1/documents?well_id=3&limit=500')).toBe(
      '/api/v1/documents?limit=500&well_id=3',
    )
    expect(packKey('/api/v1/correlation?wells=7&wells=2&align=TVDSS')).toBe(
      '/api/v1/correlation?align=TVDSS&wells=7&wells=2',
    )
    expect(packKey('http://localhost:8080/api/v1/wells/3')).toBe('/api/v1/wells/3')
  })

  it('names one cache per download and tells current packs from stale formats', () => {
    const name = packCacheName(12, 1700000000000)
    expect(name).toBe(`smriti-pack-v${PACK_VERSION}-well-12-1700000000000`)
    expect(parsePackCacheName(name)).toEqual({
      version: PACK_VERSION,
      wellId: 12,
      stamp: 1700000000000,
    })
    expect(isCurrentPackCache(name)).toBe(true)
    expect(isStalePackCache(name)).toBe(false)
    const old = `smriti-pack-v${PACK_VERSION + 1}-well-12-1`
    expect(isCurrentPackCache(old)).toBe(false)
    expect(isStalePackCache(old)).toBe(true)
    expect(isStalePackCache('smriti-pack-garbage')).toBe(true)
    expect(isStalePackCache('workbox-precache-v2-http://x/')).toBe(false)
    expect(parsePackCacheName('smriti-runtime-config')).toBeNull()
  })
})

describe('service worker request policy', () => {
  it('keeps live, personal and search data network-only', () => {
    for (const path of [
      '/api/v1/alerts?limit=200',
      '/api/v1/alerts/4/dejavu',
      '/api/v1/analytics/alerts',
      '/api/v1/wells/3/realtime?minutes=30',
      '/api/v1/replay',
      '/api/v1/stream/status',
      '/api/v1/copilot/chat',
      '/api/v1/search?q=loss',
      '/api/v1/me',
      '/api/v1/auth/config',
      '/ws/live/3',
      '/readyz',
      '/healthz',
    ])
      expect(policy(path), path).toBe('network')
  })

  it('lets knowledge reads fall back to a pack, and nothing that is not a same-origin GET', () => {
    for (const path of [
      '/api/v1/wells?limit=500',
      '/api/v1/wells/3',
      '/api/v1/wells/3/offsets?radius_km=5&mode=SURFACE',
      '/api/v1/correlation?wells=3&align=TVDSS',
      '/api/v1/ledger?event_type=LOSS',
      '/api/v1/documents/9/pages/2/image',
    ])
      expect(policy(path), path).toBe('pack-fallback')
    expect(policy('/api/v1/wells/3', 'POST')).toBe('network')
    expect(requestPolicy('GET', new URL('https://tiles.example/1/2/3.png'), ORIGIN)).toBe('network')
  })

  it('answers SPA navigations with the shell and runtime config with its own route', () => {
    expect(policy('/wells/3', 'GET', 'navigate')).toBe('shell')
    expect(policy('/assets/index.js', 'GET', 'no-cors')).toBe('network')
    expect(policy('/config.json')).toBe('runtime-config')
  })
})

describe('offsets cut from the packed wider answer', () => {
  const packed = {
    well_id: 3,
    mode: 'SURFACE',
    radius_km: 20,
    distance_label: 'surface',
    excluded: [],
    offsets: [
      { well_id: 4, distance_m: 900 },
      { well_id: 5, distance_m: 4999 },
      { well_id: 6, distance_m: 12000 },
    ],
  } as unknown as OffsetsOut

  it('maps a smaller surface radius to the packed 20 km key', () => {
    expect(widerOffsetsKey('/api/v1/wells/3/offsets?radius_km=5&mode=SURFACE')).toBe(
      '/api/v1/wells/3/offsets?mode=SURFACE&radius_km=20',
    )
    expect(widerOffsetsKey('/api/v1/wells/3/offsets?radius_km=25&mode=SURFACE')).toBeNull()
    expect(
      widerOffsetsKey('/api/v1/wells/3/offsets?radius_km=5&mode=AT_FORMATION&formation=Ty'),
    ).toBeNull()
    expect(widerOffsetsKey('/api/v1/wells/3')).toBeNull()
  })

  it('keeps only the offsets inside the asked radius', () => {
    const cut = cutOffsets(packed, 5)
    expect(cut.radius_km).toBe(5)
    expect(cut.offsets.map((o) => o.well_id)).toEqual([4, 5])
    expect(packed.offsets).toHaveLength(3)
  })
})
