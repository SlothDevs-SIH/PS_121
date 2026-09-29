/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server proxies API calls to the backend so the app always uses same-origin
// relative URLs (/api, /ws, /healthz, /readyz) — exactly like the nginx image in production.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': apiTarget,
      '/healthz': apiTarget,
      '/readyz': apiTarget,
      '/ws': { target: apiTarget.replace(/^http/, 'ws'), ws: true },
    },
  },
  // MapLibre (~1 MB) is its own lazily loaded chunk, fetched only by pages with a map.
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 1100,
    // Fonts stay files: the CSP allows font-src 'self' only, so no data: URI inlining.
    assetsInlineLimit: (file: string) => (/\.(woff2?|ttf|otf)$/.test(file) ? false : undefined),
  },
  // MapLibre's worker imports a shared chunk, so it is bundled as an ES module worker.
  worker: { format: 'es' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
})
