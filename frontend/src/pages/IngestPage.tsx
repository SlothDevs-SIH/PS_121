import { ClipboardCheck, FileText, LayoutGrid, List, Search, Upload } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { lazy, Suspense, useMemo, useRef, useState, type DragEvent } from 'react'
import { useSearchParams } from 'react-router'

import { PipelineTimeline } from '../components/documents/Pipeline'
import { ReviewQueue } from '../components/review/ReviewQueue'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge, type Tone } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Segmented } from '../components/ui/Segmented'
import { SkeletonBlock } from '../components/ui/Skeleton'
import { TabPanel, Tabs } from '../components/ui/Tabs'
import { api, ApiError, type DocumentSummary, type UploadResult } from '../lib/api/client'
import { useDocuments, useReviewCounts, useUpload, useWells } from '../lib/api/hooks'
import { cn } from '../lib/cn'
import { formatBytes } from '../lib/format/units'
import { staggerContainer, staggerItem } from '../lib/motion'
import { matchesFilter } from '../lib/wellTypes'
import { useUiStore } from '../stores/ui'

const PageViewer = lazy(() =>
  import('../components/evidence/PageViewer').then((m) => ({ default: m.PageViewer })),
)

const ACCEPT = '.pdf,.png,.jpg,.jpeg,.tif,.tiff'
const STATUS_TONE: Record<string, Tone> = {
  queued: 'neutral',
  processing: 'info',
  processed: 'ok',
  needs_review: 'warn',
  failed: 'danger',
}
const TYPES = ['all', 'DDR', 'WCR', 'other'] as const
type TypeFilter = (typeof TYPES)[number]

