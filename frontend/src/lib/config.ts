import { useQuery } from '@tanstack/react-query'

/**
 * Runtime configuration served by the web server at /config.json (set from container
 * environment), so one image works online, offline and inside OIL's network.
 */
export interface RuntimeConfig {
  /** Leaflet tile URL template; empty = no basemap (offline / air-gapped). */
  mapTileUrl: string
  mapTileAttribution: string
}

const DEFAULTS: RuntimeConfig = { mapTileUrl: '', mapTileAttribution: '' }

export async function fetchRuntimeConfig(): Promise<RuntimeConfig> {
  try {
    const r = await fetch('/config.json', { headers: { Accept: 'application/json' } })
    if (!r.ok) return DEFAULTS
    return { ...DEFAULTS, ...((await r.json()) as Partial<RuntimeConfig>) }
  } catch {
    return DEFAULTS
  }
}

export function useRuntimeConfig() {
  return useQuery({
    queryKey: ['runtime-config'],
    queryFn: fetchRuntimeConfig,
    staleTime: Infinity,
  })
}
