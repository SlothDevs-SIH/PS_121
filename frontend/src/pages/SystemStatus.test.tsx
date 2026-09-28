import { screen, within } from '@testing-library/react'

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
