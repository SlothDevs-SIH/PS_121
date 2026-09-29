import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { fullBackend, renderApp } from '../../test/utils'

describe('Command palette', () => {
  it('opens with Ctrl+K, finds a well and jumps to it on the map', async () => {
    fullBackend({ '/api/v1/wells/3': { status: 500, body: null } })
    renderApp('/system')
    await screen.findByRole('heading', { name: 'System Status' })
    await userEvent.keyboard('{Control>}k{/Control}')
    const dialog = await screen.findByRole('dialog', { name: 'Command palette' })
    await userEvent.type(screen.getByPlaceholderText(/Jump to a well/), 'ASM-03')
    await waitFor(() => expect(dialog).toHaveTextContent('SYN-ASM-03'))
    await userEvent.keyboard('{Enter}')
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Command palette' })).not.toBeInTheDocument(),
    )
    expect(await screen.findByRole('heading', { name: 'Map Explorer' })).toBeInTheDocument()
    expect(screen.getByLabelText('Active well')).toHaveValue('3')
  })

  it('lists pages and documents and closes on Escape', async () => {
    fullBackend()
    renderApp('/system')
    await userEvent.click(await screen.findByTestId('palette-trigger'))
    const dialog = await screen.findByRole('dialog', { name: 'Command palette' })
    expect(dialog).toHaveTextContent('Documents Library')
    await waitFor(() => expect(dialog).toHaveTextContent('SYN-ASM-01_DDR.pdf'))
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(dialog).not.toBeInTheDocument())
  })
})
