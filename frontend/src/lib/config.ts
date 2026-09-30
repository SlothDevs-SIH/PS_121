import { useQuery } from '@tanstack/react-query'

/**
 * Runtime configuration served by the web server at /config.json (set from container
 * environment), so one image works online, offline and inside OIL's network.
 */
export interface RuntimeConfig {
  /** Leaflet tile URL template; empty = no basemap (offline / air-gapped). */
  mapTileUrl: string
  mapTileAttribution: string
  /** Grafana for this deployment (System Status links to it); empty = none configured. */
  grafanaUrl: string
}

const DEFAULTS: RuntimeConfig = { mapTileUrl: '', mapTileAttribution: '', grafanaUrl: '' }

/** Only http(s) URLs become a link: a javascript: or relative value is dropped. */
function httpUrl(value: string): string {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:' ? value : ''
  } catch {
    return ''
  }
}

/** Known keys with string values; anything else in the file is ignored. */
export function parseRuntimeConfig(raw: unknown): RuntimeConfig {
  if (typeof raw !== 'object' || raw === null) return DEFAULTS
  const obj = raw as Record<string, unknown>
  const str = (key: keyof RuntimeConfig) => {
    const v = obj[key]
    return typeof v === 'string' ? v.trim() : DEFAULTS[key]
  }
  return {
    mapTileUrl: str('mapTileUrl'),
    mapTileAttribution: str('mapTileAttribution'),
    grafanaUrl: httpUrl(str('grafanaUrl')),
  }
}

export async function fetchRuntimeConfig(): Promise<RuntimeConfig> {
  try {
    const r = await fetch('/config.json', { headers: { Accept: 'application/json' } })
    if (!r.ok) return DEFAULTS
    return parseRuntimeConfig(await r.json())
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

export interface BuildInfo {
  version: string | null
  commit: string
  /** Build time shown in IST with its suffix, or null when the build didn't record one. */
  builtAt: string | null
}

const IST = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** What was built, from the Docker build args (VITE_* at build time; "dev" locally). */
export function buildInfo(env: Partial<ImportMetaEnv> = import.meta.env): BuildInfo {
  const version = env.VITE_APP_VERSION?.trim()
  const time = env.VITE_BUILD_TIME?.trim() ? new Date(env.VITE_BUILD_TIME.trim()) : null
  return {
    version: version && version !== 'dev' ? version : null,
    commit: env.VITE_GIT_SHA?.trim() || 'dev',
    builtAt: time && !Number.isNaN(time.getTime()) ? `${IST.format(time)} IST` : null,
  }
}
