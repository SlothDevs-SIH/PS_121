/**
 * Theme, mode and units as one hook, backed by the UI store. Kept as the single entry
 * point components use, so the store can change shape without touching every screen.
 */
import { useShallow } from 'zustand/react/shallow'

import type { UnitSystem } from '../lib/format/units'
import { useUiStore, type ThemeName, type UiMode } from '../stores/ui'

export type { ThemeName, UiMode }

export interface ThemeState {
  theme: ThemeName
  mode: UiMode
  units: UnitSystem
  isDark: boolean
  setTheme: (t: ThemeName) => void
  setMode: (m: UiMode) => void
  setUnits: (u: UnitSystem) => void
}

export function useTheme(): ThemeState {
  const s = useUiStore(
    useShallow((st) => ({
      theme: st.theme,
      mode: st.mode,
      units: st.units,
      setTheme: st.setTheme,
      setMode: st.setMode,
      setUnits: st.setUnits,
    })),
  )
  return { ...s, isDark: s.theme !== 'daylight' }
}
