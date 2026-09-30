import { CloudOff } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, matchPath, useLocation } from 'react-router'

import { SCREENS, type ScreenSpec } from '../../app/screens'
import { NEEDS_NETWORK, useConnectivity } from '../../lib/offline/online'
import { Card } from '../ui/Card'

/** The live-only screen (NEEDS_NETWORK) a path belongs to, if any. */
export function networkScreenAt(pathname: string): ScreenSpec | null {
  return (
    SCREENS.find((s) => NEEDS_NETWORK.has(s.id) && matchPath({ path: s.path }, pathname)) ?? null
  )
}

/**
 * A live-only screen (live monitor, alerts, search and its copilot) opened without the
 * connection, e.g. from a bookmark or the installed app's "Knowledge Search" shortcut,
 * says why it cannot open instead of failing (FRONTEND_PLAN §12). A screen that was open
 * when the link dropped stays mounted: its own reconnecting state keeps what it has.
 */
export function OfflineGate({ children }: { children: ReactNode }) {
  const connectivity = useConnectivity()
  const { pathname } = useLocation()
  const [openedOnline, setOpenedOnline] = useState<string | null>(null)
  // Adjusted during render (not in an effect) so the gate never flashes on a live page.
  if (connectivity === 'online' && openedOnline !== pathname) setOpenedOnline(pathname)

  const screen = networkScreenAt(pathname)
  if (connectivity === 'online' || !screen || openedOnline === pathname) return children

  return (
    <div className="mx-auto max-w-xl space-y-4 pt-6" data-testid="offline-gate">
      <h1 className="text-2xl font-semibold tracking-tight text-text">{screen.title}</h1>
      <Card className="flex items-start gap-3">
        <CloudOff size={20} aria-hidden className="mt-0.5 shrink-0 text-warn" />
        <div className="space-y-2 text-sm">
          <p className="text-text">
            This screen needs the connection: live alerts need the link to the server near eRTMAC.
            Nothing live is kept on this device, so it is never shown out of date.
          </p>
          <p className="text-muted">
            Map, Correlation, Well 360, Lessons and Ledger still work for packed wells.
          </p>
          <Link to="/map" className="inline-block font-medium text-accent hover:underline">
            Open the Map Explorer
          </Link>
        </div>
      </Card>
    </div>
  )
}
