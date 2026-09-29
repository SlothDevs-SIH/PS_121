import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { useDocumentPage } from '../../lib/api/hooks'
import { cn } from '../../lib/cn'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { PageImage } from './PageImage'

interface Props {
  documentId: number
  title?: string
  initialPage?: number
  pageCount?: number | null
  highlightSpanIds?: number[]
  onClose: () => void
}

/**
 * Evidence viewer: the stored page image with every extracted text line outlined and the
 * cited lines highlighted (master plan principle P1 — "no citation, no claim").
 */
export function PageViewer({
  documentId,
  title,
  initialPage = 1,
  pageCount,
  highlightSpanIds = [],
  onClose,
}: Props) {
  const [pageNo, setPageNo] = useState(initialPage)
  const [selected, setSelected] = useState<Set<number>>(new Set(highlightSpanIds))
  const { data: page, isPending, isError } = useDocumentPage(documentId, pageNo)
  const closeRef = useRef<HTMLButtonElement>(null)
  const last = pageCount ?? 1

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      previous?.focus()
    }
  }, [onClose])

  const toggle = (id: number) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className="fixed inset-0 z-[1000] flex items-stretch justify-center bg-black/60 p-2 md:p-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="page-viewer-title"
        className="flex w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-border bg-surface"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <h2 id="page-viewer-title" className="truncate font-semibold text-text">
              {title ?? `Document ${documentId}`} — page {pageNo}
              {pageCount ? ` of ${pageCount}` : ''}
            </h2>
            {page?.ocr_used && (
              <Badge tone="info">
                OCR · mean confidence {Math.round(page.ocr_mean_conf ?? 0)}%
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button
              aria-label="Previous page"
              disabled={pageNo <= 1}
              onClick={() => setPageNo((p) => p - 1)}
            >
              <ChevronLeft size={16} />
            </Button>
            <Button
              aria-label="Next page"
              disabled={pageNo >= last}
              onClick={() => setPageNo((p) => p + 1)}
            >
              <ChevronRight size={16} />
            </Button>
            <a
              className="px-2 text-sm text-accent underline"
              href={`/api/v1/documents/${documentId}/file`}
              target="_blank"
              rel="noreferrer"
            >
              Original file
            </a>
            <Button ref={closeRef} aria-label="Close viewer" onClick={onClose}>
              <X size={16} />
            </Button>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 gap-3 overflow-auto p-3 md:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="relative self-start">
            {isPending && <p className="text-sm text-muted">Loading page…</p>}
            {isError && <p className="text-sm text-danger">Page could not be loaded.</p>}
            {page && (
              <PageImage
                page={page}
                documentId={documentId}
                selected={selected}
                onToggle={toggle}
              />
            )}
          </div>
          <ol
            className="space-y-1 text-sm"
            aria-label="Extracted text lines"
            data-testid="span-list"
          >
            {page?.spans.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => toggle(s.id)}
                  className={cn(
                    'w-full rounded px-2 py-1 text-left hover:bg-surface-2',
                    selected.has(s.id) && 'bg-accent/15 ring-1 ring-accent',
                  )}
                >
                  <span className="block break-words text-text">{s.text}</span>
                  {s.conf !== null && (
                    <span className="text-xs text-muted">OCR confidence {Math.round(s.conf)}%</span>
                  )}
                </button>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}
