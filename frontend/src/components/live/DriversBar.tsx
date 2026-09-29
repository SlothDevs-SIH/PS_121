import type { AlertDriver } from '../../lib/api/client'
import { formatValue } from '../../lib/liveView'
import { pct } from '../../lib/risk'

/** Why the classifier scored high: each driver's drop in probability when reset to its
 * typical value, with the value and the typical value as text. */
export function DriversBar({ drivers }: { drivers: AlertDriver[] }) {
  if (drivers.length === 0)
    return <p className="text-sm text-muted">No model drivers for this alert.</p>
  const max = Math.max(...drivers.map((d) => d.contribution))
  return (
    <ul className="space-y-2" data-testid="drivers">
      {drivers.map((d) => (
        <li
          key={`${d.feature}-${d.contribution}`}
          className="grid grid-cols-[minmax(0,12rem)_1fr_auto] items-center gap-3 text-sm"
        >
          <span className="truncate" title={d.feature}>
            {d.label}
          </span>
          <span className="block h-2 rounded-full bg-surface-2" aria-hidden>
            <span
              className="block h-2 rounded-full bg-accent"
              style={{ width: `${(d.contribution / (max || 1)) * 100}%` }}
            />
          </span>
          <span className="num text-xs text-muted">
            −{pct(d.contribution)} if typical · now {formatValue(d.value, 2)} vs{' '}
            {formatValue(d.typical, 2)}
          </span>
        </li>
      ))}
    </ul>
  )
}
