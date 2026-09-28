import { HardHat, Monitor, Moon, Sun, SunMoon } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'

import { BackendStatus } from '../components/BackendStatus'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { cn } from '../lib/cn'
import { CURRENT_FRONTEND_PHASE, screensFor } from './screens'
import { useTheme, type ThemeChoice } from './themeContext'

const nextTheme: Record<ThemeChoice, ThemeChoice> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
}
const themeIcon = { system: SunMoon, light: Sun, dark: Moon } as const
const themeLabel: Record<ThemeChoice, string> = {
  system: 'Auto theme',
  light: 'Light',
  dark: 'Dark',
}

export function AppShell() {
  const { theme, setTheme, mode, setMode } = useTheme()
  const ThemeIcon = themeIcon[theme]
  const nav = screensFor(mode)

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-border bg-surface md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center justify-between px-4 py-3 md:block">
          <div>
            <div className="text-lg font-bold tracking-tight text-text">SMRITI</div>
            <div className="text-xs text-muted">eRTMAC-NWIS · offset-well intelligence</div>
          </div>
        </div>
        <nav aria-label="Main" className="overflow-x-auto px-2 pb-2">
          <ul className="flex gap-1 md:flex-col">
            {nav.map((s) => (
              <li key={s.id}>
                <NavLink
                  to={s.navPath}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm whitespace-nowrap',
                      isActive ? 'bg-accent text-accent-contrast' : 'text-text hover:bg-surface-2',
                    )
                  }
                >
                  <span>{s.title}</span>
                  {s.status !== 'built' && (
                    <span className="text-[0.7rem] opacity-70" aria-label={`planned ${s.phase}`}>
                      {s.phase}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface px-4 py-2">
          <div className="flex items-center gap-2">
            <Badge tone="info">Frontend phase {CURRENT_FRONTEND_PHASE}</Badge>
            <BackendStatus />
          </div>
          <div className="flex items-center gap-1">
            <Button
              onClick={() => setMode(mode === 'office' ? 'field' : 'office')}
              aria-label={`Switch to ${mode === 'office' ? 'field' : 'office'} view`}
              data-testid="mode-toggle"
            >
              {mode === 'office' ? <Monitor size={16} /> : <HardHat size={16} />}
              {mode === 'office' ? 'Office view' : 'Field view'}
            </Button>
            <Button
              onClick={() => setTheme(nextTheme[theme])}
              aria-label={`Theme: ${theme}. Switch to ${nextTheme[theme]}`}
              data-testid="theme-toggle"
            >
              <ThemeIcon size={16} />
              <span>{themeLabel[theme]}</span>
            </Button>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
