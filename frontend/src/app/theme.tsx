import { useEffect, type ReactNode } from 'react'

import { useUiStore } from '../stores/ui'

/** Mirrors theme and mode onto <html> (the CSS tokens key off these attributes). */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useUiStore((s) => s.theme)
  const mode = useUiStore((s) => s.mode)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    document.documentElement.dataset.mode = mode
  }, [mode])

  return <>{children}</>
}
