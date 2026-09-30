import { ServerOff, WifiOff } from 'lucide-react'
import { Link } from 'react-router'

import { useConnectivity } from '../../lib/offline/online'
import { packAge } from '../../lib/offline/packStore'
import { usePacks } from '../../lib/offline/usePacks'

/**
 * The offline banner (FRONTEND_PLAN §12, master plan Q&A): says exactly what still works
 * from the downloaded well packs and what needs the link to the server near eRTMAC.
 */
export function OfflineBanner() {
  const connectivity = useConnectivity()
  const packs = usePacks()
  if (connectivity === 'online') return null
  const list = packs.data ?? []
  const Icon = connectivity === 'offline' ? WifiOff : ServerOff

  return (
    <div
      role="status"
      data-testid="offline-banner"
      className="flex items-start gap-3 border-b border-border bg-warn-bg px-4 py-2 text-sm text-text md:px-6"
    >
      <Icon size={18} aria-hidden className="mt-0.5 shrink-0 text-warn" />
      <div className="min-w-0 space-y-0.5">
        <p>
          <strong className="font-semibold text-warn">
            {connectivity === 'offline' ? 'Offline.' : 'The SMRITI server cannot be reached.'}
          </strong>{' '}
          Map, Correlation, Well 360, Lessons and Ledger work for packed wells
          {list.length > 0 ? ': ' : '. '}
          {list.length > 0 ? (
            list.map((p, i) => (
              <span key={p.wellId}>
                {i > 0 && ', '}
                <Link to={`/wells/${p.wellId}`} className="font-medium text-accent hover:underline">
                  {p.wellName}
                </Link>{' '}
                <span className="text-muted">(updated {packAge(p.createdAt)})</span>
              </span>
            ))
          ) : (
            <span className="text-muted">No well pack is downloaded on this device.</span>
          )}
        </p>
        <p className="text-muted">
          Live monitor, alerts, copilot and new searches need the connection: live alerts need the
          link to the server near eRTMAC.
        </p>
      </div>
    </div>
  )
}
