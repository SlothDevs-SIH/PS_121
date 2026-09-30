import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { useLocation } from 'react-router'

import { OfflineBanner } from '../components/offline/OfflineBanner'
import { OfflineGate } from '../components/offline/OfflineGate'
import { UpdatePrompt } from '../components/offline/UpdatePrompt'
import { AlertToaster } from '../components/shell/AlertToaster'
import { AnimatedOutlet } from '../components/shell/AnimatedOutlet'
import { CommandPaletteHost } from '../components/shell/CommandPaletteHost'
import { Sidebar } from '../components/shell/Sidebar'
import { Topbar } from '../components/shell/Topbar'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { easeOutExpo } from '../lib/motion'
import { useUiStore } from '../stores/ui'

/**
 * App shell (FRONTEND_SPEC §3): collapsible sidebar, sticky top bar, animated outlet.
 * The sidebar column width changes through a CSS grid-template-columns transition (§7
 * rule 4), never a per-frame JS width animation. Below `lg` it is a rail; below `md` it is
 * an off-canvas drawer. Installed on a phone (viewport-fit=cover), the safe-area insets keep
 * the shell clear of notches and rounded corners.
 */
export function AppShell() {
  const collapsedPref = useUiStore((s) => s.sidebarCollapsed)
  const forceRail = useUiStore((s) => s.forceRail)
  const mobileOpen = useUiStore((s) => s.mobileNavOpen)
  const setMobileOpen = useUiStore((s) => s.setMobileNavOpen)
  const wide = useMediaQuery('(min-width: 1024px)')
  const location = useLocation()
  const collapsed = collapsedPref || forceRail || !wide

  useEffect(() => setMobileOpen(false), [location.pathname, setMobileOpen])

  return (
    <div
      className="grid min-h-screen bg-bg pr-[env(safe-area-inset-right)] pl-[env(safe-area-inset-left)] md:grid-cols-[var(--sidebar-w)_minmax(0,1fr)] md:transition-[grid-template-columns] md:duration-300 md:ease-[cubic-bezier(0.22,1,0.36,1)]"
      style={{
        ['--sidebar-w' as string]: collapsed ? 'var(--sidebar-rail)' : 'var(--sidebar-full)',
      }}
      data-sidebar={collapsed ? 'rail' : 'full'}
      data-testid="app-shell"
    >
      <aside className="sticky top-0 z-(--z-sidebar) hidden h-screen border-r border-border bg-surface pt-[env(safe-area-inset-top)] md:block">
        <Sidebar collapsed={collapsed} canToggle={wide && !forceRail} />
      </aside>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            key="drawer"
            className="fixed inset-0 z-(--z-modal) md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <button
              type="button"
              aria-label="Close navigation"
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              className="absolute inset-y-0 left-0 w-72 border-r border-border bg-surface pt-[env(safe-area-inset-top)] pl-[env(safe-area-inset-left)]"
              initial={{ x: '-100%' }}
              animate={{ x: 0, transition: { duration: 0.28, ease: easeOutExpo } }}
              exit={{ x: '-100%', transition: { duration: 0.18 } }}
            >
              <Sidebar collapsed={false} drawer />
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-col">
        <Topbar />
        <OfflineBanner />
        <main className="min-w-0 flex-1 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] md:p-6 md:pb-[max(1.5rem,env(safe-area-inset-bottom))]">
          <OfflineGate>
            <AnimatedOutlet />
          </OfflineGate>
        </main>
      </div>
      <CommandPaletteHost />
      <AlertToaster />
      <UpdatePrompt />
    </div>
  )
}
