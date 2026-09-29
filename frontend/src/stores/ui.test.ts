import { resetUiStore, useUiStore } from './ui'

describe('UI store', () => {
  it('migrates the Part 1 theme choice and remembers new ones', () => {
    window.localStorage.setItem('smriti.theme', 'light')
    resetUiStore()
    expect(useUiStore.getState().theme).toBe('daylight')
    window.localStorage.setItem('smriti.theme', 'dark')
    resetUiStore()
    expect(useUiStore.getState().theme).toBe('deep-rig')
    useUiStore.getState().setTheme('command-blue')
    expect(window.localStorage.getItem('smriti.theme')).toBe('command-blue')
  })

  it('keeps the well-type filter and ignores junk', () => {
    window.localStorage.setItem('smriti.wellType', 'lava')
    resetUiStore()
    expect(useUiStore.getState().wellType).toBe('all')
    useUiStore.getState().setWellType('water')
    resetUiStore()
    expect(useUiStore.getState().wellType).toBe('water')
  })

  it('does not persist the forced rail or the palette state', () => {
    useUiStore.getState().setForceRail(true)
    useUiStore.getState().setPaletteOpen(true)
    resetUiStore()
    expect(useUiStore.getState().forceRail).toBe(false)
    expect(useUiStore.getState().paletteOpen).toBe(false)
  })
})
