import { Link } from 'react-router'

import { useReadiness } from '../lib/api/hooks'
import { Badge } from './ui/Badge'

/** Header pill: ready / degraded (503 with a report) / unreachable. Links to System Status. */
export function BackendStatus() {
  const { data, isError, isPending } = useReadiness()

  let tone: 'ok' | 'warn' | 'danger' | 'neutral' = 'neutral'
  let label = 'Checking backend…'
  if (isError) {
    tone = 'danger'
    label = 'Backend unreachable'
  } else if (data?.status === 'ready') {
    tone = 'ok'
    label = 'Backend ready'
  } else if (data) {
    const down = data.components.filter((c) => !c.ok).map((c) => c.name)
    tone = 'warn'
    label = `Degraded: ${down.join(', ')}`
  }

  return (
    <Link to="/system" aria-label={`${label}. Open system status`} data-testid="backend-status">
      <Badge tone={tone} aria-busy={isPending}>
        <span aria-hidden className="size-2 rounded-full bg-current" />
        {label}
      </Badge>
    </Link>
  )
}
