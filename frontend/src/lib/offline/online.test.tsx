import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

import { Providers } from '../../app/providers'
import { makeQueryClient } from '../../app/queryClient'
import { mockBackend, READY } from '../../test/utils'
import { useConnectivity, useOnline } from './online'

afterEach(() => {
  window.dispatchEvent(new Event('online'))
})

function wrapper({ children }: { children: ReactNode }) {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false, refetchInterval: false } })
  return <Providers client={client}>{children}</Providers>
}

function setOnline(value: boolean) {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(value)
  act(() => {
    window.dispatchEvent(new Event(value ? 'online' : 'offline'))
  })
}

describe('online / offline hooks', () => {
  it('follows navigator.onLine and the online/offline events', () => {
    const { result } = renderHook(() => useOnline())
    expect(result.current).toBe(true)
    setOnline(false)
    expect(result.current).toBe(false)
    setOnline(true)
    expect(result.current).toBe(true)
  })

  it('is online when the server answers readiness', async () => {
    const fetchMock = mockBackend({ '/readyz': READY })
    const { result } = renderHook(() => useConnectivity(), { wrapper })
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(result.current).toBe('online')
  })

  it('is offline without a network, before any request', () => {
    mockBackend({ '/readyz': READY })
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    const { result } = renderHook(() => useConnectivity(), { wrapper })
    expect(result.current).toBe('offline')
  })

  it('is unreachable when the device has a network but the server cannot be reached', async () => {
    mockBackend({ '/readyz': 'network-error' })
    const { result } = renderHook(() => useConnectivity(), { wrapper })
    await waitFor(() => expect(result.current).toBe('unreachable'))
  })

  it('stays online when the web server answers with an error (the API may come back)', async () => {
    const fetchMock = mockBackend({ '/readyz': { status: 502, body: {} } })
    const { result } = renderHook(() => useConnectivity(), { wrapper })
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 20))
    expect(result.current).toBe('online')
  })
})
