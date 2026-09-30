import { act, screen, within } from '@testing-library/react'

import { installPackSupport } from '../../lib/offline/fakeCaches'
import { PACK_META_PATH, packCacheName } from '../../lib/offline/keys'
import { fullBackend, mockBackend, renderApp } from '../../test/utils'

let uninstall: () => void = () => {}
afterEach(() => {
  uninstall()
  // TanStack Query's online manager is a module singleton: leave it online for the next test.
  window.dispatchEvent(new Event('online'))
})

function goOffline() {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  act(() => {
    window.dispatchEvent(new Event('offline'))
  })
}

describe('Offline banner and offline-aware navigation', () => {
  it('stays out of the way while online', async () => {
    fullBackend()
    renderApp('/system')
    await screen.findByRole('heading', { level: 1, name: 'System Status' })
    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByText('Alerts').closest('a')).toHaveAttribute('href', '/alerts')
  })

  it('says what works and what does not, naming the packed wells', async () => {
    const support = installPackSupport()
    uninstall = support.uninstall
    const cache = await support.storage.open(packCacheName(3, 1))
    await cache.put(
      `${window.location.origin}${PACK_META_PATH}`,
      new Response(
        JSON.stringify({
          version: 1,
          wellId: 3,
          wellName: 'SYN-ASM-03',
          createdAt: new Date(Date.now() - 5 * 60_000).toISOString(),
          bytes: 1000,
          entries: 10,
          missing: 0,
          imagesSkipped: 0,
          capBytes: 1,
        }),
      ),
    )
    fullBackend()
    renderApp('/system')
    await screen.findByRole('heading', { level: 1, name: 'System Status' })
    goOffline()

    const banner = await screen.findByTestId('offline-banner')
    expect(banner).toHaveTextContent(
      'Offline. Map, Correlation, Well 360, Lessons and Ledger work for packed wells',
    )
    expect(banner).toHaveTextContent(
      'Live monitor, alerts, copilot and new searches need the connection: live alerts need the link to the server near eRTMAC.',
    )
    const link = await within(banner).findByRole('link', { name: 'SYN-ASM-03' })
    expect(link).toHaveAttribute('href', '/wells/3')
    expect(banner).toHaveTextContent('(updated 5 min ago)')

    // Live-only screens are shown as unavailable instead of failing; knowledge ones stay.
    const nav = screen.getByRole('navigation', { name: 'Main' })
    for (const title of ['Live Well Monitor', 'Alerts', 'Knowledge Search']) {
      const item = within(nav).getByText(title).closest('[data-screen]')
      expect(item, title).toHaveAttribute('aria-disabled', 'true')
      expect(item?.tagName, title).not.toBe('A')
    }
    expect(within(nav).getByText('Correlation Panel').closest('a')).toHaveAttribute(
      'href',
      '/correlation',
    )

    act(() => {
      vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
      window.dispatchEvent(new Event('online'))
    })
    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument()
  })

  it('says so when no pack is downloaded', async () => {
    fullBackend()
    renderApp('/system')
    await screen.findByRole('heading', { level: 1, name: 'System Status' })
    goOffline()
    expect(await screen.findByTestId('offline-banner')).toHaveTextContent(
      'No well pack is downloaded on this device.',
    )
  })

  it('treats a server that cannot be reached at all like offline', async () => {
    mockBackend({ '/readyz': 'network-error' })
    renderApp('/ledger')
    expect(await screen.findByTestId('offline-banner')).toHaveTextContent(
      'The SMRITI server cannot be reached.',
    )
  })

  it('does not call an erroring backend offline (the web server answered)', async () => {
    mockBackend({ '/readyz': { status: 502, body: {} } })
    renderApp('/system')
    await screen.findByRole('heading', { level: 1, name: 'System Status' })
    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument()
  })
})
