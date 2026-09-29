import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { fullBackend, renderApp } from '../test/utils'

describe('Dashboard', () => {
  it('shows KPIs from real endpoints, recent events and no simulated alerts', async () => {
    fullBackend()
    renderApp('/')
    const wells = await screen.findByTestId('kpi-wells')
    await waitFor(() =>
      expect(wells.querySelector('[data-value]')).toHaveAttribute('data-value', '4'),
    )
    expect(wells).toHaveTextContent('2 oil · 1 gas · 0 water')
    const drilling = screen.getByTestId('kpi-drilling')
    expect(drilling.querySelector('[data-value]')).toHaveAttribute('data-value', '1')
    expect(drilling).toHaveTextContent('SYN-ASM-41')
    await waitFor(() =>
      expect(screen.getByTestId('kpi-events').querySelector('[data-value]')).toHaveAttribute(
        'data-value',
        '2',
      ),
    )
    expect(screen.getByTestId('kpi-documents')).toHaveTextContent('/ 2')
    expect(await screen.findByText('5 extractions awaiting review')).toBeInTheDocument()

    const recent = await screen.findByTestId('recent-events')
    const items = within(recent).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Stuck pipe (differential)') // newest first
    expect(items[1]).toHaveTextContent('unverified')
    expect(screen.getByText(/Nothing here is simulated/)).toBeInTheDocument()
  })

  it('follows the global well-type switcher', async () => {
    fullBackend()
    renderApp('/')
    const wells = await screen.findByTestId('kpi-wells')
    await userEvent.click(screen.getAllByRole('radio', { name: 'Gas' })[0]!)
    await waitFor(() =>
      expect(wells.querySelector('[data-value]')).toHaveAttribute('data-value', '1'),
    )
    expect(wells).toHaveTextContent('Gas wells')
    await waitFor(() =>
      expect(screen.getByTestId('kpi-events').querySelector('[data-value]')).toHaveAttribute(
        'data-value',
        '1',
      ),
    )
    expect(window.localStorage.getItem('smriti.wellType')).toBe('gas')
  })
})
