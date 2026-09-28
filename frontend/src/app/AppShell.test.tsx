import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { META, ME, mockBackend, NOT_READY, notImplemented, READY, renderApp } from '../test/utils'
import { screensFor } from './screens'

describe('App shell', () => {
  it('redirects / to System Status and shows every office screen in the nav', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'System Status' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    for (const s of screensFor('office')) {
      expect(within(nav).getByText(s.title)).toBeInTheDocument()
    }
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

  it('cycles theme system → light → dark and sets data-theme', async () => {
    mockBackend({ '/readyz': READY, '/api/v1/meta': META, '/api/v1/me': ME })
    renderApp('/system')
    const toggle = await screen.findByTestId('theme-toggle')
    await userEvent.click(toggle)
    expect(document.documentElement.dataset.theme).toBe('light')
    await userEvent.click(toggle)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(window.localStorage.getItem('smriti.theme')).toBe('dark')
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

  it('renders planned screens with their phase and live endpoint probes', async () => {
    mockBackend({
      '/readyz': READY,
      '/api/v1/wells': notImplemented('B1'),
      '/api/v1/wells/1/offsets': notImplemented('B1'),
    })
    renderApp('/map')
    expect(await screen.findByRole('heading', { name: 'Well Map' })).toBeInTheDocument()
    expect(screen.getByTestId('planned-phase')).toHaveTextContent('frontend phase F1')
    expect(await screen.findAllByText('501 · backend phase B1')).toHaveLength(2)
  })
})
