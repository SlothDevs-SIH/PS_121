import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { fullBackend, renderApp } from '../../test/utils'
import { networkScreenAt } from './OfflineGate'

afterEach(() => {
  // TanStack Query's online manager is a module singleton: leave it online for the next test.
  window.dispatchEvent(new Event('online'))
})

function setOnline(value: boolean) {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(value)
  act(() => {
    window.dispatchEvent(new Event(value ? 'online' : 'offline'))
  })
}

describe('Live-only screens without the connection', () => {
  it('knows which paths need the live server', () => {
    expect(networkScreenAt('/live')?.id).toBe('live')
    expect(networkScreenAt('/alerts')?.id).toBe('alerts')
    expect(networkScreenAt('/search')?.id).toBe('search')
    for (const path of ['/', '/map', '/wells/3', '/correlation', '/ledger', '/system'])
      expect(networkScreenAt(path), path).toBeNull()
  })

  it('explains instead of failing when opened offline, and opens once back online', async () => {
    fullBackend()
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    renderApp('/alerts')
    const gate = await screen.findByTestId('offline-gate')
    expect(within(gate).getByRole('heading', { level: 1 })).toHaveTextContent('Alerts')
    expect(gate).toHaveTextContent(
      'This screen needs the connection: live alerts need the link to the server near eRTMAC.',
    )
    expect(within(gate).getByRole('link', { name: 'Open the Map Explorer' })).toHaveAttribute(
      'href',
      '/map',
    )

    setOnline(true)
    await waitFor(() => expect(screen.queryByTestId('offline-gate')).not.toBeInTheDocument())
    expect(await screen.findByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
  })

  it('leaves a screen that was open when the link dropped to its own reconnecting state', async () => {
    fullBackend()
    renderApp('/alerts')
    await screen.findByRole('heading', { level: 1, name: 'Alerts' })
    setOnline(false)
    await screen.findByTestId('offline-banner')
    expect(screen.queryByTestId('offline-gate')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
  })

  it('never gates the knowledge screens', async () => {
    fullBackend()
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    renderApp('/system')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'System Status' }),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('offline-gate')).not.toBeInTheDocument()
  })

  it('lists live-only pages in the command palette as unavailable offline', async () => {
    fullBackend()
    renderApp('/system')
    await screen.findByRole('heading', { level: 1, name: 'System Status' })
    setOnline(false)
    await userEvent.click(await screen.findByTestId('palette-trigger'))
    const dialog = await screen.findByRole('dialog', { name: 'Command palette' })
    const item = (title: string) =>
      within(dialog).getByText(title).closest('[data-kind="page"]') as HTMLElement
    for (const title of ['Live Well Monitor', 'Alerts', 'Knowledge Search']) {
      expect(item(title), title).toHaveAttribute('aria-disabled', 'true')
      expect(item(title), title).toHaveTextContent('offline')
    }
    expect(item('Correlation Panel')).toHaveAttribute('aria-disabled', 'false')
  })
})
