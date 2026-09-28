import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

/**
 * An extracted value. Unverified values get a dashed outline (master plan P7): the reader
 * can see at a glance which facts a human has confirmed.
 */
export function ConfidenceValue({
  children,
  verified,
  confidence,
}: {
  children: ReactNode
  verified: boolean
  confidence?: number | null
}) {
  const label = verified
    ? 'Verified by a reviewer'
    : `Unverified${confidence !== null && confidence !== undefined ? ` · confidence ${Math.round(confidence * 100)}%` : ''}`
  return (
    <span
      title={label}
      aria-label={typeof children === 'string' ? `${children} (${label})` : undefined}
      data-verified={verified}
      className={cn('rounded px-1', !verified && 'border border-dashed border-muted')}
    >
      {children}
    </span>
  )
}
