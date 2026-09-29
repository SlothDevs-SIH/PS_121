import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { resetUiStore } from '../stores/ui'

// jsdom has no WebGL: MapLibre is replaced by a small fake that keeps the data flow
// (sources, HTML markers, camera calls) observable. See src/test/fakeMaplibre.ts.
vi.mock('../lib/maplibre', () => import('./fakeMaplibre'))

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= NoopResizeObserver as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= function scrollIntoView() {}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('data-mode')
  try {
    window.localStorage.clear()
  } catch {
    // ignore
  }
  resetUiStore()
})
