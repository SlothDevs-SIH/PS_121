import { ChevronRight, HardHat, Menu, Monitor, Ruler, Search } from 'lucide-react'
import { matchPath, useLocation } from 'react-router'

import { SCREENS } from '../../app/screens'
import { useUiStore } from '../../stores/ui'
import { BackendStatus } from '../BackendStatus'
import { Button } from '../ui/Button'
import { ThemeSwitcher } from './ThemeSwitcher'
import { WellTypeSwitcher } from './WellTypeSwitcher'

function useScreenTitle(): string {
  const { pathname } = useLocation()
  const screen = SCREENS.find((s) => matchPath({ path: s.path, end: true }, pathname))
  return screen?.title ?? 'Not found'
}

export function Topbar() {
  const title = useScreenTitle()
  const mode = useUiStore((s) => s.mode)
  const setMode = useUiStore((s) => s.setMode)
  const units = useUiStore((s) => s.units)
  const setUnits = useUiStore((s) => s.setUnits)
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen)
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen)
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

  return (
    <header className="sticky top-0 z-(--z-sticky) flex h-14 items-center gap-2 border-b border-border bg-glass px-3 backdrop-blur-md md:px-4">
      <Button
        className="md:hidden"
        onClick={() => setMobileNavOpen(true)}
        aria-label="Open navigation"
        data-testid="mobile-nav-toggle"
      >
        <Menu size={18} />
      </Button>
      <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1 text-sm sm:flex">
        <span className="text-muted">SMRITI</span>
        <ChevronRight size={14} aria-hidden className="text-muted" />
        <span className="truncate font-medium text-text" data-testid="breadcrumb-current">
          {title}
        </span>
      </nav>

      <div className="mx-auto hidden md:block">
        <WellTypeSwitcher />
      </div>
      <div className="mx-auto md:hidden">
        <WellTypeSwitcher compact />
      </div>

      <div className="flex items-center gap-0.5 sm:gap-1 [&>button]:px-2 sm:[&>button]:px-3">
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          aria-label="Search wells, documents and pages"
          data-testid="palette-trigger"
          className="flex h-9 items-center gap-2 rounded-lg border border-border bg-surface-2 px-2.5 text-sm text-muted hover:text-text"
        >
          <Search size={15} aria-hidden />
          <span className="hidden lg:inline">Search</span>
          <kbd className="hidden rounded border border-border px-1 font-mono text-[0.65rem] lg:inline">
            {isMac ? '⌘' : 'Ctrl'} K
          </kbd>
        </button>
        <div className="hidden lg:block">
          <BackendStatus />
        </div>
        <Button
          onClick={() => setMode(mode === 'office' ? 'field' : 'office')}
          aria-label={`Switch to ${mode === 'office' ? 'field' : 'office'} view`}
          title={mode === 'office' ? 'Office view' : 'Field view'}
          data-testid="mode-toggle"
        >
          {mode === 'office' ? <Monitor size={16} /> : <HardHat size={16} />}
          <span className="hidden xl:inline">{mode === 'office' ? 'Office' : 'Field'}</span>
        </Button>
        <Button
          onClick={() => setUnits(units === 'metric' ? 'oilfield' : 'metric')}
          aria-label={`Units: ${units}. Switch to ${units === 'metric' ? 'oilfield' : 'metric'}`}
          title={units === 'metric' ? 'Metric units' : 'Oilfield units'}
          data-testid="units-toggle"
        >
          <Ruler size={16} />
          <span className="hidden xl:inline">{units === 'metric' ? 'Metric' : 'Oilfield'}</span>
        </Button>
        <ThemeSwitcher />
      </div>
    </header>
  )
}
