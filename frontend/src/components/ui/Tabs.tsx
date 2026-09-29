import { motion } from 'motion/react'
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'

import { cn } from '../../lib/cn'
import { activePillTransition } from '../../lib/motion'

export interface TabSpec<T extends string> {
  id: T
  label: string
  icon?: ReactNode
  count?: number
}

/** WAI-ARIA tabs: arrow keys move between tabs, the panel is labelled by its tab. */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  idPrefix,
}: {
  tabs: TabSpec<T>[]
  value: T
  onChange: (v: T) => void
  label: string
  idPrefix: string
}) {
  const pill = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const onKey = (e: KeyboardEvent, i: number) => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!step && e.key !== 'Home' && e.key !== 'End') return
    e.preventDefault()
    const next =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? tabs.length - 1
          : (i + step + tabs.length) % tabs.length
    onChange(tabs[next]!.id)
    refs.current[next]?.focus()
  }
  return (
    <div
      role="tablist"
      aria-label={label}
      className="flex max-w-full items-center gap-1 overflow-x-auto border-b border-border"
    >
      {tabs.map((t, i) => {
        const selected = t.id === value
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${t.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${t.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              'relative flex items-center gap-1.5 px-3 py-2 text-sm font-medium whitespace-nowrap',
              selected ? 'text-text' : 'text-muted hover:text-text',
            )}
          >
            {t.icon}
            {t.label}
            {t.count !== undefined && (
              <span className="num rounded-full bg-surface-2 px-1.5 text-xs text-muted">
                {t.count}
              </span>
            )}
            {selected && (
              <motion.span
                layoutId={`${pill}-tab`}
                transition={activePillTransition}
                className="absolute inset-x-1 -bottom-px h-0.5 rounded-full bg-accent"
                aria-hidden
              />
            )}
          </button>
        )
      })}
    </div>
  )
}

export function TabPanel({
  idPrefix,
  id,
  children,
  className,
}: {
  idPrefix: string
  id: string
  children: ReactNode
  className?: string
}) {
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-tab-${id}`}
      className={className}
    >
      {children}
    </div>
  )
}
