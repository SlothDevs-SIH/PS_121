/// <reference lib="webworker" />
/**
 * SMRITI service worker (FRONTEND_PLAN §12, ADR-F20), built by vite-plugin-pwa
 * (injectManifest) into /sw.js:
 *   - precaches the app shell (HTML, JS, CSS, fonts, icons) so the app opens with no network;
 *   - SPA navigations get the precached index.html;
 *   - API reads go to the network first and fall back to a downloaded well pack (./fallback.ts);
 *     live data (alerts, real-time, replay, stream, copilot, search, sign-in) is never
 *     intercepted, and no API response is cached here: only "Download well pack" stores them;
 *   - /config.json is network first with its last good copy offline.
 * A new version waits until the page asks it to take over (the "Update available" prompt).
 */
import {
  cleanupOutdatedCaches,
  createHandlerBoundToURL,
  precacheAndRoute,
} from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { NetworkFirst } from 'workbox-strategies'

import { networkThenPack } from './fallback'
import { isStalePackCache, NAVIGATION_DENYLIST, requestPolicy } from './keys'

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: (string | { url: string })[] }

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

registerRoute(
  new NavigationRoute(createHandlerBoundToURL('/index.html'), { denylist: NAVIGATION_DENYLIST }),
)

registerRoute(
  ({ url, request }) =>
    requestPolicy(request.method, url, self.location.origin, request.mode) === 'runtime-config',
  new NetworkFirst({ cacheName: 'smriti-runtime-config', networkTimeoutSeconds: 4 }),
)

registerRoute(
  ({ url, request }) =>
    requestPolicy(request.method, url, self.location.origin, request.mode) === 'pack-fallback',
  ({ request }) =>
    networkThenPack(request, {
      fetch: (r) => fetch(r),
      caches: self.caches,
      origin: self.location.origin,
    }),
)

self.addEventListener('message', (event) => {
  if ((event.data as { type?: string } | null)?.type === 'SKIP_WAITING') void self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await self.caches.keys())
        if (isStalePackCache(name)) await self.caches.delete(name)
    })(),
  )
})
