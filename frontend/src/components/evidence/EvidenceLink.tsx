import { FileText } from 'lucide-react'
import { lazy, Suspense, useState, type ReactNode } from 'react'

const PageViewer = lazy(() => import('./PageViewer').then((m) => ({ default: m.PageViewer })))

interface Props {
  documentId: number
  pageNo?: number
  pageCount?: number | null
  spanIds?: number[]
  title?: string
  children?: ReactNode
}

/** Clickable citation: opens the source page with the cited lines highlighted. */
export function EvidenceLink({
  documentId,
  pageNo = 1,
  pageCount,
  spanIds,
  title,
  children,
}: Props) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-accent underline-offset-2 hover:underline"
        data-testid="evidence-link"
      >
        <FileText size={14} aria-hidden />
        {children ?? `doc ${documentId}, p.${pageNo}`}
      </button>
      {open && (
        <Suspense fallback={null}>
          <PageViewer
            documentId={documentId}
            initialPage={pageNo}
            pageCount={pageCount}
            highlightSpanIds={spanIds}
            title={title}
            onClose={() => setOpen(false)}
          />
        </Suspense>
      )}
    </>
  )
}
