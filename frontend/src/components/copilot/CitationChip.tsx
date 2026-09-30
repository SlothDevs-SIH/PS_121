import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router'

import { recordHref, type CopilotCitation } from '../../lib/copilot'

const PageViewer = lazy(() =>
  import('../evidence/PageViewer').then((m) => ({ default: m.PageViewer })),
)

const chip =
  'mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1 align-baseline text-[0.7rem] font-semibold leading-none num'

/**
 * An inline `[n]` mark. A report page opens the evidence viewer at that page with the cited
 * lines highlighted (the same viewer as `EvidenceLink`); a database record links to its
 * screen. Until the `citations` event arrives (it follows the answer) the mark is inert.
 */
export function CitationChip({ n, citation }: { n: number; citation?: CopilotCitation }) {
  const [open, setOpen] = useState(false)
  if (!citation)
    return (
      <span className={`${chip} bg-surface-2 text-muted`} data-testid="citation-pending">
        {n}
      </span>
    )
  const name = `Source ${n}: ${citation.label}${citation.filename ? `, ${citation.filename}` : ''}`
  if (citation.kind === 'page' && citation.document_id !== null) {
    const documentId = citation.document_id
    return (
      <>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`${chip} bg-accent/15 text-accent ring-1 ring-accent/40 hover:bg-accent/25`}
          aria-label={`${name}. Open the page`}
          title={name}
          data-testid="citation-chip"
        >
          {n}
        </button>
        {open && (
          <Suspense fallback={null}>
            <PageViewer
              documentId={documentId}
              initialPage={citation.page_no ?? 1}
              highlightSpanIds={citation.span_ids}
              title={citation.filename ?? citation.label}
              onClose={() => setOpen(false)}
            />
          </Suspense>
        )}
      </>
    )
  }
  const href = recordHref(citation)
  const label = `${name} (database record)`
  return href ? (
    <Link
      to={href}
      className={`${chip} bg-info-bg text-info ring-1 ring-info/40 hover:underline`}
      aria-label={`${label}. Open it`}
      title={label}
      data-testid="citation-chip"
    >
      {n}
    </Link>
  ) : (
    <span
      className={`${chip} bg-info-bg text-info`}
      title={label}
      aria-label={label}
      role="note"
      data-testid="citation-chip"
    >
      {n}
    </span>
  )
}
