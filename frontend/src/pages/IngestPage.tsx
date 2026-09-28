import { Upload } from 'lucide-react'
import { lazy, Suspense, useRef, useState, type DragEvent } from 'react'

import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge, type Tone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardTitle } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { ApiError, type DocumentSummary, type UploadResult } from '../lib/api/client'
import { useDocuments, useUpload } from '../lib/api/hooks'
import { cn } from '../lib/cn'
import { formatBytes } from '../lib/format/units'

const PageViewer = lazy(() =>
  import('../components/evidence/PageViewer').then((m) => ({ default: m.PageViewer })),
)

const STATUS_TONE: Record<string, Tone> = {
  queued: 'neutral',
  processing: 'info',
  processed: 'ok',
  needs_review: 'warn',
  failed: 'danger',
}
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.tif,.tiff'

export function IngestPage() {
  const [statusFilter, setStatusFilter] = useState('')
  const [results, setResults] = useState<UploadResult[] | null>(null)
  const [dragging, setDragging] = useState(false)
  const [viewing, setViewing] = useState<DocumentSummary | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const docs = useDocuments(statusFilter || undefined)
  const upload = useUpload()

  const send = (files: FileList | File[] | null) => {
    const list = Array.from(files ?? [])
    if (list.length === 0) return
    setResults(null)
    upload.mutate(list, { onSuccess: setResults })
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    send(e.dataTransfer.files)
  }

  const columns: Column<DocumentSummary>[] = [
    { key: 'id', header: 'ID', render: (d) => d.id, sortValue: (d) => d.id, align: 'right' },
    {
      key: 'filename',
      header: 'File',
      render: (d) => <span className="break-all">{d.filename}</span>,
      sortValue: (d) => d.filename,
    },
    { key: 'type', header: 'Type', render: (d) => d.doc_type ?? '—', sortValue: (d) => d.doc_type },
    {
      key: 'well',
      header: 'Well',
      render: (d) =>
        d.well_name ?? <span className="text-warn">{d.raw_well_name ?? 'unknown'}</span>,
      sortValue: (d) => d.well_name ?? d.raw_well_name,
    },
    {
      key: 'date',
      header: 'Report date',
      render: (d) => d.report_date ?? '—',
      sortValue: (d) => d.report_date,
    },
    { key: 'pages', header: 'Pages', render: (d) => d.page_count ?? '—', align: 'right' },
    {
      key: 'status',
      header: 'Status',
      render: (d) => (
        <span className="flex flex-col gap-0.5">
          <Badge tone={STATUS_TONE[d.ingest_status] ?? 'neutral'}>
            {d.ingest_status.replace('_', ' ')}
          </Badge>
          {d.error && <span className="text-xs text-muted">{d.error}</span>}
        </span>
      ),
      sortValue: (d) => d.ingest_status,
    },
  ]

  const counts = docs.data?.status_counts ?? {}
  const uploadError = upload.error instanceof ApiError ? upload.error : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold text-text">Ingestion &amp; Review</h1>
        {docs.data?.items.some((d) => d.synthetic) && <SyntheticBadge />}
        <Badge tone="neutral">Review queue: frontend phase F2</Badge>
      </div>

      <Card>
        <CardTitle>Upload reports</CardTitle>
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border p-6 text-center',
            dragging && 'border-accent bg-accent/10',
          )}
          data-testid="drop-zone"
        >
          <Upload aria-hidden className="text-muted" />
          <p className="text-sm text-muted">
            Drop PDF, PNG, JPEG or TIFF reports here (scanned pages are OCR'd), or
          </p>
          <Button
            variant="primary"
            onClick={() => input.current?.click()}
            disabled={upload.isPending}
          >
            {upload.isPending ? 'Uploading…' : 'Choose files'}
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            aria-label="Choose report files"
            data-testid="file-input"
            onChange={(e) => {
              send(e.target.files)
              e.target.value = ''
            }}
          />
        </div>
        {uploadError && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {uploadError.message} (request {uploadError.requestId ?? 'n/a'})
          </p>
        )}
        {results && (
          <ul className="mt-3 space-y-1 text-sm" data-testid="upload-results">
            {results.map((r) => (
              <li key={r.document_id} className="flex flex-wrap items-center gap-2">
                <Badge tone={r.duplicate ? 'neutral' : 'ok'}>
                  {r.duplicate ? 'already ingested' : 'queued'}
                </Badge>
                <span className="break-all">{r.filename}</span>
                <span className="text-muted">→ document {r.document_id}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="mb-0">Documents</CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="status-counts">
            {Object.entries(counts).map(([k, v]) => (
              <Badge key={k} tone={STATUS_TONE[k] ?? 'neutral'}>
                {k.replace('_', ' ')}: {v}
              </Badge>
            ))}
            <label className="sr-only" htmlFor="status-filter">
              Filter by status
            </label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-md border border-border bg-surface px-2 py-1 text-text"
            >
              <option value="">All statuses</option>
              {Object.keys(STATUS_TONE).map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </select>
          </div>
        </div>
        {docs.isError && <p className="text-sm text-danger">Documents could not be loaded.</p>}
        {docs.data && (
          <>
            <p className="mb-2 text-xs text-muted">
              {docs.data.total} documents · click a row to see the page with its extracted lines ·
              total size {formatBytes(docs.data.items.reduce((a, d) => a + d.size_bytes, 0))}
            </p>
            <DataTable
              testId="documents-table"
              caption="Ingested documents"
              columns={columns}
              rows={docs.data.items}
              rowKey={(d) => d.id}
              initialSort={{ key: 'id', dir: 'desc' }}
              onRowClick={(d) => d.page_count && setViewing(d)}
              selectedKey={viewing?.id ?? null}
              empty="No documents yet — upload a report above."
            />
          </>
        )}
      </Card>

      {viewing && (
        <Suspense fallback={null}>
          <PageViewer
            documentId={viewing.id}
            title={viewing.filename}
            pageCount={viewing.page_count}
            onClose={() => setViewing(null)}
          />
        </Suspense>
      )}
    </div>
  )
}