export function IngestPage() {
  const [params, setParams] = useSearchParams()
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [statusFilter, setStatusFilter] = useState('')
  const [results, setResults] = useState<UploadResult[] | null>(null)
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const wellType = useUiStore((s) => s.wellType)
  const docs = useDocuments(statusFilter || undefined)
  const wells = useWells()
  const upload = useUpload()
  const reviewCounts = useReviewCounts()
  const section = params.get('view') === 'review' ? 'review' : 'library'

  const fluidByWell = useMemo(
    () => new Map((wells.data?.items ?? []).map((w) => [w.id, w.fluid_type ?? null])),
    [wells.data],
  )
  const items = useMemo(() => {
    const q = query.trim().toLowerCase()
    const newestFirst = [...(docs.data?.items ?? [])].sort((a, b) => b.id - a.id)
    return newestFirst.filter((d) => {
      if (wellType !== 'all' && !(d.well_id && matchesFilter(fluidByWell.get(d.well_id), wellType)))
        return false
      if (typeFilter === 'other' && (d.doc_type === 'DDR' || d.doc_type === 'WCR')) return false
      if (typeFilter !== 'all' && typeFilter !== 'other' && d.doc_type !== typeFilter) return false
      if (!q) return true
      return [d.filename, d.well_name ?? '', d.raw_well_name ?? ''].some((v) =>
        v.toLowerCase().includes(q),
      )
    })
  }, [docs.data, query, typeFilter, wellType, fluidByWell])

  const viewingId = Number(params.get('doc')) || null
  const viewing = (docs.data?.items ?? []).find((d) => d.id === viewingId) ?? null
  const open = (d: DocumentSummary) => {
    if (!d.page_count) return
    const next = new URLSearchParams(params)
    next.set('doc', String(d.id))
    setParams(next, { replace: true })
  }
  const close = () => {
    const next = new URLSearchParams(params)
    next.delete('doc')
    setParams(next, { replace: true })
  }

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

  const all = docs.data?.items ?? []
  const stageTotals = [
    { label: 'Uploaded', n: all.length },
    {
      label: 'Text & OCR',
      n: all.filter((d) => d.ingest_status === 'processed' || d.ingest_status === 'needs_review')
        .length,
    },
    { label: 'Extracted', n: all.filter((d) => d.extract_status === 'done').length },
    { label: 'Indexed', n: all.filter((d) => d.index_status === 'done').length },
  ]

  const columns: Column<DocumentSummary>[] = [
    {
      key: 'id',
      header: 'ID',
      render: (d) => <span className="num">{d.id}</span>,
      sortValue: (d) => d.id,
      align: 'right',
    },
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
      render: (d) => <span className="num">{d.report_date ?? '—'}</span>,
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
    {
      key: 'pipeline',
      header: 'Pipeline',
      render: (d) => <PipelineTimeline doc={d} compact />,
    },
    {
      key: 'events',
      header: 'Events',
      render: (d) => <span className="num">{d.event_count}</span>,
      sortValue: (d) => d.event_count,
      align: 'right',
    },
  ]

  const uploadError = upload.error instanceof ApiError ? upload.error : null

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight text-text">Documents Library</h1>
        {all.some((d) => d.synthetic) && <SyntheticBadge />}
      </div>
      <Tabs
        label="Documents Library sections"
        idPrefix="docs"
        value={section}
        onChange={(v) => {
          const next = new URLSearchParams(params)
          if (v === 'review') next.set('view', 'review')
          else next.delete('view')
          setParams(next, { replace: true })
        }}
        tabs={[
          {
            id: 'library',
            label: 'Library',
            icon: <FileText size={14} aria-hidden />,
            count: all.length,
          },
          {
            id: 'review',
            label: 'Review queue',
            icon: <ClipboardCheck size={14} aria-hidden />,
            count: reviewCounts.data?.pending ?? undefined,
          },
        ]}
      />
      {section === 'review' ? (
        <TabPanel idPrefix="docs" id="review">
          <ReviewQueue />
        </TabPanel>
      ) : (
        <TabPanel idPrefix="docs" id="library" className="space-y-5">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <Card
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                'flex flex-col items-center justify-center gap-2 border-2 border-dashed text-center transition-colors',
                dragging && 'border-accent bg-accent/10',
              )}
              data-testid="drop-zone"
            >
              <div className="relative grid size-12 place-items-center">
                {upload.isPending && (
                  <motion.span
                    aria-hidden
                    className="absolute inset-0 rounded-full border-2 border-accent border-t-transparent"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 0.9, repeat: Infinity, ease: 'linear' }}
                  />
                )}
                <Upload aria-hidden className="text-muted" />
              </div>
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
              {uploadError && (
                <p role="alert" className="text-sm text-danger">
                  {uploadError.message} (request {uploadError.requestId ?? 'n/a'})
                </p>
              )}
              {results && (
                <ul className="w-full space-y-1 text-left text-sm" data-testid="upload-results">
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
              <p className="mb-3 text-sm font-semibold text-text">Pipeline</p>
              <ol className="grid grid-cols-4 gap-2" data-testid="stage-totals">
                {stageTotals.map((s, i) => (
                  <li key={s.label} className="relative rounded-lg bg-surface-2 p-3">
                    <p className="num text-2xl font-semibold text-text">{docs.data ? s.n : '—'}</p>
                    <p className="text-xs text-muted">{s.label}</p>
                    {i < stageTotals.length - 1 && (
                      <span aria-hidden className="absolute top-1/2 -right-2 z-1 text-muted">
                        ›
                      </span>
                    )}
                  </li>
                ))}
              </ol>
              <div
                className="mt-3 flex flex-wrap items-center gap-1.5 text-xs"
                data-testid="status-counts"
              >
                {Object.entries(docs.data?.status_counts ?? {}).map(([k, v]) => (
                  <Badge key={k} tone={STATUS_TONE[k] ?? 'neutral'}>
                    {k.replace('_', ' ')}: {v}
                  </Badge>
                ))}
              </div>
            </Card>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="relative min-w-56 flex-1">
              <span className="sr-only">Search documents</span>
              <Search
                size={15}
                aria-hidden
                className="absolute top-1/2 left-2.5 -translate-y-1/2 text-muted"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter by file or well name"
                className="h-9 w-full rounded-lg border border-border bg-surface pr-3 pl-8 text-sm text-text placeholder:text-muted"
              />
            </label>
            <Segmented
              label="Document type"
              options={TYPES.map((t) => ({
                id: t,
                label: t === 'all' ? 'All types' : t === 'other' ? 'Other' : t,
              }))}
              value={typeFilter}
              onChange={setTypeFilter}
              testId="type-filter"
            />
            <label className="sr-only" htmlFor="status-filter">
              Filter by status
            </label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 rounded-lg border border-border bg-surface px-2 text-sm text-text"
            >
              <option value="">All statuses</option>
              {Object.keys(STATUS_TONE).map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </select>
            <Segmented
              label="Layout"
              options={[
                { id: 'grid', label: 'Grid', icon: <LayoutGrid size={13} /> },
                { id: 'list', label: 'List', icon: <List size={13} /> },
              ]}
              value={view}
              onChange={setView}
              testId="view-toggle"
            />
          </div>

          {docs.isError && <p className="text-sm text-danger">Documents could not be loaded.</p>}
          {docs.isPending && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[0, 1, 2, 3].map((k) => (
                <SkeletonBlock key={k} className="aspect-[3/4] w-full rounded-xl" />
              ))}
            </div>
          )}
          {docs.data && (
            <p className="text-xs text-muted">
              {items.length} of {docs.data.total} documents · click one to see its page with the
              extracted lines · total size {formatBytes(all.reduce((a, d) => a + d.size_bytes, 0))}
            </p>
          )}

          <AnimatePresence mode="wait" initial={false}>
            {docs.data && view === 'grid' && (
              <motion.ul
                key="grid"
                className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
                variants={staggerContainer}
                initial="hidden"
                animate="show"
                exit={{ opacity: 0 }}
                data-testid="documents-grid"
              >
                {items.length === 0 && (
                  <li className="col-span-full rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted">
                    No documents match — upload a report or change the filters.
                  </li>
                )}
                {items.slice(0, 120).map((d) => (
                  <motion.li key={d.id} variants={staggerItem}>
                    <button
                      type="button"
                      onClick={() => open(d)}
                      disabled={!d.page_count}
                      className="group flex w-full flex-col overflow-hidden rounded-xl border border-border bg-surface text-left shadow-card transition-transform hover:-translate-y-0.5 disabled:cursor-default"
                      data-testid="document-card"
                      aria-label={`Open ${d.filename}`}
                    >
                      <div className="relative aspect-[4/3] w-full overflow-hidden bg-surface-2">
                        {d.page_count ? (
                          <img
                            src={api.pageImageUrl(d.id, 1)}
                            alt=""
                            loading="lazy"
                            decoding="async"
                            className="h-full w-full object-cover object-top opacity-90 transition-opacity group-hover:opacity-100"
                          />
                        ) : (
                          <div className="grid h-full place-items-center text-muted">
                            <FileText aria-hidden />
                          </div>
                        )}
                        <span className="absolute top-2 left-2 flex gap-1">
                          <Badge tone="info">{d.doc_type ?? 'unclassified'}</Badge>
                          {d.synthetic && <Badge tone="warn">SYNTHETIC</Badge>}
                        </span>
                      </div>
                      <div className="space-y-2 p-3">
                        <p className="truncate text-sm font-medium text-text" title={d.filename}>
                          {d.filename}
                        </p>
                        <p className="truncate text-xs text-muted">
                          {d.well_name ?? d.raw_well_name ?? 'well unknown'} ·{' '}
                          {d.report_date ?? 'no date'} · {d.page_count ?? '—'} p.
                        </p>
                        <PipelineTimeline doc={d} />
                      </div>
                    </button>
                  </motion.li>
                ))}
              </motion.ul>
            )}
            {docs.data && view === 'list' && (
              <motion.div
                key="list"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                <DataTable
                  testId="documents-table"
                  caption="Documents"
                  columns={columns}
                  rows={items}
                  rowKey={(d) => d.id}
                  initialSort={{ key: 'id', dir: 'desc' }}
                  onRowClick={open}
                  selectedKey={viewing?.id ?? null}
                  empty="No documents match — upload a report or change the filters."
                />
              </motion.div>
            )}
          </AnimatePresence>
          {docs.data && view === 'grid' && items.length > 120 && (
            <p className="text-center text-xs text-muted">
              Showing the first 120 in the grid; switch to the list for all {items.length}.
            </p>
          )}

          {viewing && (
            <Suspense fallback={null}>
              <PageViewer
                documentId={viewing.id}
                title={viewing.filename}
                pageCount={viewing.page_count}
                onClose={close}
              />
            </Suspense>
          )}
        </TabPanel>
      )}
    </div>
  )
}
