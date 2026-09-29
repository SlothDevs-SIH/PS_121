import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { pipelineSteps } from '../lib/documents'
import { DOCUMENTS, fullBackend, PAGE, renderApp } from '../test/utils'

function backend() {
  return fullBackend({
    'POST /api/v1/documents': {
      status: 202,
      body: [
        { document_id: 9, filename: 'new.pdf', sha256: 'a', status: 'queued', duplicate: false },
        { document_id: 7, filename: 'old.pdf', sha256: 'b', status: 'processed', duplicate: true },
      ],
    },
    '/api/v1/documents/7/pages/1': PAGE,
  })
}

describe('Documents Library', () => {
  it('shows document cards with their pipeline stages', async () => {
    backend()
    renderApp('/documents')
    const grid = await screen.findByTestId('documents-grid')
    const cards = within(grid).getAllByTestId('document-card')
    expect(cards).toHaveLength(2)
    // Newest first; the unidentified scan stops at extraction (skipped).
    const [scan, ddr] = cards
    expect(within(scan!).getByLabelText('Extraction: skipped')).toBeInTheDocument()
    expect(within(ddr!).getByLabelText('Indexed: done')).toBeInTheDocument()
    expect(screen.getByTestId('stage-totals')).toHaveTextContent('2Uploaded')
    expect(screen.getByTestId('stage-totals')).toHaveTextContent('1Extracted')
  })

  it('switches to the list and filters by type and text', async () => {
    backend()
    renderApp('/documents')
    await screen.findByTestId('documents-grid')
    await userEvent.click(screen.getByRole('radio', { name: 'List' }))
    const table = await screen.findByTestId('documents-table')
    expect(within(table).getByText('needs review')).toBeInTheDocument()
    expect(within(table).getByText("well not identified (read: 'SYN ASM 9x')")).toBeInTheDocument()
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search documents' }), 'unknown')
    expect(within(table).queryByText('SYN-ASM-01_DDR.pdf')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: 'WCR' }))
    expect(screen.getByText('No documents match — upload a report or change the filters.'))
  })

  it('uploads files as multipart and reports new vs duplicate', async () => {
    const fetchMock = backend()
    renderApp('/documents')
    await screen.findByTestId('documents-grid')
    const file = new File(['%PDF-1.4 test'], 'new.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByTestId('file-input'), file)
    const results = await screen.findByTestId('upload-results')
    expect(within(results).getByText('queued')).toBeInTheDocument()
    expect(within(results).getByText('already ingested')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    const body = post?.[1]?.body
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).getAll('files')).toHaveLength(1)
  })

  it('opens the evidence viewer from a card and from a ?doc= link', async () => {
    backend()
    const { unmount } = renderApp('/documents')
    await userEvent.click(await screen.findByRole('button', { name: 'Open SYN-ASM-01_DDR.pdf' }))
    expect(
      await screen.findByRole('dialog', { name: /SYN-ASM-01_DDR.pdf — page 1 of 1/ }),
    ).toBeInTheDocument()
    unmount()
    backend()
    renderApp('/documents?doc=7')
    expect(await screen.findByRole('dialog', { name: /SYN-ASM-01_DDR.pdf/ })).toBeInTheDocument()
  })

  it('maps stage columns to timeline states', () => {
    const doc = DOCUMENTS.body.items[0]!
    expect(
      pipelineSteps({ ...doc, ingest_status: 'processing' } as never).map((s) => s.state),
    ).toEqual(['done', 'active', 'done', 'done'])
    expect(
      pipelineSteps({ ...doc, extract_status: 'failed', extract_error: 'boom' } as never)[2],
    ).toEqual({ label: 'Extraction', state: 'failed', note: 'boom' })
  })
})
