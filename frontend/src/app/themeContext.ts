import { createContext, useContext } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'
export type UiMode = 'office' | 'field'

export interface ThemeState {
  theme: ThemeChoice
  resolvedTheme: 'light' | 'dark'
  mode: UiMode
  setTheme: (t: ThemeChoice) => void
  setMode: (m: UiMode) => void
}

export const ThemeContext = createContext<ThemeState | null>(null)

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}
