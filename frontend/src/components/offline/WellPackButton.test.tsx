import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Providers } from '../../app/providers'
import { makeQueryClient } from '../../app/queryClient'
import { installPackSupport } from '../../lib/offline/fakeCaches'
import { resetDownloads } from '../../lib/offline/usePacks'
import { mockBackend, READY } from '../../test/utils'
import { WellPackButton } from './WellPackButton'

const WELL = {
  status: 200,
  body: {
    id: 3,
    name: 'SYN-ASM-03',
    formation_tops: [],
    event_counts: {},
    recent_events: [],
    lessons: [],
  },
}

let uninstall: () => void = () => {}
afterEach(() => {
  uninstall()
  resetDownloads()
  window.dispatchEvent(new Event('online'))
})

function renderButton() {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false, refetchInterval: false } })
  return render(
    <Providers client={client}>
      <WellPackButton wellId={3} />
    </Providers>,
  )
}

describe('WellPackButton', () => {
  it('is not offered where the browser cannot keep a pack', () => {
    mockBackend({ '/readyz': READY })
    renderButton()
    expect(screen.queryByTestId('well-pack')).not.toBeInTheDocument()
  })

  it('downloads the pack, shows its size and age, and removes it', async () => {
    uninstall = installPackSupport().uninstall
    mockBackend({ '/readyz': READY, '/api/v1/wells/3': WELL })
    renderButton()
    await userEvent.click(await screen.findByRole('button', { name: /Download well pack/ }))
    const ready = await screen.findByTestId('well-pack-ready')
    expect(ready).toHaveTextContent(/Offline pack · [\d.]+ (B|KB|MB) · updated just now/)
    expect(screen.getByRole('button', { name: /Update pack/ })).toBeEnabled()

    await userEvent.click(screen.getByRole('button', { name: /Remove pack/ }))
    expect(await screen.findByTestId('well-pack-download')).toBeInTheDocument()
    expect(await caches.keys()).toEqual([])
  })

  it('shows progress while downloading and can be cancelled', async () => {
    uninstall = installPackSupport().uninstall
    const fetchMock = mockBackend({ '/readyz': READY, '/api/v1/wells/3': WELL })
    const real = fetchMock.getMockImplementation()!
    // The well list never answers, so the download stays in its first stage.
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input).startsWith('/api/v1/wells?'))
        return new Promise<Response>((_, reject) =>
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          ),
        )
      return real(input, init)
    })
    renderButton()
    await userEvent.click(await screen.findByRole('button', { name: /Download well pack/ }))
    const bar = await screen.findByRole('progressbar', { name: 'Well pack download' })
    expect(Number(bar.getAttribute('aria-valuenow'))).toBeLessThan(100)
    expect(screen.getByTestId('well-pack-status')).toHaveTextContent(/of 8 ·/)

    await userEvent.click(screen.getByRole('button', { name: /Cancel/ }))
    expect(await screen.findByText(/Download cancelled/)).toBeInTheDocument()
    expect(screen.getByTestId('well-pack-download')).toBeInTheDocument()
    expect(await caches.keys()).toEqual([])
  })

  it('explains a well the server does not know', async () => {
    uninstall = installPackSupport().uninstall
    mockBackend({ '/readyz': READY })
    renderButton()
    await userEvent.click(await screen.findByRole('button', { name: /Download well pack/ }))
    expect(await screen.findByText(/This well could not be loaded/)).toBeInTheDocument()
  })

  it('cannot start a download offline', async () => {
    uninstall = installPackSupport().uninstall
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    mockBackend({ '/readyz': READY })
    renderButton()
    const button = await screen.findByRole('button', { name: /Download well pack/ })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'Needs a connection')
  })
})
