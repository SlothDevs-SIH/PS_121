import { motion } from 'motion/react'
import type { ReactNode } from 'react'

import { useCountUp } from '../../hooks/useCountUp'
import { cn } from '../../lib/cn'
import { staggerItem } from '../../lib/motion'
import { formatNumber } from '../../lib/format/units'
import { SkeletonBlock } from './Skeleton'

interface Props {
  label: string
  value: number | null
  suffix?: string
  icon: ReactNode
  hint?: ReactNode
  /** Soft pulsing glow for live states (e.g. wells drilling now). */
  live?: boolean
  testId?: string
  footer?: ReactNode
}

export function KpiCard({ label, value, suffix, icon, hint, live, testId, footer }: Props) {
  const shown = useCountUp(value)
  return (
    <motion.div
      variants={staggerItem}
      className={cn(
        'relative overflow-hidden rounded-xl border border-border bg-surface p-4 shadow-card',
      )}
      data-testid={testId}
    >
      {live && (
        <motion.span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-xl ring-2 ring-accent"
          animate={{ opacity: [0.15, 0.55, 0.15] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      <div className="flex items-center justify-between gap-2 text-sm text-muted">
        <span>{label}</span>
        <span className="text-muted">{icon}</span>
      </div>
      <div className="mt-2 flex h-9 items-baseline gap-1">
        {value === null || shown === null ? (
          <SkeletonBlock className="h-8 w-20" />
        ) : (
          <>
            <span className="num text-3xl font-semibold text-text" data-value={value}>
              {formatNumber(Math.round(shown))}
            </span>
            {suffix && <span className="text-sm text-muted">{suffix}</span>}
          </>
        )}
      </div>
      {hint && <div className="mt-1 min-h-5 text-xs text-muted">{hint}</div>}
      {footer && <div className="mt-3">{footer}</div>}
    </motion.div>
  )
}
