import { lazy, Suspense, type ComponentType } from 'react'
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

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

/** Built screens map to real components; everything else renders its PlannedScreen. */
const builtScreens: Record<string, ComponentType> = {
  system: SystemStatus,
  map: WellMapPage,
  ingest: IngestPage,
}

const loading = <p className="text-sm text-muted">Loading…</p>

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/system" replace /> },
      ...SCREENS.map((s) => {
        const Built = builtScreens[s.id]
        return {
          path: s.path.replace(/^\//, ''),
          element: Built ? (
            <Suspense fallback={loading}>
              <Built />
            </Suspense>
          ) : (
            <PlannedScreen screen={s} />
          ),
        }
      }),
      { path: '*', element: <NotFound /> },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
