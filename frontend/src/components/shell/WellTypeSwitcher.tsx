import { Layers } from 'lucide-react'
import { motion } from 'motion/react'
import { useId } from 'react'

import { cn } from '../../lib/cn'
import { activePillTransition } from '../../lib/motion'
import { FLUID_ORDER, FLUIDS } from '../../lib/wellTypes'
import { useUiStore, type WellTypeFilter } from '../../stores/ui'

const OPTIONS: { id: WellTypeFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  ...FLUID_ORDER.map((f) => ({ id: f, label: FLUIDS[f].label })),
]

/** Global Oil / Gas / Water / All filter (FRONTEND_SPEC §3.2); every well list reads it. */
export function WellTypeSwitcher({ compact = false }: { compact?: boolean }) {
  const value = useUiStore((s) => s.wellType)
  const setValue = useUiStore((s) => s.setWellType)
  const pillId = useId()

  return (
    <div
      role="radiogroup"
      aria-label="Well type filter"
      data-testid="well-type-switcher"
      className="flex items-center rounded-full border border-border bg-surface-2 p-0.5"
    >
      {OPTIONS.map((o) => {
        const selected = value === o.id
        const Icon = o.id === 'all' ? Layers : FLUIDS[o.id].icon
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={o.label}
            title={`Show ${o.id === 'all' ? 'all wells' : FLUIDS[o.id].plural.toLowerCase()}`}
            onClick={() => setValue(o.id)}
            className={cn(
              'relative flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors',
              selected ? 'text-text' : 'text-muted hover:text-text',
            )}
          >
            {selected && (
              <motion.span
                layoutId={`${pillId}-pill`}
                transition={activePillTransition}
                className="absolute inset-0 rounded-full bg-surface shadow-card"
                aria-hidden
              />
            )}
            <Icon
              size={14}
              aria-hidden
              className={cn('relative', o.id !== 'all' && FLUIDS[o.id].textClass)}
            />
            {!compact && <span className="relative">{o.label}</span>}
          </button>
        )
      })}
    </div>
  )
}
