import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Providers } from '../../app/providers'
import { makeQueryClient } from '../../app/queryClient'
import { mockBackend, PAGE } from '../../test/utils'
import { PageViewer } from './PageViewer'

function renderViewer(onClose = vi.fn(), highlight: number[] = [102]) {
  mockBackend({ '/api/v1/documents/7/pages/1': PAGE })
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false } })
  render(
    <Providers client={client}>
      <PageViewer
        documentId={7}
        pageCount={1}
        highlightSpanIds={highlight}
        onClose={onClose}
        title="DDR"
      />
    </Providers>,
  )
  return onClose
}

describe('PageViewer (evidence)', () => {
  it('overlays every extracted line at its bbox and highlights the cited ones', async () => {
    renderViewer()
    expect(await screen.findByRole('img', { name: 'Page 1 of document 7' })).toHaveAttribute(
      'src',
      '/api/v1/documents/7/pages/1/image',
    )
    const cited = screen.getByRole('button', { name: /Line 2: Partial losses/ })
    expect(cited).toHaveAttribute('data-highlighted', 'true')
    expect(cited.style.left).toBe('8%')
    expect(cited.style.top).toBe('20%')
    expect(screen.getByRole('button', { name: /Line 1: DAILY/ })).toHaveAttribute(
      'data-highlighted',
      'false',
    )
    expect(screen.getByText('OCR · mean confidence 88%')).toBeInTheDocument()
  })

  it('toggles highlights from the line list and closes on Escape', async () => {
    const onClose = renderViewer(vi.fn(), [])
    await userEvent.click(await screen.findByRole('button', { name: /^DAILY DRILLING REPORT/ }))
    expect(screen.getByRole('button', { name: /Line 1: DAILY/ })).toHaveAttribute(
      'data-highlighted',
      'true',
    )
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
