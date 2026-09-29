import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import {
  fullBackend,
  META,
  ME,
  mockBackend,
  NOT_READY,
  notImplemented,
  READY,
  renderApp,
} from '../test/utils'
import { screensFor } from './screens'

describe('App shell', () => {
  it('opens on the Dashboard and lists every office screen in the sidebar', async () => {
    fullBackend()
    renderApp('/')
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    for (const s of screensFor('office')) {
      expect(within(nav).getByText(s.title)).toBeInTheDocument()
    }
    expect(screen.getByTestId('breadcrumb-current')).toHaveTextContent('Dashboard')
  })

  it('shows per-fluid well counts in the sidebar', async () => {
    fullBackend()
    renderApp('/system')
    await waitFor(() => expect(screen.getByTestId('well-count-oil')).toHaveTextContent('2'))
    expect(screen.getByTestId('well-count-gas')).toHaveTextContent('1')
    expect(screen.getByTestId('well-count-water')).toHaveTextContent('0')
  })

  it('shows backend ready / degraded / unreachable in the header', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    const { unmount } = renderApp('/system')
    expect(await screen.findByText('Backend ready')).toBeInTheDocument()
    unmount()

    mockBackend({ '/readyz': NOT_READY, '/api/v1/meta': META, '/api/v1/me': ME })
    const second = renderApp('/system')
    expect(await screen.findByText('Degraded: redis')).toBeInTheDocument()
    second.unmount()

    mockBackend({
      '/readyz': 'network-error',
      '/api/v1/meta': 'network-error',
      '/api/v1/me': 'network-error',
    })
    renderApp('/system')
    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })

  it('switches to field view: larger type attribute and reduced nav, remembered', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    await userEvent.click(await screen.findByTestId('mode-toggle'))
    expect(document.documentElement.dataset.mode).toBe('field')
    expect(window.localStorage.getItem('smriti.mode')).toBe('field')
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).queryByText('Admin')).not.toBeInTheDocument()
    expect(within(nav).getByText('Live Well Monitor')).toBeInTheDocument()
  })

  it('defaults to Deep Rig and cycles Daylight Field → Command Blue, remembered', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    const toggle = await screen.findByTestId('theme-toggle')
    expect(document.documentElement.dataset.theme).toBe('deep-rig')
    await userEvent.click(toggle)
    expect(document.documentElement.dataset.theme).toBe('daylight')
    await userEvent.click(toggle)
    expect(document.documentElement.dataset.theme).toBe('command-blue')
    expect(window.localStorage.getItem('smriti.theme')).toBe('command-blue')
    await userEvent.click(toggle)
    expect(document.documentElement.dataset.theme).toBe('deep-rig')
  })

  it('collapses the sidebar to a rail and remembers it (wide screens only)', async () => {
    vi.stubGlobal(
      'matchMedia',
      (q: string) =>
        ({
          matches: q.includes('min-width: 1024px'),
          addEventListener: () => {},
          removeEventListener: () => {},
        }) as unknown as MediaQueryList,
    )
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    const shell = await screen.findByTestId('app-shell')
    expect(shell).toHaveAttribute('data-sidebar', 'full')
    await userEvent.click(screen.getByTestId('sidebar-toggle'))
    expect(shell).toHaveAttribute('data-sidebar', 'rail')
    expect(window.localStorage.getItem('smriti.sidebar')).toBe('rail')
    await userEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }))
    expect(shell).toHaveAttribute('data-sidebar', 'full')
  })

  it('has no collapse toggle when the window is too narrow to choose', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    expect(await screen.findByTestId('app-shell')).toHaveAttribute('data-sidebar', 'rail')
    expect(screen.queryByTestId('sidebar-toggle')).not.toBeInTheDocument()
  })

  it('still renders when localStorage throws', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    await userEvent.click(await screen.findByTestId('mode-toggle'))
    expect(document.documentElement.dataset.mode).toBe('field')
    expect(getItem).toHaveBeenCalled()
  })

  it('shows a not-found page for unknown routes', async () => {
    mockBackend({ '/readyz': READY })
    renderApp('/does-not-exist')
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('redirects the Part 1 /ingest link to the Documents Library', async () => {
    fullBackend()
    renderApp('/ingest')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Documents Library' }),
    ).toBeInTheDocument()
  })

  it('renders planned screens with their phase and live endpoint probes', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/alerts': notImplemented('B5') })
    renderApp('/alerts')
    expect(await screen.findByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
    expect(screen.getByTestId('planned-phase')).toHaveTextContent('frontend phase F4')
    expect(await screen.findAllByText('501 · backend phase B5')).toHaveLength(1)
  })
})
