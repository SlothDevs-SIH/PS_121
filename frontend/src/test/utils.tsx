import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'

import { Providers } from '../app/providers'
import { makeQueryClient } from '../app/queryClient'
import { routes } from '../app/router'

type Route = { status: number; body: unknown } | 'network-error'

/** Replace global fetch with a table of path → response (path match ignores the query). */
export function mockBackend(table: Record<string, Route>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    const key = Object.keys(table).find((k) => url === k || url.split('?')[0] === k)
    const route = key
      ? table[key]
      : {
          status: 404,
          body: { error: { code: 'not_found', message: 'nf', details: {}, request_id: 'r' } },
        }
    if (route === 'network-error' || route === undefined) throw new TypeError('Failed to fetch')
    return new Response(JSON.stringify(route.body), {
      status: route.status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function renderApp(path: string) {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false, refetchInterval: false } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  return render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
  )
}

export const READY = {
  status: 200,
  body: {
    status: 'ready',
    components: [
      { name: 'postgres', ok: true, latency_ms: 3.1, detail: 'extensions ok' },
      { name: 'redis', ok: true, latency_ms: 1.0, detail: 'ping ok' },
      { name: 'object_storage', ok: true, latency_ms: 2.0, detail: 'buckets ok' },
    ],
  },
}

export const NOT_READY = {
  status: 503,
  body: {
    status: 'not_ready',
    components: [
      { name: 'postgres', ok: true, latency_ms: 3.1, detail: 'extensions ok' },
      { name: 'redis', ok: false, latency_ms: 2000, detail: 'ConnectionError' },
    ],
  },
}

export const META = {
  status: 200,
  body: {
    name: 'SMRITI backend',
    version: '0.1.0',
    git_sha: 'abc1234',
    env: 'dev',
    backend_phase: 'B0',
    components: [
      { key: 'platform', stage: '-', name: 'Skeleton', phase: 'B0', status: 'built' },
      {
        key: 'ingest',
        stage: 'S1',
        name: 'Document ingestion & OCR',
        phase: 'B1',
        status: 'planned',
      },
    ],
  },
}

export const ME = {
  status: 200,
  body: { user_id: 'dev', name: 'Local Developer', roles: ['admin'] },
}

export function notImplemented(phase: string) {
  return {
    status: 501,
    body: {
      error: {
        code: 'not_implemented',
        message: `planned for ${phase}`,
        details: { feature: 'x', phase },
        request_id: 'req-1',
      },
    },
  }
}
