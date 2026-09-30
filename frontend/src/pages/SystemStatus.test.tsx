import { screen, within } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { META, ME, mockBackend, NOT_READY, READY, renderApp } from '../test/utils'

describe('System Status page', () => {
  it('lists readiness per component and the backend component registry', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    const table = await screen.findByTestId('readiness-table')
    expect(within(table).getByText('postgres')).toBeInTheDocument()
    expect(within(table).getAllByText('ok')).toHaveLength(3)
    expect(await screen.findByTestId('backend-phase')).toHaveTextContent('B0')
    const list = screen.getByTestId('component-list')
    expect(within(list).getByText('built · B0')).toBeInTheDocument()
    expect(within(list).getByText('planned · B1')).toBeInTheDocument()
    expect(screen.getByText('Local Developer (admin)')).toBeInTheDocument()
  })

  it('marks failing components as down', async () => {
    mockBackend({ '/readyz': NOT_READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    const table = await screen.findByTestId('readiness-table')
    expect(within(table).getByText('down')).toBeInTheDocument()
  })

  it('explains how to start the backend when it is unreachable', async () => {
    mockBackend({
      '/readyz': 'network-error',
      '/api/v1/meta': 'network-error',
      '/api/v1/me': 'network-error',
    })
    renderApp('/system')
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unreachable')
  })
})

describe('System Status: build and monitoring (B6)', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('shows the frontend build injected at build time', async () => {
    vi.stubEnv('VITE_GIT_SHA', 'abc1234')
    vi.stubEnv('VITE_APP_VERSION', '0.6.0')
    vi.stubEnv('VITE_BUILD_TIME', '2026-09-30T06:30:00Z')
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    expect(await screen.findByTestId('frontend-commit')).toHaveTextContent('abc1234')
    expect(screen.getByTestId('frontend-version')).toHaveTextContent('0.6.0')
    expect(screen.getByTestId('frontend-built-at')).toHaveTextContent('IST')
  })

  it('links Grafana when config.json names one', async () => {
    mockBackend({
      '/readyz': READY,
      '/api/v1/meta': META,
      '/api/v1/me': ME,
      '/config.json': {
        status: 200,
        body: {
          mapTileUrl: '',
          mapTileAttribution: '',
          grafanaUrl: 'https://grafana.example/d/smriti',
        },
      },
    })
    renderApp('/system')
    const link = await screen.findByTestId('grafana-link')
    expect(link).toHaveAttribute('href', 'https://grafana.example/d/smriti')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('says how to add Grafana when none is configured', async () => {
    vi.stubEnv('VITE_GIT_SHA', '')
    vi.stubEnv('VITE_APP_VERSION', '')
    mockBackend({
      '/readyz': READY,
      '/api/v1/meta': META,
      '/api/v1/me': ME,
      '/config.json': {
        status: 200,
        body: { mapTileUrl: '', mapTileAttribution: '', grafanaUrl: '' },
      },
    })
    renderApp('/system')
    expect(await screen.findByTestId('grafana-none')).toHaveTextContent('GRAFANA_URL')
    expect(screen.getByTestId('frontend-commit')).toHaveTextContent('dev')
    expect(screen.getByTestId('frontend-version')).toHaveTextContent('unversioned')
  })
})
