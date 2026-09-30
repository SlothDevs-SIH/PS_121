import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { UpdatePrompt } from '../../components/offline/UpdatePrompt'
import { usePwaStore, syncThemeColor } from './pwa'

afterEach(() => {
  usePwaStore.setState({ applyUpdate: null })
  document.head.querySelector('meta[name="theme-color"]')?.remove()
  document.getElementById('theme-tokens')?.remove()
})

describe('installed-app polish', () => {
  it('keeps the theme-color meta equal to the active theme’s --bg token', async () => {
    const style = document.createElement('style')
    style.id = 'theme-tokens'
    style.textContent = `
      :root[data-theme='deep-rig'] { --bg: #0a0e14; }
      :root[data-theme='daylight'] { --bg: #f5f3ee; }`
    document.head.append(style)
    const meta = document.createElement('meta')
    meta.name = 'theme-color'
    meta.content = '#000000'
    document.head.append(meta)

    document.documentElement.dataset.theme = 'deep-rig'
    const stop = syncThemeColor()
    expect(meta.content).toBe('#0a0e14')
    document.documentElement.dataset.theme = 'daylight'
    await act(async () => {}) // MutationObserver callbacks run as microtasks
    expect(meta.content).toBe('#f5f3ee')
    stop()
    document.documentElement.dataset.theme = 'deep-rig'
    await act(async () => {})
    expect(meta.content).toBe('#f5f3ee')
  })

  it('offers "Update available – Reload" only when a new version waits', async () => {
    render(<UpdatePrompt />)
    expect(screen.queryByTestId('update-prompt')).not.toBeInTheDocument()

    const apply = vi.fn()
    act(() => usePwaStore.getState().setUpdate(apply))
    expect(await screen.findByTestId('update-prompt')).toHaveTextContent('Update available')
    await userEvent.click(screen.getByRole('button', { name: /Reload/ }))
    expect(apply).toHaveBeenCalledOnce()

    await userEvent.click(screen.getByRole('button', { name: 'Later' }))
    expect(usePwaStore.getState().applyUpdate).toBeNull()
  })
})
