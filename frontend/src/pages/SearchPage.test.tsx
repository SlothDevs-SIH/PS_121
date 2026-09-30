import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { highlight } from '../lib/highlight'
import {
  byteChunks,
  errorResponse,
  LEDGER_EVENTS,
  mockCopilot,
  page2,
  sse,
  sseResponse,
  UNANSWERABLE_EVENTS,
} from '../test/fixtures/copilot'
import {
  ALERT_PAGE,
  alertFixture,
  fullBackend,
  NO_RECORD,
  PAGE,
  REALTIME,
  renderApp,
  SEARCH_RESULT,
} from '../test/utils'

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

describe('Copilot panel', () => {
  async function ask(question: string) {
    await userEvent.type(await screen.findByTestId('copilot-input'), `${question}{Enter}`)
  }
  const lastTurn = () => screen.getAllByTestId('copilot-turn').at(-1)!

  it('streams a cited answer; a citation chip opens the cited page with its lines highlighted', async () => {
    const fetchMock = fullBackend({ '/api/v1/documents/7/pages/2': page2(PAGE) })
    // 5-byte reads: every event, and the multi-byte ¼ and ″, are split across chunks.
    const copilot = mockCopilot(() => sseResponse(byteChunks(sse(LEDGER_EVENTS), 5)).response)
    renderApp('/search?copilot=')
    await ask('What worked for losses in the Tipam?{Enter}')
    await waitFor(() => expect(lastTurn()).toHaveAttribute('data-status', 'done'))
    expect(copilot).toHaveBeenCalledTimes(1) // the second Enter sent nothing
    const answer = within(lastTurn()).getByTestId('copilot-answer')
    expect(answer).toHaveTextContent('worked 7 of 8 times in the 12¼″ section')
    expect(answer.querySelector('strong')).toHaveTextContent('LCM pill (coarse)')
    expect(screen.getByTestId('copilot-status')).toHaveTextContent(
      /^Answer: Recorded treatments .* not proven to cause it\. 2 sources\.$/,
    )

    const why = within(lastTurn()).getByTestId('copilot-why')
    await userEvent.click(within(why).getByText('Why this answer?'))
    const tool = within(why).getByTestId('copilot-tool')
    expect(tool).toHaveTextContent('Read the Mitigation Ledger get_ledger')
    expect(tool).toHaveTextContent('problem LOSS · formation Tipam Sandstone')
    expect(tool).toHaveTextContent('→ 2 facts found')

    const [pageChip, wellChip] = within(answer).getAllByTestId('citation-chip')
    expect(wellChip).toHaveAttribute('href', '/wells/1')
    await userEvent.click(pageChip!)
    const viewer = await screen.findByRole('dialog', { name: /SYN-ASM-01_DDR\.pdf — page 2/ })
    expect(
      await within(viewer).findByRole('button', { name: /Line 2: Partial losses/ }),
    ).toHaveAttribute('data-highlighted', 'true')
    expect(fetchMock.mock.calls.some(([u]) => String(u) === '/api/v1/documents/7/pages/2')).toBe(
      true,
    )
  })

  it('renders partial tokens as they arrive, including a character split mid-UTF-8', async () => {
    fullBackend()
    const [plan, tool, intro, fact, ...rest] = LEDGER_EVENTS
    const factBytes = new TextEncoder().encode(sse([fact!]))
    const cut = factBytes.indexOf(0xc2) + 1 // inside "¼" (C2 BC)
    const introText = sse([intro!])
    const { response, control } = sseResponse(
      [sse([plan!, tool!]) + introText.slice(0, 30), introText.slice(30), factBytes.slice(0, cut)],
      { open: true },
    )
    mockCopilot(() => response)
    renderApp('/search?copilot=')
    await ask('What worked?')
    const answer = await screen.findByTestId('copilot-answer')
    expect(answer).toHaveTextContent(/^Recorded treatments for losses/)
    expect(answer).not.toHaveTextContent('LCM pill')
    expect(screen.getByTestId('copilot-caret')).toBeInTheDocument()
    expect(screen.getByTestId('copilot-status')).toHaveTextContent('The copilot is answering.')

    control.push(factBytes.slice(cut))
    expect(await within(answer).findByText(/12¼″ section/)).toBeInTheDocument()
    // Marks wait, inert, for the citations event that follows the answer.
    expect(within(answer).getAllByTestId('citation-pending')).toHaveLength(2)
    expect(screen.getByTestId('copilot-status')).toHaveTextContent('The copilot is answering.')

    control.push(sse(rest))
    control.close()
    await waitFor(() => expect(within(answer).getAllByTestId('citation-chip')).toHaveLength(2))
    expect(screen.queryByTestId('copilot-caret')).toBeNull()
  })

  it('says "No record found" plainly when the records cannot answer', async () => {
    fullBackend()
    mockCopilot(() => sseResponse([sse(UNANSWERABLE_EVENTS)]).response)
    renderApp('/search?copilot=')
    await ask('What was the rig cost per day on SYN-ASM-20?')
    const refusal = await screen.findByTestId('copilot-no-record')
    expect(refusal).toHaveTextContent('No record found')
    expect(refusal).toHaveTextContent('The closest report passages do not mention cost.')
    expect(screen.queryByTestId('copilot-answer')).toBeNull()
    expect(screen.queryByTestId('copilot-sources')).toBeNull()
    expect(screen.getByTestId('copilot-status')).toHaveTextContent(/^No record found\. The closest/)
  })

  it('aborts the stream on Stop and when the page unmounts', async () => {
    fullBackend()
    const streams: ReturnType<typeof sseResponse>[] = []
    mockCopilot(() => {
      streams.push(sseResponse([sse(LEDGER_EVENTS.slice(0, 3))], { open: true }))
      return streams.at(-1)!.response
    })
    const view = renderApp('/search?copilot=')
    await ask('first')
    await screen.findByTestId('copilot-answer')
    await userEvent.click(screen.getByTestId('copilot-stop'))
    await streams[0]!.control.cancelled
    expect(lastTurn()).toHaveAttribute('data-status', 'stopped')
    expect(lastTurn()).toHaveTextContent('Stopped: the answer above is incomplete.')

    await ask('second')
    await waitFor(() => expect(screen.getAllByTestId('copilot-answer')).toHaveLength(2))
    view.unmount()
    await streams[1]!.control.cancelled
    expect(streams[1]!.control.isCancelled()).toBe(true)
  })

  it('on 429 says when to ask again, counts down from Retry-After, then allows it', async () => {
    fullBackend()
    const copilot = mockCopilot(() =>
      errorResponse(429, 'rate_limited', 'Too many requests', { 'Retry-After': '2' }),
    )
    renderApp('/search?copilot=')
    await ask('one too many')
    const error = await screen.findByTestId('copilot-error')
    expect(error).toHaveTextContent('Too many questions this minute')
    expect(error).toHaveTextContent(/ask again in [12] s/)
    await userEvent.type(screen.getByTestId('copilot-input'), 'again')
    expect(screen.getByTestId('copilot-send')).toBeDisabled()
    expect(screen.getByTestId('copilot-hint')).toHaveTextContent(/ask again in [12] s/)
    await waitFor(() => expect(screen.getByTestId('copilot-send')).toBeEnabled(), {
      timeout: 5000,
    })
    expect(error).toHaveTextContent('You can ask again now.')
    await userEvent.click(screen.getByTestId('copilot-send'))
    expect(copilot).toHaveBeenCalledTimes(2)
  })

  it('opens from an alert with the alert and its well as context', async () => {
    fullBackend({
      'GET /api/v1/alerts': ALERT_PAGE,
      'GET /api/v1/alerts/8': { status: 200, body: alertFixture(8) },
      '/api/v1/wells/4/realtime': REALTIME,
    })
    const copilot = mockCopilot(() => sseResponse([sse(LEDGER_EVENTS)]).response)
    renderApp('/alerts?id=8')
    await userEvent.click(await screen.findByTestId('ask-copilot'))
    const input = await screen.findByTestId('copilot-input')
    expect(input).toHaveValue('Why did this alert fire?')
    expect(input).toHaveFocus()
    const context = screen.getByTestId('copilot-context')
    expect(context).toHaveTextContent('SYN-ASM-41')
    expect(context).toHaveTextContent('alert #8')
    await userEvent.click(screen.getByTestId('copilot-send'))
    await waitFor(() => expect(copilot).toHaveBeenCalledTimes(1))
    expect(JSON.parse(String(copilot.mock.calls[0]![0]!.body))).toEqual({
      message: 'Why did this alert fire?',
      well_id: 4,
      alert_id: 8,
    })
    await userEvent.click(screen.getByRole('button', { name: 'Stop asking about alert 8' }))
    expect(screen.getByTestId('copilot-context')).not.toHaveTextContent('alert #8')
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByTestId('copilot-panel')).toBeNull())
  })
})
