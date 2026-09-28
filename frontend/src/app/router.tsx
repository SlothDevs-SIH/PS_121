import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { NotFound } from '../pages/NotFound'
import { PlannedScreen } from '../pages/PlannedScreen'
import { SystemStatus } from '../pages/SystemStatus'
import { AppShell } from './AppShell'
import { SCREENS } from './screens'

/** Built screens map to real components; everything else renders its PlannedScreen. */
const builtScreens: Record<string, () => React.JSX.Element> = {
  system: SystemStatus,
}

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
          element: Built ? <Built /> : <PlannedScreen screen={s} />,
        }
      }),
      { path: '*', element: <NotFound /> },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
