import { Bell, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'

import { useAlertsFeed } from '../../hooks/useLive'
import type { AlertOut } from '../../lib/api/client'
import { useMe } from '../../lib/api/hooks'
import { Badge } from '../ui/Badge'

const TOAST_MS = 10_000
const MAX_TOASTS = 4
const SEVERITY_TONE = { critical: 'danger', warning: 'warn', info: 'info' } as const

/**
 * Every alert pushed over /ws/alerts, anywhere in the app: a toast (critical ones stay
 * until closed and are announced assertively) and an unseen count in the tab title,
 * cleared when the Alerts screen is opened.
 */
export function AlertToaster() {
  const me = useMe()
  const canRead = me.data?.permissions.includes('read_live') ?? false
  const [toasts, setToasts] = useState<{ alert: AlertOut; action: string }[]>([])
  const [unseen, setUnseen] = useState(0)
  const { pathname } = useLocation()
  const baseTitle = useRef(typeof document !== 'undefined' ? document.title : 'SMRITI')

  const onAlert = useCallback((alert: AlertOut, action: string) => {
    setToasts((t) =>
      [{ alert, action }, ...t.filter((x) => x.alert.id !== alert.id)].slice(0, MAX_TOASTS),
    )
    setUnseen((n) => n + 1)
    if (alert.severity !== 'critical')
      setTimeout(() => setToasts((t) => t.filter((x) => x.alert.id !== alert.id)), TOAST_MS)
  }, [])
  useAlertsFeed({ enabled: canRead, onAlert })

  const onAlertsPage = pathname.startsWith('/alerts')
  const shown = onAlertsPage ? 0 : unseen
  useEffect(() => {
    document.title = shown > 0 ? `(${shown}) ${baseTitle.current}` : baseTitle.current
  }, [shown])
  useEffect(() => {
    if (!onAlertsPage) return
    const t = setTimeout(() => setUnseen(0), 0)
    return () => clearTimeout(t)
  }, [onAlertsPage])

  const close = (id: number) => setToasts((t) => t.filter((x) => x.alert.id !== id))
  return (
    <div
      className="pointer-events-none fixed right-4 bottom-4 z-(--z-toast) flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col gap-2"
      data-testid="alert-toasts"
    >
      {toasts.map(({ alert: a, action }) => (
        <div
          key={a.id}
          role={a.severity === 'critical' ? 'alert' : 'status'}
          className="pointer-events-auto rounded-xl border border-border bg-surface p-3 shadow-card"
          data-testid="alert-toast"
        >
          <div className="flex items-center gap-2">
            <Bell size={14} aria-hidden className="text-accent" />
            <Badge tone={SEVERITY_TONE[a.severity]}>{a.severity}</Badge>
            <span className="text-xs text-muted">
              {a.well_name}
              {action === 'fused' ? ' · updated' : ''}
            </span>
            <button
              type="button"
              onClick={() => close(a.id)}
              aria-label="Close alert notification"
              className="ml-auto rounded p-1 text-muted hover:bg-surface-2"
            >
              <X size={14} aria-hidden />
            </button>
          </div>
          <Link
            to={`/alerts?id=${a.id}`}
            onClick={() => close(a.id)}
            className="mt-1 block text-sm font-medium text-text hover:text-accent"
          >
            {a.title}
          </Link>
        </div>
      ))}
    </div>
  )
}
