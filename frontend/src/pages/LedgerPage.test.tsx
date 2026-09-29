import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { fullBackend, LEDGER, renderApp } from '../test/utils'

const FORMATIONS = {
  status: 200,
  body: [{ id: 4, name: 'Tipam Sandstone', synonyms: [], strat_order: 4, basin: 'Assam' }],
}

describe('Mitigation Ledger', () => {
  it('shows the ranking in the API order with credible intervals and the caveat', async () => {
    fullBackend({ '/api/v1/ledger': LEDGER, '/api/v1/formations': FORMATIONS })
    renderApp('/ledger')
    const ranked = await screen.findByTestId('ledger-ranked')
    const actions = within(ranked)
      .getAllByTestId('ledger-action')
      .map((b) => b.getAttribute('data-code'))
    expect(actions).toEqual(['LCM_PILL_COARSE', 'LCM_PILL_FINE', 'REDUCE_MW'])
    expect(within(ranked).getByText('7 of 8')).toBeInTheDocument()
    expect(
      within(ranked).getByRole('img', {
        name: 'LCM pill (coarse) worked: 80% (90% credible interval 60% to 95%)',
      }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('ledger-caveat')).toHaveTextContent('observational data, not causal')
    expect(screen.getByTestId('ledger-caveat')).toHaveTextContent('never counted')
    expect(screen.getByTestId('ledger-scope')).toHaveTextContent('2 with unknown outcome')
    expect(screen.getByText('SYNTHETIC data')).toBeInTheDocument()
    // n < min_n: listed, not ranked
    const insufficient = screen.getByTestId('ledger-insufficient')
    expect(within(insufficient).getByText('Cement plug')).toBeInTheDocument()
    expect(within(insufficient).getAllByRole('row')[1]).toHaveTextContent('–')
  })

  it('expands an action into its cases with evidence and recurrence', async () => {
    fullBackend({ '/api/v1/ledger': LEDGER, '/api/v1/formations': FORMATIONS })
    renderApp('/ledger')
    const first = (await screen.findAllByTestId('ledger-action'))[0]!
    expect(first).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(first)
    expect(first).toHaveAttribute('aria-expanded', 'true')
    const cases = screen.getByTestId('ledger-cases')
    expect(within(cases).getByText('SYN-ASM-08')).toHaveAttribute('href', '/wells/8?tab=events')
    expect(within(cases).getByText('DDR p.1')).toBeInTheDocument()
    expect(within(cases).getByText(/recurred \(recorded success\)/)).toBeInTheDocument()
    expect(within(cases).getByText('no citation')).toBeInTheDocument()
    expect(screen.getByTestId('ledger-strata')).toHaveTextContent('high 6/7')
  })

  it('refetches for another problem and formation', async () => {
    const fetchMock = fullBackend({ '/api/v1/ledger': LEDGER, '/api/v1/formations': FORMATIONS })
    renderApp('/ledger')
    await screen.findByTestId('ledger-ranked')
    await userEvent.selectOptions(screen.getByTestId('ledger-type'), 'KICK')
    await screen.findByRole('option', { name: 'Tipam Sandstone' })
    await userEvent.selectOptions(screen.getByTestId('ledger-formation'), 'Tipam Sandstone')
    await waitFor(() =>
      expect(fetchMock.mock.calls.map((c) => String(c[0]))).toContain(
        '/api/v1/ledger?event_type=KICK&formation=Tipam+Sandstone',
      ),
    )
  })

  it('says plainly when nothing reaches the minimum n', async () => {
    fullBackend({
      '/api/v1/ledger': { status: 200, body: { ...LEDGER.body, ranked: [] } },
      '/api/v1/formations': FORMATIONS,
    })
    renderApp('/ledger')
    expect(await screen.findByTestId('ledger-empty')).toHaveTextContent('No action has 3')
  })
})
