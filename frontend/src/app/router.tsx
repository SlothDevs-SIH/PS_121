import { lazy, Suspense, type ComponentType } from 'react'
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { SkeletonBlock } from '../components/ui/Skeleton'
import { NotFound } from '../pages/NotFound'
import { PlannedScreen } from '../pages/PlannedScreen'
import { SystemStatus } from '../pages/SystemStatus'
import { AppShell } from './AppShell'
import { SCREENS } from './screens'

// Heavier screens are split into their own chunks (map libraries, tables) and loaded on demand.
// Route config is not hot-reloadable anyway, so fast-refresh's one-export rule doesn't apply.
// oxlint-disable-next-line react/only-export-components
const WellMapPage = lazy(() =>
  import('../pages/WellMapPage').then((m) => ({ default: m.WellMapPage })),
)
// oxlint-disable-next-line react/only-export-components
const IngestPage = lazy(() =>
  import('../pages/IngestPage').then((m) => ({ default: m.IngestPage })),
)
// oxlint-disable-next-line react/only-export-components
const DashboardPage = lazy(() =>
  import('../pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
// oxlint-disable-next-line react/only-export-components
const CorrelationPage = lazy(() =>
  import('../pages/CorrelationPage').then((m) => ({ default: m.CorrelationPage })),
)
// oxlint-disable-next-line react/only-export-components
const Well360Page = lazy(() =>
  import('../pages/Well360Page').then((m) => ({ default: m.Well360Page })),
)
// oxlint-disable-next-line react/only-export-components
const SearchPage = lazy(() =>
  import('../pages/SearchPage').then((m) => ({ default: m.SearchPage })),
)

// oxlint-disable-next-line react/only-export-components
const LedgerPage = lazy(() =>
  import('../pages/LedgerPage').then((m) => ({ default: m.LedgerPage })),
)

// oxlint-disable-next-line react/only-export-components
const LiveMonitorPage = lazy(() =>
  import('../pages/LiveMonitorPage').then((m) => ({ default: m.LiveMonitorPage })),
)
// oxlint-disable-next-line react/only-export-components
const AlertsPage = lazy(() =>
  import('../pages/AlertsPage').then((m) => ({ default: m.AlertsPage })),
)

/** Built screens map to real components; everything else renders its PlannedScreen. */
const builtScreens: Record<string, ComponentType> = {
  dashboard: DashboardPage,
  system: SystemStatus,
  map: WellMapPage,
  documents: IngestPage,
  correlation: CorrelationPage,
  well360: Well360Page,
  search: SearchPage,
  ledger: LedgerPage,
  live: LiveMonitorPage,
  alerts: AlertsPage,
}

const loading = (
  <div className="space-y-4" aria-busy="true">
    <SkeletonBlock className="h-8 w-56" />
    <SkeletonBlock className="h-64 w-full" />
  </div>
)

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      // Part 1 links to the upload screen keep working.
      { path: 'ingest', element: <Navigate to="/documents" replace /> },
      ...SCREENS.map((s): RouteObject => {
        const Built = builtScreens[s.id]
        const element = Built ? (
          <Suspense fallback={loading}>
            <Built />
          </Suspense>
        ) : (
          <PlannedScreen screen={s} />
        )
        if (s.path === '/') return { index: true, element }
        return { path: s.path.replace(/^\//, ''), element }
      }),
      { path: '*', element: <NotFound /> },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
