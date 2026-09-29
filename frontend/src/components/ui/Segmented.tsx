import { motion } from 'motion/react'
import { useId, type ReactNode } from 'react'

import { cn } from '../../lib/cn'
import { activePillTransition } from '../../lib/motion'

interface Option<T extends string> {
  id: T
  label: string
  icon?: ReactNode
}

/** Segmented control with a sliding selection pill (one layoutId per instance, §5). */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  testId,
}: {
  options: Option<T>[]
  value: T
  onChange: (v: T) => void
  label: string
  testId?: string
}) {
  const id = useId()
  return (
    <div
      role="radiogroup"
      aria-label={label}
      data-testid={testId}
      className="flex items-center rounded-lg border border-border bg-surface-2 p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={value === o.id}
          aria-label={o.label}
          onClick={() => onChange(o.id)}
          className={cn(
            'relative flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium',
            value === o.id ? 'text-text' : 'text-muted hover:text-text',
          )}
        >
          {value === o.id && (
            <motion.span
              layoutId={`${id}-seg`}
              transition={activePillTransition}
              className="absolute inset-0 rounded-md bg-surface shadow-card"
              aria-hidden
            />
          )}
          {o.icon && <span className="relative">{o.icon}</span>}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  )
}
