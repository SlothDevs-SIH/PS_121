import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { fullBackend, PAGE, renderApp, reviewItem } from '../../test/utils'

const QUEUE = {
  status: 200,
  body: {
    items: [
      reviewItem(1),
      reviewItem(2, {
        kind: 'alias',
        proposed: { raw_name: 'SYN ASM 9x' },
        reason: 'well not identified',
      }),
    ],
    next_cursor: null,
    status_counts: { pending: 2, accepted: 0, corrected: 0, rejected: 0 },
  },
}

function backend() {
  return fullBackend({
    '/api/v1/review-queue': QUEUE,
    '/api/v1/documents/7/pages/1': PAGE,
    'POST /api/v1/review-queue/1': { status: 200, body: reviewItem(1, { status: 'corrected' }) },
    'POST /api/v1/review-queue/2': { status: 200, body: reviewItem(2, { status: 'rejected' }) },
  })
}

function posted(fetchMock: ReturnType<typeof fullBackend>, id: number) {
  const call = fetchMock.mock.calls.find(
    ([u, init]) => String(u) === `/api/v1/review-queue/${id}` && init?.method === 'POST',
  )
  return call ? JSON.parse(String(call[1]?.body)) : null
}

describe('Review queue', () => {
  it('shows the item against its page, highlighted, with why it needs review', async () => {
    backend()
    renderApp('/documents?view=review')
    const panel = await screen.findByTestId('review-panel')
    expect(panel).toHaveTextContent("casing size unreadable ('T')")
    expect(within(screen.getByTestId('review-fields')).getByText('Casing OD')).toBeInTheDocument()
    await waitFor(() =>
      expect(document.querySelector('[data-highlighted="true"]')).toHaveAttribute(
        'title',
        'Partial losses of 45 bbl/hr at 2,415 m in Tipam',
      ),
    )
    expect(screen.getByRole('tab', { name: /Review queue/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('corrects only the changed field, by keyboard', async () => {
    const fetchMock = backend()
    renderApp('/documents?view=review')
    await screen.findByTestId('review-panel')
    await userEvent.keyboard('e')
    const od = await screen.findByLabelText('Correct Casing OD')
    await userEvent.type(od, '7')
    await userEvent.click(screen.getByRole('button', { name: /Save correction \(1\)/ }))
    await waitFor(() =>
      expect(posted(fetchMock, 1)).toEqual({ action: 'correct', fields: { od_in: 7 } }),
    )
    expect(await screen.findByTestId('review-notice')).toHaveTextContent('Corrected 1 field')
  })

  it('moves with J/K; alias items can only be accepted or rejected, with a reason', async () => {
    const fetchMock = backend()
    renderApp('/documents?view=review')
    await screen.findByTestId('review-panel')
    await userEvent.keyboard('j')
    expect(screen.getByTestId('review-panel')).toHaveTextContent('well not identified')
    expect(screen.getByTestId('review-edit')).toBeDisabled()
    await userEvent.keyboard('r')
    await userEvent.click(
      within(screen.getByTestId('review-panel')).getByRole('button', { name: 'Reject' }),
    )
    await waitFor(() =>
      expect(posted(fetchMock, 2)).toEqual({
        action: 'reject',
        reason: 'Not a real fact in the report',
      }),
    )
  })
})
