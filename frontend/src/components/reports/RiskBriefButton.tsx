import { FileDown, LoaderCircle } from 'lucide-react'
import { useState } from 'react'

import { ApiError } from '../../lib/api/client'
import { useMe, useOffsetBrief } from '../../lib/api/hooks'
import { cn } from '../../lib/cn'
import { formatBytes } from '../../lib/format/units'
import { saveBlob, type BriefProgress } from '../../lib/reports'

function progressText(p: BriefProgress | null): string {
  if (!p || p.received === 0) return 'Preparing the brief…'
  if (p.total) return `Downloading… ${Math.min(100, Math.round((p.received / p.total) * 100))}%`
  return `Downloading… ${formatBytes(p.received)}`
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return 'Backend unreachable: the brief could not be downloaded.'
    if (err.status === 401 || err.status === 403)
      return 'Your role cannot download risk briefs (drilling engineers can).'
    if (err.status === 404) return 'This well was not found.'
    return `The brief could not be made: ${err.message}${err.requestId ? ` (request ${err.requestId})` : ''}`
  }
  return `The brief could not be downloaded: ${String(err)}`
}

/**
 * "Offset Risk Brief (PDF)" for a pre-spud or section-planning meeting: the well, its
 * offsets within `radiusKm`, the offset prior risk by formation, what worked nearby and the
 * report pages behind every number. Fetched as a blob (same origin, session cookie) with
 * progress, then saved under the server's filename.
 */
export function RiskBriefButton({
  wellId,
  wellName,
  radiusKm = 5,
  className,
}: {
  wellId: number
  wellName: string
  radiusKm?: number
  className?: string
}) {
  const brief = useOffsetBrief()
  const me = useMe()
  // The backend enforces read_risk; this only explains up front why the button is off.
  const denied = me.data ? !me.data.permissions.includes('read_risk') : false
  const [progress, setProgress] = useState<BriefProgress | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const radius = Math.min(20, Math.max(0.1, radiusKm))

  const download = () => {
    setProgress(null)
    setSaved(null)
    brief.mutate(
      { wellId, radiusKm: radius, wellName, onProgress: setProgress },
      {
        onSuccess: ({ blob, filename }) => {
          saveBlob(blob, filename)
          setSaved(filename)
        },
      },
    )
  }

  return (
    <span className={cn('inline-flex flex-wrap items-center gap-2', className)}>
      <button
        type="button"
        onClick={download}
        disabled={brief.isPending || denied}
        aria-busy={brief.isPending}
        title={
          denied
            ? 'Needs the risk permission (drilling engineers and admins)'
            : `Offset wells within ${radius} km, offset prior risk by formation, what worked nearby, with report pages`
        }
        className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-text hover:bg-surface-2 disabled:opacity-60"
        data-testid="risk-brief-button"
      >
        {brief.isPending ? (
          <LoaderCircle size={14} aria-hidden className="animate-spin motion-reduce:animate-none" />
        ) : (
          <FileDown size={14} aria-hidden />
        )}
        Offset Risk Brief (PDF)
      </button>
      <span role="status" aria-live="polite" className="text-xs" data-testid="risk-brief-status">
        {denied ? (
          <span className="text-muted">Needs the drilling-engineer role</span>
        ) : brief.isPending ? (
          <span className="num text-muted">{progressText(progress)}</span>
        ) : brief.isError ? (
          <span className="text-danger">{errorText(brief.error)}</span>
        ) : saved ? (
          <span className="text-muted">Saved {saved}</span>
        ) : null}
      </span>
    </span>
  )
}
