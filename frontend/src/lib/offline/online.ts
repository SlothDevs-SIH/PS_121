import { useSyncExternalStore } from 'react'

import { ApiError } from '../api/client'
import { useReadiness } from '../api/hooks'

function subscribe(onChange: () => void): () => void {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

/** The browser's own view of the network (false = no network interface is up). */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  )
}

/**
 * 'offline': the device has no network. 'unreachable': it has one, but the SMRITI server
 * cannot be reached at all (a rig tablet off the eRTMAC link, a phone unplugged from its
 * `adb reverse` tunnel). Either way only downloaded well packs can answer. A backend that
 * answers with an error is neither: the web server is there, so live data may return.
 */
export type Connectivity = 'online' | 'offline' | 'unreachable'

export function useConnectivity(): Connectivity {
  const online = useOnline()
  const ready = useReadiness()
  if (!online) return 'offline'
  if (ready.isError && ready.error instanceof ApiError && ready.error.status === 0)
    return 'unreachable'
  return 'online'
}

/** Screens that need the live link to the server near eRTMAC; unavailable offline. */
export const NEEDS_NETWORK: ReadonlySet<string> = new Set(['live', 'alerts', 'search', 'copilot'])
