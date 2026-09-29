import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import {
  CORRELATION,
  eventDetail,
  FORMATION_STATS,
  fullBackend,
  OFFSETS,
  PAGE,
  renderApp,
} from '../test/utils'

function backend(extra = {}) {
  return fullBackend({
    '/api/v1/correlation': CORRELATION,
    '/api/v1/correlation/formation-stats': FORMATION_STATS,
    '/api/v1/wells/2/offsets': OFFSETS,
    '/api/v1/events/200': eventDetail(200),
    '/api/v1/documents/7/pages/1': PAGE,
    ...extra,
  })
}

describe('Correlation Panel', () => {
  it('starts from the planned well and its nearest offsets, in that order', async () => {
    const fetchMock = backend()
    renderApp('/correlation')
    const headers = await screen.findAllByTestId('corr-header')
    expect(headers.map((h) => h.querySelector('a')?.textContent)).toEqual([
      'SYN-ASM-P01',
      'SYN-ASM-01',
      'SYN-ASM-03',
    ])
    // Offsets come nearest first: SYN-ASM-01 (1.4 km) before SYN-ASM-03 (2.4 km).
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) =>
          String(u).startsWith('/api/v1/correlation?wells=2&wells=1&wells=3'),
        ),
      ).toBe(true),
    )
    expect(screen.getByTestId('correlation-panel')).toHaveAttribute('data-align', 'TVDSS')
    expect(screen.getByTestId('fallback-badge')).toHaveTextContent('no Tipam Sandstone top')
    expect(screen.getAllByTestId('synthetic-badge').length).toBeGreaterThan(0)
  })

  it('opens an event with what the crew did and its source page', async () => {
    backend()
    renderApp('/correlation?wells=2,1,3')
    const column = await screen.findByTestId('corr-column-2')
    await userEvent.click(within(column).getByTestId('event-marker'))
    const card = screen.getByTestId('event-card')
    expect(card).toHaveTextContent('Lost circulation')
    expect(await within(card).findByText('Pumped coarse LCM pill')).toBeInTheDocument()
    await userEvent.click(within(card).getByTestId('evidence-link'))
    expect(await screen.findByRole('dialog')).toHaveTextContent('SYN-ASM-01_DDR.pdf')
  })

  it('flattens on a formation top and keeps the choice in the URL', async () => {
    const fetchMock = backend()
    renderApp('/correlation?wells=2,1,3')
    await screen.findAllByTestId('corr-header')
    await userEvent.click(screen.getByRole('radio', { name: 'Flatten on top' }))
    const top = await screen.findByTestId('top-select')
    expect(top).toHaveValue('Tipam Sandstone') // the middle formation of the panel
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) =>
          String(u).includes('align=FLATTEN_ON_TOP&top=Tipam+Sandstone'),
        ),
      ).toBe(true),
    )
    await userEvent.selectOptions(top, 'Barail')
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('top=Barail'))).toBe(true),
    )
  })

  it('removes wells, hides tracks, zooms, and tabulates formation statistics', async () => {
    backend()
    renderApp('/correlation?wells=2,1,3')
    await screen.findAllByTestId('corr-header')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Events' }))
    expect(screen.queryAllByTestId('event-marker')).toHaveLength(0)
    await userEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(screen.getByTestId('zoom-level')).toHaveTextContent('×1.6')
    const stats = await screen.findByTestId('formation-stats')
    expect(stats).toHaveTextContent('Lost circulation: 2 of 3')
    expect(stats).toHaveTextContent('none recorded')
    await userEvent.click(screen.getByRole('button', { name: 'Remove SYN-ASM-03' }))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Remove SYN-ASM-03' })).toBeNull(),
    )
  })
})
