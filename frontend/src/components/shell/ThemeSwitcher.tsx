import { Moon, Satellite, Sun } from 'lucide-react'
import type { MouseEvent } from 'react'
import { flushSync } from 'react-dom'

import { THEMES, useUiStore, type ThemeName } from '../../stores/ui'
import { Button } from '../ui/Button'

const ICON = { 'deep-rig': Moon, daylight: Sun, 'command-blue': Satellite } as const

type WithViewTransition = Document & {
  startViewTransition?: (cb: () => void) => unknown
}

/** Cycles the three themes; the next one sweeps in as a circle from the click point. */
export function ThemeSwitcher() {
  const theme = useUiStore((s) => s.theme)
  const setTheme = useUiStore((s) => s.setTheme)
  const idx = THEMES.findIndex((t) => t.id === theme)
  const next: ThemeName = THEMES[(idx + 1) % THEMES.length]?.id ?? 'deep-rig'
  const label = THEMES[idx]?.label ?? theme
  const Icon = ICON[theme]

  const onClick = (e: MouseEvent<HTMLButtonElement>) => {
    const doc = document as WithViewTransition
    const reduce =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!doc.startViewTransition || reduce) {
      setTheme(next)
      return
    }
    const root = document.documentElement
    const x = e.clientX || window.innerWidth - 40
    const y = e.clientY || 24
    const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
    root.style.setProperty('--reveal-x', `${x}px`)
    root.style.setProperty('--reveal-y', `${y}px`)
    root.style.setProperty('--reveal-r', `${r}px`)
    doc.startViewTransition(() => {
      flushSync(() => setTheme(next))
      root.dataset.theme = next
    })
  }

  return (
    <Button
      onClick={onClick}
      aria-label={`Theme: ${label}. Switch to ${THEMES.find((t) => t.id === next)?.label}`}
      data-testid="theme-toggle"
      data-theme-name={theme}
      title={`Theme: ${label}`}
    >
      <Icon size={16} aria-hidden />
      <span className="hidden xl:inline">{label}</span>
    </Button>
  )
}
