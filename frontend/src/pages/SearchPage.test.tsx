import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { highlight } from '../lib/highlight'
import { fullBackend, NO_RECORD, PAGE, renderApp, SEARCH_RESULT } from '../test/utils'

describe('Knowledge Search', () => {
  it('shows lessons first, then passages with highlighted terms and a page citation', async () => {
    const fetchMock = fullBackend({
      '/api/v1/search': SEARCH_RESULT,
      '/api/v1/documents/7/pages/1': PAGE,
    })
    renderApp('/search')
    await userEvent.type(await screen.findByTestId('search-input'), 'lost circulation Tipam{Enter}')
    const results = await screen.findByTestId('search-results')
    expect(within(results).getByTestId('lesson-card')).toHaveTextContent(
      'Coarse LCM worked first time',
    )
    const passage = within(results).getByTestId('passage')
    expect(Array.from(passage.querySelectorAll('mark')).map((m) => m.textContent)).toEqual([
      'Lost',
      'circulation',
      'Tipam',
    ])
    expect(screen.getByTestId('search-summary')).toHaveTextContent('hashing stand-in')
    await userEvent.click(within(passage).getByTestId('evidence-link'))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        ([u]) => String(u) === '/api/v1/search?q=lost+circulation+Tipam&limit=20',
      ),
    ).toBe(true)
  })

  it('says "No record found" instead of guessing', async () => {
    fullBackend({ '/api/v1/search': NO_RECORD })
    renderApp('/search?q=unicorn')
    expect(await screen.findByTestId('no-record')).toHaveTextContent('No record found')
    expect(screen.queryByTestId('passage')).toBeNull()
  })

  it('sends the filters as query parameters', async () => {
    const fetchMock = fullBackend({
      '/api/v1/search': SEARCH_RESULT,
      '/api/v1/formations': { status: 200, body: [] },
    })
    renderApp('/search?q=losses')
    await screen.findByTestId('search-results')
    await userEvent.selectOptions(screen.getByTestId('filter-well'), '1')
    await userEvent.selectOptions(screen.getByLabelText(/and offsets within/), '5')
    await userEvent.click(screen.getByRole('button', { name: 'Lost circulation' }))
    await userEvent.click(screen.getByRole('button', { name: 'Stuck pipe' }))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) =>
          String(u).includes(
            'q=losses&well_id=1&radius_km=5&limit=20&event_type=LOSS&event_type=STUCK',
          ),
        ),
      ).toBe(true),
    )
  })
})

describe('highlight', () => {
  it('marks the given ranges and keeps the rest as text', () => {
    const { container } = render(
      <p>
        {highlight('stuck pipe in Barail', [
          [0, 5],
          [14, 20],
          [2, 3],
        ])}
      </p>,
    )
    expect(container.textContent).toBe('stuck pipe in Barail')
    expect(Array.from(container.querySelectorAll('mark')).map((m) => m.textContent)).toEqual([
      'stuck',
      'Barail',
    ])
  })
})
