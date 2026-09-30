import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'

import { Providers } from './app/providers'
import { createAppRouter } from './app/router'
import { syncThemeColor } from './lib/offline/pwa'
import { registerServiceWorker } from './lib/offline/register'
// Self-hosted fonts (CSP font-src 'self'; no FOUT reflow from a late web-font swap).
import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/600.css'
import './styles/index.css'

const root = document.getElementById('root')
if (!root) throw new Error('#root element missing from index.html')

createRoot(root).render(
  <StrictMode>
    <Providers>
      <RouterProvider router={createAppRouter()} />
    </Providers>
  </StrictMode>,
)

// Installed-app polish (FRONTEND_PLAN §12): status-bar colour follows the theme, and the
// service worker (production only) keeps the shell and downloaded well packs offline.
syncThemeColor()
void registerServiceWorker()
