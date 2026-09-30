import { CloudDownload, HardDriveDownload, LoaderCircle, RefreshCw, Trash2, X } from 'lucide-react'

import { cn } from '../../lib/cn'
import { formatBytes } from '../../lib/format/units'
import { PACK_CAP_BYTES } from '../../lib/offline/keys'
import { useConnectivity } from '../../lib/offline/online'
import type { PackPhase, PackProgress } from '../../lib/offline/pack'
import { packAge } from '../../lib/offline/packStore'
import { useWellPack } from '../../lib/offline/usePacks'
import { Badge } from '../ui/Badge'

const PHASE_LABEL: Record<PackPhase, string> = {
  well: 'the well',
  knowledge: 'offsets, events and ledger',
  correlation: 'correlation panels',
  evidence: 'report pages',
  images: 'page thumbnails',
}

function percent(p: PackProgress | null): number {
  if (!p || p.total === 0) return 0
  return Math.min(100, Math.round((p.done / p.total) * 100))
}

const chip =
  'inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-text hover:bg-surface-2 disabled:opacity-60'

/**
 * "Download well pack" (FRONTEND_PLAN §12): stores this well's offsets, correlation panels,
 * risk profile, lessons, ledger rows and small report-page images on the device, so Map,
 * Correlation, Well 360 and Ledger still open for it offline. Hidden where the browser
 * cannot keep one (no service worker or Cache Storage, e.g. plain http on a LAN address).
 */
export function WellPackButton({ wellId, className }: { wellId: number; className?: string }) {
  const pack = useWellPack(wellId)
  const connectivity = useConnectivity()
  if (!pack.supported) return null
  const online = connectivity === 'online'
  const { meta, progress, busy } = pack

  return (
    <span
      className={cn('inline-flex flex-wrap items-center gap-2', className)}
      data-testid="well-pack"
    >
      {busy ? (
        <>
          <span className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm text-text">
            <LoaderCircle
              size={14}
              aria-hidden
              className="animate-spin motion-reduce:animate-none"
            />
            Packing {progress ? PHASE_LABEL[progress.phase] : 'the well'}…
            <span
              role="progressbar"
              aria-label="Well pack download"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent(progress)}
              className="relative h-1.5 w-20 overflow-hidden rounded-full bg-surface-2"
            >
              <span
                className="absolute inset-0 origin-left rounded-full bg-accent transition-transform"
                style={{ transform: `scaleX(${percent(progress) / 100})` }}
              />
            </span>
          </span>
          <button type="button" className={chip} onClick={pack.cancel}>
            <X size={14} aria-hidden /> Cancel
          </button>
        </>
      ) : meta ? (
        <>
          <Badge tone="ok" data-testid="well-pack-ready">
            <HardDriveDownload size={12} aria-hidden />
            Offline pack · {formatBytes(meta.bytes)} · updated {packAge(meta.createdAt)}
          </Badge>
          <button
            type="button"
            className={chip}
            onClick={() => void pack.download()}
            disabled={!online}
            title={online ? 'Download this well again with the latest data' : 'Needs a connection'}
          >
            <RefreshCw size={14} aria-hidden /> Update pack
          </button>
          <button type="button" className={chip} onClick={() => void pack.remove()}>
            <Trash2 size={14} aria-hidden /> Remove pack
          </button>
        </>
      ) : (
        <button
          type="button"
          className={chip}
          onClick={() => void pack.download()}
          disabled={!online}
          title={
            online
              ? `Offsets, correlation, risk, lessons, ledger and report pages for offline use (up to ${formatBytes(PACK_CAP_BYTES)})`
              : 'Needs a connection'
          }
          data-testid="well-pack-download"
        >
          <CloudDownload size={14} aria-hidden /> Download well pack
        </button>
      )}
      <span role="status" aria-live="polite" className="text-xs" data-testid="well-pack-status">
        {busy && progress ? (
          <span className="num text-muted">
            {progress.done} of {progress.total} · {formatBytes(progress.bytes)}
          </span>
        ) : pack.error ? (
          <span className="text-danger">{pack.error}</span>
        ) : meta && meta.imagesSkipped > 0 ? (
          <span className="text-warn">
            {meta.imagesSkipped} page images left out to stay under {formatBytes(meta.capBytes)}.
          </span>
        ) : null}
      </span>
    </span>
  )
}
