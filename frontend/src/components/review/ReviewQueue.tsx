import { Check, ChevronDown, ChevronUp, Pencil, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'

import { ApiError, type ReviewItem } from '../../lib/api/client'
import { useDecideReview, useDocumentPage, useReviewQueue } from '../../lib/api/hooks'
import { cn } from '../../lib/cn'
import {
  buildCorrection,
  canCorrect,
  FIELD_SPECS,
  initialDraft,
  labelFor,
  type Draft,
} from '../../lib/review'
import { PageImage } from '../evidence/PageImage'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Segmented } from '../ui/Segmented'
import { SkeletonBlock } from '../ui/Skeleton'

type Status = 'pending' | 'corrected' | 'accepted' | 'rejected'
const STATUSES: Status[] = ['pending', 'corrected', 'accepted', 'rejected']

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  return (
    <span className="inline-flex items-center gap-1.5" title={`Extraction confidence ${pct}%`}>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <span
          className={cn(
            'block h-full rounded-full',
            pct < 50 ? 'bg-danger' : pct < 75 ? 'bg-warn' : 'bg-ok',
          )}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="num text-xs text-muted">{pct}%</span>
    </span>
  )
}

function display(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

/** Page image with the cited lines highlighted, scrolled so the first one is in view. */
function EvidencePage({ item }: { item: ReviewItem }) {
  const page = useDocumentPage(item.document_id ?? 0, item.page_no ?? 1)
  const wrap = useRef<HTMLDivElement>(null)
  const selected = useMemo(() => new Set(item.span_ids), [item.span_ids])
  useEffect(() => {
    const hit = wrap.current?.querySelector('[data-highlighted="true"]')
    if (hit && 'scrollIntoView' in hit) hit.scrollIntoView({ block: 'center' })
  }, [page.data])
  if (!item.document_id) return <p className="text-sm text-muted">No source page recorded.</p>
  return (
    <div
      ref={wrap}
      className="max-h-[70vh] overflow-auto rounded-lg border border-border bg-surface-2 p-2"
      role="region"
      aria-label={`Source page ${item.page_no ?? ''} of ${item.filename ?? 'the document'}`}
      // Scrollable without focusable content inside: focusable so the keyboard can scroll it.
      tabIndex={0}
    >
      {page.isPending && <SkeletonBlock className="aspect-[3/4] w-full" />}
      {page.isError && <p className="text-sm text-danger">The page could not be loaded.</p>}
      {page.data && (
        <PageImage page={page.data} documentId={item.document_id} selected={selected} />
      )}
    </div>
  )
}

function Decision({ item, onDone }: { item: ReviewItem; onDone: (message: string) => void }) {
  const decide = useDecideReview()
  const [editing, setEditing] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [draft, setDraft] = useState<Draft>(() => initialDraft(item.kind, item.proposed))
  const [reason, setReason] = useState('Not a real fact in the report')
  const firstInput = useRef<HTMLInputElement | HTMLSelectElement | null>(null)
  const reasonInput = useRef<HTMLInputElement>(null)
  const specs = FIELD_SPECS[item.kind] ?? {}
  const correctable = canCorrect(item.kind)
  const { fields, errors } = buildCorrection(item.kind, item.proposed, draft)
  const changed = Object.keys(fields).length
  const pending = item.status === 'pending'

  const run = (decision: Parameters<typeof decide.mutate>[0]['decision'], message: string) =>
    decide.mutate({ id: item.id, decision }, { onSuccess: () => onDone(message) })

  const accept = () => run({ action: 'accept' }, `Accepted · ${item.well_name ?? ''} ${item.kind}`)
  const save = (e?: FormEvent) => {
    e?.preventDefault()
    if (changed && !Object.keys(errors).length)
      run({ action: 'correct', fields }, `Corrected ${changed} field${changed > 1 ? 's' : ''}`)
  }
  const reject = (e?: FormEvent) => {
    e?.preventDefault()
    if (reason.trim()) run({ action: 'reject', reason: reason.trim() }, 'Rejected')
  }

  // Keyboard: A accept · E edit · R reject (ignored while typing in a field).
  useEffect(() => {
    if (!pending) return
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && ['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName)) return
      if (e.metaKey || e.ctrlKey || e.altKey || document.querySelector('[role="dialog"]')) return
      const k = e.key.toLowerCase()
      if (k === 'a') {
        e.preventDefault()
        accept()
      } else if (k === 'e' && correctable) {
        e.preventDefault()
        setEditing(true)
        setRejecting(false)
        setTimeout(() => firstInput.current?.focus(), 0)
      } else if (k === 'r') {
        e.preventDefault()
        setRejecting(true)
        setEditing(false)
        setTimeout(() => reasonInput.current?.select(), 0)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const error = decide.error instanceof ApiError ? decide.error : null
  const keys = Object.keys(item.proposed)
  return (
    <div className="space-y-3">
      <form onSubmit={save} className="space-y-2" aria-label="Extracted values">
        <table className="w-full text-sm" data-testid="review-fields">
          <thead className="text-xs text-muted">
            <tr>
              <th className="py-1 text-left font-medium">Field</th>
              <th className="py-1 text-left font-medium">Extracted</th>
              {editing && <th className="py-1 text-left font-medium">Correction</th>}
            </tr>
          </thead>
          <tbody>
            {keys.map((key, i) => {
              const spec = specs[key]
              const current =
                item.correction && key in item.correction ? item.correction[key] : undefined
              return (
                <tr key={key} className="border-t border-border align-top">
                  <td className="py-1.5 pr-2 text-muted">
                    {labelFor(item.kind, key)}
                    {spec?.unit && <span className="text-xs"> ({spec.unit})</span>}
                  </td>
                  <td className="py-1.5 pr-2">
                    <span
                      className={cn(
                        'rounded border border-dashed border-muted px-1 text-text',
                        (item.proposed[key] === null || item.proposed[key] === undefined) &&
                          'text-warn',
                      )}
                    >
                      {display(item.proposed[key])}
                    </span>
                    {current !== undefined && (
                      <span className="ml-2 text-xs text-ok">→ {display(current)}</span>
                    )}
                  </td>
                  {editing && (
                    <td className="py-1">
                      {spec ? (
                        <label>
                          <span className="sr-only">Correct {labelFor(item.kind, key)}</span>
                          {spec.kind === 'select' ? (
                            <select
                              ref={i === 0 ? (el) => void (firstInput.current = el) : undefined}
                              value={draft[key] ?? ''}
                              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                              className="h-8 w-full rounded border border-border bg-surface px-1 text-sm text-text"
                            >
                              <option value="">unknown</option>
                              {spec.options?.map((o) => (
                                <option key={o} value={o}>
                                  {o}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <input
                              ref={i === 0 ? (el) => void (firstInput.current = el) : undefined}
                              type={spec.kind === 'date' ? 'date' : 'text'}
                              inputMode={spec.kind === 'number' ? 'decimal' : undefined}
                              value={draft[key] ?? ''}
                              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                              aria-invalid={Boolean(errors[key])}
                              className={cn(
                                'h-8 w-full rounded border bg-surface px-2 text-sm text-text',
                                errors[key] ? 'border-danger' : 'border-border',
                              )}
                            />
                          )}
                          {errors[key] && (
                            <span className="text-xs text-danger">{errors[key]}</span>
                          )}
                        </label>
                      ) : (
                        <span className="text-xs text-muted">not editable</span>
                      )}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
        {editing && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              type="submit"
              disabled={!changed || Object.keys(errors).length > 0 || decide.isPending}
            >
              Save correction{changed ? ` (${changed})` : ''}
            </Button>
            <Button onClick={() => setEditing(false)}>Cancel</Button>
            <span className="text-xs text-muted">Values in canonical units: m, SG, in, h.</span>
          </div>
        )}
      </form>

      {rejecting && (
        <form onSubmit={reject} className="flex flex-wrap items-center gap-2">
          <label className="flex-1 text-sm">
            <span className="sr-only">Reason for rejecting</span>
            <input
              ref={reasonInput}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="h-9 w-full rounded border border-border bg-surface px-2 text-sm text-text"
              maxLength={2000}
            />
          </label>
          <Button
            type="submit"
            className="bg-danger-bg text-danger"
            disabled={!reason.trim() || decide.isPending}
          >
            Reject
          </Button>
          <Button onClick={() => setRejecting(false)}>Cancel</Button>
        </form>
      )}

      {pending ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
          <Button
            variant="primary"
            onClick={accept}
            disabled={decide.isPending}
            data-testid="review-accept"
          >
            <Check size={15} aria-hidden /> Accept <kbd className="text-xs opacity-70">A</kbd>
          </Button>
          <Button
            onClick={() => {
              setEditing(true)
              setRejecting(false)
            }}
            disabled={!correctable || decide.isPending}
            title={correctable ? undefined : `${item.kind} items can only be accepted or rejected`}
            data-testid="review-edit"
          >
            <Pencil size={14} aria-hidden /> Edit <kbd className="text-xs opacity-70">E</kbd>
          </Button>
          <Button
            onClick={() => {
              setRejecting(true)
              setEditing(false)
            }}
            disabled={decide.isPending}
            data-testid="review-reject"
          >
            <X size={15} aria-hidden /> Reject <kbd className="text-xs opacity-70">R</kbd>
          </Button>
          <span className="text-xs text-muted">J / K next / previous</span>
        </div>
      ) : (
        <p className="text-sm text-muted">
          {item.status} by {item.decided_by ?? '—'}
          {item.decided_at ? ` on ${item.decided_at.slice(0, 10)}` : ''}
        </p>
      )}
      {error && (
        <p className="text-sm text-danger" role="alert">
          {error.status === 409
            ? 'Someone already decided this item; the list has been refreshed.'
            : error.message}
        </p>
      )}
    </div>
  )
}

/** Review queue: low-confidence extractions checked against the page they came from (P7). */
export function ReviewQueue() {
  const [status, setStatus] = useState<Status>('pending')
  const queue = useReviewQueue({ status })
  const items = useMemo(() => queue.data?.items ?? [], [queue.data])
  const counts = queue.data?.status_counts ?? {}
  // ?item=<id> opens one item directly (links from elsewhere, e2e tests).
  const [params] = useSearchParams()
  const [selectedId, setSelectedId] = useState<number | null>(Number(params.get('item')) || null)
  const [lastIndex, setLastIndex] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)

  const index = Math.max(
    0,
    items.findIndex((i) => i.id === selectedId),
  )
  const current =
    items.find((i) => i.id === selectedId) ?? items[Math.min(lastIndex, items.length - 1)] ?? null
  const move = (step: number) => {
    if (!items.length) return
    const at = current ? items.indexOf(current) : index
    const next = items[Math.min(items.length - 1, Math.max(0, at + step))]!
    setSelectedId(next.id)
    setLastIndex(items.indexOf(next))
  }

  // J / K move through the list.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && ['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName)) return
      if (e.metaKey || e.ctrlKey || e.altKey || document.querySelector('[role="dialog"]')) return
      if (e.key === 'j' || e.key === 'J') move(1)
      if (e.key === 'k' || e.key === 'K') move(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="space-y-3" data-testid="review-queue">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label="Review status"
          options={STATUSES.map((s) => ({ id: s, label: `${s} ${counts[s] ?? 0}` }))}
          value={status}
          onChange={(s) => {
            setStatus(s)
            setSelectedId(null)
            setLastIndex(0)
          }}
          testId="review-status"
        />
        <span className="text-xs text-muted">
          Lowest confidence first. Accepting marks the value verified; a correction also goes into
          the evaluation gold set.
        </span>
      </div>
      {notice && (
        <p className="text-sm text-ok" role="status" data-testid="review-notice">
          {notice}
        </p>
      )}
      {queue.isPending && <SkeletonBlock className="h-64 w-full" />}
      {queue.isError && (
        <p className="text-sm text-danger">The review queue could not be loaded.</p>
      )}
      {queue.data && items.length === 0 && (
        <Card className="text-center text-sm text-muted" data-testid="review-empty">
          {status === 'pending'
            ? 'Nothing waits for review. New low-confidence extractions appear here.'
            : `No ${status} items.`}
        </Card>
      )}
      {current && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[16rem_minmax(0,1fr)_minmax(0,24rem)]">
          <ol
            className="max-h-[70vh] space-y-1 overflow-auto"
            aria-label="Review items"
            data-testid="review-list"
          >
            {items.map((it) => (
              <li key={it.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(it.id)
                    setLastIndex(items.indexOf(it))
                  }}
                  aria-current={it.id === current.id}
                  className={cn(
                    'w-full rounded-lg border px-2.5 py-2 text-left text-xs',
                    it.id === current.id
                      ? 'border-accent bg-accent/10'
                      : 'border-border hover:bg-surface-2',
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    <Badge tone="info">{it.kind}</Badge>
                    <span className="truncate font-medium text-text">
                      {it.well_name ?? 'well unknown'}
                    </span>
                  </span>
                  <span className="mt-1 block truncate text-muted">{it.reason}</span>
                  <ConfidenceBar value={it.confidence} />
                </button>
              </li>
            ))}
          </ol>
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <span className="truncate" data-testid="review-source">
                {current.filename ?? 'no document'}
                {current.page_no ? ` · page ${current.page_no}` : ''}
              </span>
              <span className="flex items-center gap-1">
                <Button
                  aria-label="Previous item"
                  onClick={() => move(-1)}
                  disabled={items.indexOf(current) <= 0}
                >
                  <ChevronUp size={15} />
                </Button>
                <span className="num">
                  {items.indexOf(current) + 1} / {items.length}
                </span>
                <Button
                  aria-label="Next item"
                  onClick={() => move(1)}
                  disabled={items.indexOf(current) >= items.length - 1}
                >
                  <ChevronDown size={15} />
                </Button>
              </span>
            </div>
            <EvidencePage item={current} />
          </div>
          <Card className="space-y-3 self-start" data-testid="review-panel">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="info">{current.kind}</Badge>
                <span className="font-semibold text-text">
                  {current.well_name ?? 'well unknown'}
                </span>
                <ConfidenceBar value={current.confidence} />
              </div>
              <p className="text-sm text-warn">Why it needs review: {current.reason}</p>
            </div>
            <Decision
              key={current.id}
              item={current}
              onDone={(message) => {
                setNotice(message)
                setSelectedId(null) // the decided item leaves the list; stay at its position
              }}
            />
          </Card>
        </div>
      )}
    </div>
  )
}
