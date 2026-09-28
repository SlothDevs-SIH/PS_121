import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { META, ME, mockBackend, OFFSETS, READY, renderApp, WELLS, wellDetail } from '../test/utils'

// Leaflet needs a real layout engine; the page logic is tested with a stand-in map.
vi.mock('../components/map/WellMap', () => ({
  default: (p: { wells: { role: string }[]; radiusKm: number }) => (
    <div data-testid="mock-map">
      {p.wells.filter((w) => w.role === 'offset').length} offsets on map · r={p.radiusKm}
    </div>
  ),
}))

function backend() {
  return mockBackend({
    '/readyz': READY,
    '/api/v1/meta': META,
    '/api/v1/me': ME,
    '/config.json': { status: 200, body: { mapTileUrl: '', mapTileAttribution: '' } },
    '/api/v1/wells': WELLS,
    '/api/v1/wells/1': wellDetail(1),
    '/api/v1/wells/2': wellDetail(2),
    '/api/v1/wells/1/trajectory': {
      status: 200,
      body: { well_id: 1, wellbore_id: 1, assumed: false, crs_epsg: 32646, stations: [], path: [] },
    },
    '/api/v1/wells/2/trajectory': {
      status: 200,
      body: { well_id: 2, wellbore_id: 2, assumed: false, crs_epsg: 32646, stations: [], path: [] },
    },
    '/api/v1/wells/2/offsets': OFFSETS,
    '/api/v1/wells/1/offsets': { status: 200, body: { ...OFFSETS.body, well_id: 1, offsets: [] } },
  })
}

describe('Well Map page', () => {
  it('defaults to the planned well and lists offsets nearest first', async () => {
    const fetchMock = backend()
    renderApp('/map')
    expect(await screen.findByRole('heading', { name: 'Well Map' })).toBeInTheDocument()
    expect(await screen.findByTestId('offset-count')).toHaveTextContent('2 within 5 km')
    const rows = within(screen.getByTestId('offset-table')).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getAllByRole('cell')[0]!.textContent)).toEqual([
      'SYN-ASM-01',
      'SYN-ASM-03',
    ])
    expect(within(rows[0]!).getByText('1.4 km')).toBeInTheDocument()
    expect(await screen.findByTestId('mock-map')).toHaveTextContent('2 offsets on map · r=5')
    expect(screen.getByTestId('synthetic-badge')).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(([u]) =>
        String(u).startsWith('/api/v1/wells/2/offsets?radius_km=5&mode=SURFACE'),
      ),
    ).toBe(true)
  })

  it('switches the active well from the list and disables B2 modes', async () => {
    backend()
    renderApp('/map?well=2&r=5')
    await screen.findByTestId('offset-table')
    expect(screen.getByRole('radio', { name: /At formation/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: 'Surface' })).toHaveAttribute('aria-checked', 'true')
    await userEvent.click(within(screen.getByTestId('offset-table')).getByText('SYN-ASM-01'))
    expect(
      await screen.findByText('No offset wells within 5 km — widen the radius.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Active well')).toHaveValue('1')
  })
})
