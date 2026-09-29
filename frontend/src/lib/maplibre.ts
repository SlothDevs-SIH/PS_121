/**
 * MapLibre, configured for the app's strict same-origin CSP: the worker is bundled by Vite
 * as its own same-origin ES module file (no blob: URL), and MapLibre is told where it is.
 * Tests replace this module (jsdom has no WebGL): see src/test/setup.ts.
 */
import 'maplibre-gl/dist/maplibre-gl.css'

import { setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

setWorkerUrl(workerUrl)

export {
  GeoJSONSource,
  LngLatBounds,
  Map,
  Marker,
  NavigationControl,
  ScaleControl,
} from 'maplibre-gl'
