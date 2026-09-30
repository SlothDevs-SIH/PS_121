import { cleanupPacks, packSupported } from './packStore'
import { usePwaStore } from './pwa'

const UPDATE_CHECK_MS = 60 * 60_000

/**
 * Registers the service worker built from ./sw.ts (production builds only: the dev server
 * has none, so development never serves stale code). A new version waits until the user
 * picks "Reload" in the update prompt, so a page is never swapped out mid-task.
 */
export async function registerServiceWorker(): Promise<void> {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return
  const { Workbox } = await import('workbox-window')
  const wb = new Workbox('/sw.js', { scope: '/' })
  wb.addEventListener('waiting', () => {
    usePwaStore.getState().setUpdate(() => {
      wb.addEventListener('controlling', () => window.location.reload())
      wb.messageSkipWaiting()
    })
  })
  void wb.register().then((reg) => {
    if (reg) setInterval(() => void reg.update().catch(() => undefined), UPDATE_CHECK_MS)
  })
  if (packSupported()) void cleanupPacks().catch(() => undefined)
}
