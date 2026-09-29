/**
 * Client-only UI state (FRONTEND_SPEC §6): theme, office/field mode, display units, sidebar
 * collapse and the global well-type filter. Server data never lives here (TanStack Query
 * owns it). Choices are remembered per viewer in localStorage, guarded for private windows.
 */
import { create } from 'zustand'

import type { UnitSystem } from '../lib/format/units'
import { readPref, writePref } from '../lib/storage'

export type ThemeName = 'deep-rig' | 'daylight' | 'command-blue'
export type UiMode = 'office' | 'field'
export type WellTypeFilter = 'all' | 'oil' | 'gas' | 'water'

export const THEMES: { id: ThemeName; label: string }[] = [
  { id: 'deep-rig', label: 'Deep Rig' },
  { id: 'daylight', label: 'Daylight Field' },
  { id: 'command-blue', label: 'Command Blue' },
]

const KEYS = {
  theme: 'smriti.theme',
  mode: 'smriti.mode',
  units: 'smriti.units',
  sidebar: 'smriti.sidebar',
  wellType: 'smriti.wellType',
} as const

function initialTheme(): ThemeName {
  const saved = readPref(KEYS.theme)
  if (saved === 'deep-rig' || saved === 'daylight' || saved === 'command-blue') return saved
  if (saved === 'light') return 'daylight' // choices saved by the Part 1 app
  return 'deep-rig'
}

function initialWellType(): WellTypeFilter {
  const saved = readPref(KEYS.wellType)
  return saved === 'oil' || saved === 'gas' || saved === 'water' ? saved : 'all'
}

export interface UiState {
  theme: ThemeName
  mode: UiMode
  units: UnitSystem
  sidebarCollapsed: boolean
  /** Set by full-bleed pages (Map Explorer) for their lifetime; not a saved preference. */
  forceRail: boolean
  mobileNavOpen: boolean
  paletteOpen: boolean
  wellType: WellTypeFilter
  setTheme: (t: ThemeName) => void
  setMode: (m: UiMode) => void
  setUnits: (u: UnitSystem) => void
  setSidebarCollapsed: (c: boolean) => void
  setForceRail: (f: boolean) => void
  setMobileNavOpen: (o: boolean) => void
  setPaletteOpen: (o: boolean) => void
  setWellType: (t: WellTypeFilter) => void
}

export const useUiStore = create<UiState>()((set) => ({
  theme: initialTheme(),
  mode: readPref(KEYS.mode) === 'field' ? 'field' : 'office',
  units: readPref(KEYS.units) === 'oilfield' ? 'oilfield' : 'metric',
  sidebarCollapsed: readPref(KEYS.sidebar) === 'rail',
  forceRail: false,
  mobileNavOpen: false,
  paletteOpen: false,
  wellType: initialWellType(),
  setTheme: (theme) => {
    writePref(KEYS.theme, theme)
    set({ theme })
  },
  setMode: (mode) => {
    writePref(KEYS.mode, mode)
    set({ mode })
  },
  setUnits: (units) => {
    writePref(KEYS.units, units)
    set({ units })
  },
  setSidebarCollapsed: (sidebarCollapsed) => {
    writePref(KEYS.sidebar, sidebarCollapsed ? 'rail' : 'full')
    set({ sidebarCollapsed })
  },
  setForceRail: (forceRail) => set({ forceRail }),
  setMobileNavOpen: (mobileNavOpen) => set({ mobileNavOpen }),
  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
  setWellType: (wellType) => {
    writePref(KEYS.wellType, wellType)
    set({ wellType })
  },
}))

/** Read the stored preferences again (tests reset storage between cases). */
export function resetUiStore(): void {
  useUiStore.setState({
    theme: initialTheme(),
    mode: readPref(KEYS.mode) === 'field' ? 'field' : 'office',
    units: readPref(KEYS.units) === 'oilfield' ? 'oilfield' : 'metric',
    sidebarCollapsed: readPref(KEYS.sidebar) === 'rail',
    forceRail: false,
    mobileNavOpen: false,
    paletteOpen: false,
    wellType: initialWellType(),
  })
}
