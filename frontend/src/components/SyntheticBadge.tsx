import { Badge } from './ui/Badge'

/** Shown wherever synthetic wells or documents appear (master plan §24 communication rules). */
export function SyntheticBadge({ label = 'SYNTHETIC data' }: { label?: string }) {
  return (
    <Badge
      tone="warn"
      data-testid="synthetic-badge"
      title="Synthetic Upper-Assam-style data, not Oil India data"
    >
      {label}
    </Badge>
  )
}
