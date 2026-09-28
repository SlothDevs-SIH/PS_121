import { useEffect, useMemo, useState, type ReactNode } from 'react'

import type { UnitSystem } from '../lib/format/units'
import { readPref, writePref } from '../lib/storage'
import { ThemeContext, type ThemeChoice, type ThemeState, type UiMode } from './themeContext'

const THEME_KEY = 'smriti.theme'
const MODE_KEY = 'smriti.mode'
const UNITS_KEY = 'smriti.units'

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false
}

function initialTheme(): ThemeChoice {
  const saved = readPref(THEME_KEY)
  return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'system'
}

function initialUnits(): UnitSystem {
  return readPref(UNITS_KEY) === 'oilfield' ? 'oilfield' : 'metric'
}

function initialMode(): UiMode {
  return readPref(MODE_KEY) === 'field' ? 'field' : 'office'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeChoice>(initialTheme)
  const [mode, setModeState] = useState<UiMode>(initialMode)
  const [units, setUnitsState] = useState<UnitSystem>(initialUnits)
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const resolvedTheme: 'light' | 'dark' =
    theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme
  }, [resolvedTheme])

  useEffect(() => {
    document.documentElement.dataset.mode = mode
  }, [mode])

  const value = useMemo<ThemeState>(
    () => ({
      theme,
      resolvedTheme,
      mode,
      units,
      setUnits: (u) => {
        setUnitsState(u)
        writePref(UNITS_KEY, u)
      },
      setTheme: (t) => {
        setThemeState(t)
        writePref(THEME_KEY, t)
      },
      setMode: (m) => {
        setModeState(m)
        writePref(MODE_KEY, m)
      },
    }),
    [theme, resolvedTheme, mode, units],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
