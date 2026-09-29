import type { PageOut } from '../../lib/api/client'
import { cn } from '../../lib/cn'

/** The stored page image with every extracted line outlined and the selected ones filled. */
export function PageImage({
  page,
  documentId,
  selected,
  onToggle,
}: {
  page: PageOut
  documentId: number
  selected: Set<number>
  onToggle?: (id: number) => void
}) {
  return (
    <div className="relative w-full" data-testid="page-image-wrap">
      <img
        src={page.image_url}
        alt={`Page ${page.page_no} of document ${documentId}`}
        className="block w-full rounded border border-border bg-white"
      />
      {page.spans.map((s) => {
        const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = s.bbox
        const on = selected.has(s.id)
        const box = {
          left: `${x0 * 100}%`,
          top: `${y0 * 100}%`,
          width: `${(x1 - x0) * 100}%`,
          height: `${(y1 - y0) * 100}%`,
        }
        // Without a toggle the boxes are only a highlight, not controls.
        if (!onToggle)
          return (
            <span
              key={s.id}
              title={s.text}
              aria-hidden
              data-highlighted={on}
              className={cn(
                'absolute rounded-sm',
                on ? 'border border-accent bg-accent/25 ring-2 ring-accent' : '',
              )}
              style={box}
            />
          )
        return (
          <button
            key={s.id}
            type="button"
            title={s.text}
            aria-label={`Line ${s.line_no + 1}: ${s.text}`}
            data-highlighted={on}
            onClick={() => onToggle(s.id)}
            className={cn(
              'absolute rounded-sm border',
              on
                ? 'border-accent bg-accent/25 ring-2 ring-accent'
                : 'border-transparent hover:border-accent/60',
            )}
            style={box}
          />
        )
      })}
    </div>
  )
}
