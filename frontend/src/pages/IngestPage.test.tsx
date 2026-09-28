import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DOCUMENTS, META, ME, mockBackend, PAGE, READY, renderApp } from '../test/utils'

function backend() {
  return mockBackend({
    '/readyz': READY,
    '/api/v1/meta': META,
    '/api/v1/me': ME,
    'GET /api/v1/documents': DOCUMENTS,
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

describe('Ingestion page', () => {
  it('lists documents with status counts and review reasons', async () => {
    backend()
    renderApp('/ingest')
    const table = await screen.findByTestId('documents-table')
    expect(within(table).getByText('needs review')).toBeInTheDocument()
    expect(within(table).getByText("well not identified (read: 'SYN ASM 9x')")).toBeInTheDocument()
    expect(screen.getByTestId('status-counts')).toHaveTextContent('processed: 1')
  })

  it('uploads files as multipart and reports new vs duplicate', async () => {
    const fetchMock = backend()
    renderApp('/ingest')
    await screen.findByTestId('documents-table')
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

  it('opens the evidence viewer for a document', async () => {
    backend()
    renderApp('/ingest')
    await userEvent.click(await screen.findByText('SYN-ASM-01_DDR.pdf'))
    expect(
      await screen.findByRole('dialog', { name: /SYN-ASM-01_DDR.pdf — page 1 of 1/ }),
    ).toBeInTheDocument()
  })
})
