import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { resetUiStore } from '../stores/ui'
import { FakeWebSocket } from './fakeWebSocket'

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

vi.stubGlobal('WebSocket', FakeWebSocket)

afterEach(() => {
  cleanup()
  FakeWebSocket.reset()
  vi.unstubAllGlobals()
  vi.stubGlobal('WebSocket', FakeWebSocket)
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('data-mode')
  try {
    window.localStorage.clear()
  } catch {
    // ignore
  }
  resetUiStore()
})

// Pages are lazy chunks; under a parallel full run on a many-core machine (one jsdom
// per worker) the cold import behind a file's first render has been seen to pass 10 s.
// findBy* resolves as soon as the element appears, so this only bounds failures.
configure({ asyncUtilTimeout: 20000 })
