import type { ReactNode } from 'react'

/** Split a snippet at the backend's highlight ranges ([start, end) character offsets). */
export function highlight(text: string, ranges: number[][]): ReactNode[] {
  const out: ReactNode[] = []
  let at = 0
  const sorted = [...ranges]
    .filter((r) => r.length === 2 && r[0]! < r[1]!)
    .sort((a, b) => a[0]! - b[0]!)
  for (const [s, e] of sorted as [number, number][]) {
    if (s < at) continue
    if (s > at) out.push(text.slice(at, s))
    out.push(
      <mark key={s} className="rounded-sm bg-accent/25 px-0.5 text-text">
        {text.slice(s, e)}
      </mark>,
    )
    at = e
  }
  if (at < text.length) out.push(text.slice(at))
  return out
}
