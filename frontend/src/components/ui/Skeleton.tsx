import type { HTMLAttributes } from 'react'

import { cn } from '../../lib/cn'

/** Shimmer placeholder sized like the content it stands in for (§7 rule 3). */
export function SkeletonBlock({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cn('skeleton rounded-md', className)} {...props} />
}
