import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { useUiStore } from '../stores/ui'
import { fullBackend, OFFSETS, renderApp, wellDetail } from '../test/utils'

// The page logic is tested with a stand-in map; WellMap itself has its own test.
vi.mock('../components/map/WellMap', () => ({
  default: (p: { wells: { role: string; dimmed?: boolean }[]; radiusKm: number }) => (
    <div data-testid="mock-map">
      {p.wells.filter((w) => w.role === 'offset').length} offsets on map · r={p.radiusKm} ·{' '}
      {p.wells.length} wells · {p.wells.filter((w) => w.dimmed).length} dimmed
    </div>
  ),
}))

const TRAJ = (id: number) => ({
  status: 200,
  body: { well_id: id, wellbore_id: id, assumed: false, crs_epsg: 32646, stations: [], path: [] },
})

function backend() {
  return fullBackend({
    '/api/v1/wells/1': wellDetail(1),
    '/api/v1/wells/2': wellDetail(2),
    '/api/v1/wells/1/trajectory': TRAJ(1),
    '/api/v1/wells/2/trajectory': TRAJ(2),
    '/api/v1/wells/2/offsets': OFFSETS,
    '/api/v1/wells/1/offsets': { status: 200, body: { ...OFFSETS.body, well_id: 1, offsets: [] } },
  })
}

describe('Map Explorer', () => {
  it('defaults to the planned well and lists offsets nearest first', async () => {
    const fetchMock = backend()
    renderApp('/map')
    expect(await screen.findByRole('heading', { name: 'Map Explorer' })).toBeInTheDocument()
    expect(await screen.findByTestId('offset-count')).toHaveTextContent('2 within 5 km')
    const rows = within(screen.getByTestId('offset-table')).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getAllByRole('cell')[0]!.textContent)).toEqual([
      'SYN-ASM-01',
      'SYN-ASM-03',
    ])
    expect(within(rows[0]!).getByText('1.4 km')).toBeInTheDocument()
    expect(await screen.findByTestId('mock-map')).toHaveTextContent('2 offsets on map · r=5')
    expect(
      fetchMock.mock.calls.some(([u]) =>
        String(u).startsWith('/api/v1/wells/2/offsets?radius_km=5&mode=SURFACE'),
      ),
    ).toBe(true)
  })

  it('folds the sidebar to a rail while open and restores it after', async () => {
    backend()
    const { unmount } = renderApp('/map')
    await screen.findByTestId('offset-table')
    expect(useUiStore.getState().forceRail).toBe(true)
    unmount()
    expect(useUiStore.getState().forceRail).toBe(false)
  })

  it('switches wells from the offset list; other distance modes wait for Part 3', async () => {
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

  it('dims wells of other fluids and hides fluids switched off in the legend', async () => {
    backend()
    renderApp('/map?type=gas')
    const map = await screen.findByTestId('mock-map')
    await waitFor(() => expect(useUiStore.getState().wellType).toBe('gas'))
    // 4 wells: the planned (active) well is never dimmed; oil wells 1 and 4 are dimmed.
    await waitFor(() => expect(map).toHaveTextContent('4 wells · 2 dimmed'))
    await userEvent.click(screen.getByRole('button', { name: 'Hide oil wells' }))
    expect(map).toHaveTextContent('2 wells · 0 dimmed')
  })
})
