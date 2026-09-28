import { ApiError, apiFetch, fetchReadiness } from './client'
import { mockBackend, NOT_READY, notImplemented, READY } from '../../test/utils'

describe('apiFetch', () => {
  it('returns parsed JSON on 2xx', async () => {
    mockBackend({ '/api/v1/me': { status: 200, body: { user_id: 'dev' } } })
    await expect(apiFetch('/api/v1/me')).resolves.toEqual({ user_id: 'dev' })
  })

  it('turns the backend error envelope into an ApiError with the planned phase', async () => {
    mockBackend({ '/api/v1/wells': notImplemented('B1') })
    const err = await apiFetch('/api/v1/wells').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    const apiErr = err as ApiError
    expect(apiErr.status).toBe(501)
    expect(apiErr.code).toBe('not_implemented')
    expect(apiErr.plannedPhase).toBe('B1')
    expect(apiErr.requestId).toBe('req-1')
  })

  it('handles non-envelope error bodies', async () => {
    mockBackend({ '/x': { status: 502, body: 'bad gateway' } })
    const err = (await apiFetch('/x').catch((e: unknown) => e)) as ApiError
    expect(err.status).toBe(502)
    expect(err.code).toBe('http_error')
    expect(err.plannedPhase).toBeNull()
  })

  it('reports network failures as status 0 / network_error', async () => {
    mockBackend({ '/api/v1/meta': 'network-error' })
    const err = (await apiFetch('/api/v1/meta').catch((e: unknown) => e)) as ApiError
    expect(err.status).toBe(0)
    expect(err.code).toBe('network_error')
  })
})

describe('fetchReadiness', () => {
  it('returns the report on 200', async () => {
    mockBackend({ '/readyz': READY })
    await expect(fetchReadiness()).resolves.toMatchObject({ status: 'ready' })
  })

  it('returns the report on 503 instead of throwing', async () => {
    mockBackend({ '/readyz': NOT_READY })
    await expect(fetchReadiness()).resolves.toMatchObject({ status: 'not_ready' })
  })
})
