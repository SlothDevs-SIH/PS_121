import { FileSearch, Search, SearchX, Sparkles } from 'lucide-react'
import { AnimatePresence } from 'motion/react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'

import { CopilotPanel } from '../components/copilot/CopilotPanel'
import { EvidenceLink } from '../components/evidence/EvidenceLink'
import { LessonCardView } from '../components/knowledge/LessonCardView'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { SkeletonBlock } from '../components/ui/Skeleton'
import type { Passage, SearchParams } from '../lib/api/client'
import { useFormations, useMe, useSearch, useWells } from '../lib/api/hooks'
import { cn } from '../lib/cn'
import { useCopilotChat } from '../lib/copilotChat'
import { EVENT_TYPES } from '../lib/eventTypes'
import { formatNumber } from '../lib/format/units'
import { highlight } from '../lib/highlight'

const TYPE_FILTERS = [
  'LOSS',
  'KICK',
  'STUCK',
  'TIGHT',
  'TORQUE',
  'INSTAB',
  'BALLING',
  'OVERP',
  'CEMENT',
]
const EXAMPLES = [
  'lost circulation Tipam',
  'stuck pipe Barail',
  'kick while drilling',
  'losses during cementing',
  'bit balling Girujan',
]
const RADII = [1, 2, 5, 10, 20]
const LESSONS_SHOWN = 6

function PassageCard({ p }: { p: Passage }) {
  const pages = p.page_from === p.page_to ? `p.${p.page_from}` : `pp.${p.page_from}–${p.page_to}`
  return (
    <article
      className="space-y-2 rounded-xl border border-border bg-surface p-4 text-sm shadow-card"
      data-testid="passage"
    >
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="info">{p.doc_type ?? 'document'}</Badge>
        {p.well_id ? (
          <Link to={`/wells/${p.well_id}`} className="font-medium text-accent hover:underline">
            {p.well_name}
          </Link>
        ) : (
          <span className="text-muted">well unknown</span>
        )}
        <span className="truncate text-muted" title={p.filename}>
          {p.filename}
        </span>
        {p.synthetic && <Badge tone="warn">SYNTHETIC</Badge>}
        <span
          className="ml-auto text-muted"
          title="Rank in the keyword list and in the embedding list, fused by reciprocal rank"
        >
          keyword #{p.lexical_rank ?? '–'} · embedding #{p.dense_rank ?? '–'}
        </span>
      </header>
      <p className="whitespace-pre-line text-text">{highlight(p.snippet, p.highlights)}</p>
      <EvidenceLink
        documentId={p.document_id}
        pageNo={p.page_from}
        spanIds={p.span_ids}
        title={p.filename}
      >
        [{p.doc_type ?? 'doc'}:{pages}] open the page with these lines highlighted
      </EvidenceLink>
    </article>
  )
}

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const wells = useWells()
  const formations = useFormations()
  const q = params.get('q') ?? ''
  const [draft, setDraft] = useState(q)
  const [allLessons, setAllLessons] = useState(false)
  const wellId = Number(params.get('well')) || null
  const types = params.getAll('type')
  // The copilot panel is open while `copilot` is in the URL (its value prefills the question),
  // so "Ask copilot" elsewhere (an alert's detail) can link here with its context.
  const me = useMe()
  const canAsk = me.data?.permissions.includes('copilot') ?? false
  const copilotOpen = canAsk && params.has('copilot')
  const alertId = Number(params.get('alert')) || null
  const chat = useCopilotChat()

  const request = useMemo<SearchParams | null>(() => {
    if (!q.trim()) return null
    const r = Number(params.get('r')) || null
    return {
      q: q.trim(),
      well_id: wellId,
      radius_km: wellId ? r : null,
      formation: params.get('fm'),
      event_type: types.length ? types : undefined,
      doc_type: params.get('doc'),
      date_from: params.get('from'),
      date_to: params.get('to'),
      limit: 20,
    }
  }, [q, params, wellId, types])
  const search = useSearch(request)

  const set = (patch: Record<string, string | string[] | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      next.delete(k)
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x))
      else if (v) next.set(k, v)
    }
    setParams(next, { replace: true })
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    set({ q: draft.trim() || null })
  }
  const toggleType = (t: string) =>
    set({ type: types.includes(t) ? types.filter((x) => x !== t) : [...types, t] })
  const openCopilot = () => {
    const next = new URLSearchParams(params)
    next.set('copilot', q)
    setParams(next, { replace: true })
  }
  const closeCopilot = () => {
    chat.stop()
    set({ copilot: null, alert: null })
  }

  const data = search.data
  const anySynthetic =
    Boolean(data?.passages.some((p) => p.synthetic)) ||
    Boolean(data?.lessons.some((l) => l.synthetic))
  const select = 'h-9 rounded-lg border border-border bg-surface px-2 text-sm text-text'

  return (
    <div
      className={cn(
        'mx-auto',
        copilotOpen ? 'max-w-7xl lg:grid lg:grid-cols-[minmax(0,1fr)_26rem] lg:gap-4' : 'max-w-5xl',
      )}
    >
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-text">Knowledge Search</h1>
          {anySynthetic && <SyntheticBadge />}
          {canAsk && (
            <Button
              className="ml-auto"
              onClick={copilotOpen ? closeCopilot : openCopilot}
              aria-expanded={copilotOpen}
              data-testid="open-copilot"
            >
              <Sparkles size={15} className="text-accent" aria-hidden />
              {copilotOpen ? 'Hide copilot' : 'Ask copilot'}
            </Button>
          )}
        </div>
        <p className="text-sm text-muted">
          Search every ingested report. Lessons from extracted events come first, then the report
          passages, each with the page it came from. If nothing matches, it says so.
        </p>

        <form onSubmit={submit} className="flex gap-2" role="search">
          <label className="relative flex-1">
            <span className="sr-only">Search drilling history</span>
            <Search
              size={16}
              aria-hidden
              className="absolute top-1/2 left-3 -translate-y-1/2 text-muted"
            />
            <input
              type="search"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="e.g. lost circulation in Tipam, stuck pipe while tripping…"
              className="h-11 w-full rounded-xl border border-border bg-surface pr-3 pl-9 text-base text-text placeholder:text-muted"
              data-testid="search-input"
              maxLength={500}
            />
          </label>
          <Button variant="primary" type="submit" className="h-11 px-5">
            Search
          </Button>
        </form>

        <Card className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-muted">
              Well
              <select
                className={select}
                value={wellId ?? ''}
                onChange={(e) =>
                  set({ well: e.target.value || null, r: e.target.value ? params.get('r') : null })
                }
                data-testid="filter-well"
              >
                <option value="">Any well</option>
                {(wells.data?.items ?? []).map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              and offsets within
              <select
                className={select}
                value={params.get('r') ?? ''}
                disabled={!wellId}
                onChange={(e) => set({ r: e.target.value || null })}
              >
                <option value="">this well only</option>
                {RADII.map((r) => (
                  <option key={r} value={r}>
                    {r} km
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              Formation
              <select
                className={select}
                value={params.get('fm') ?? ''}
                onChange={(e) => set({ fm: e.target.value || null })}
              >
                <option value="">Any</option>
                {(formations.data ?? []).map((f) => (
                  <option key={f.id} value={f.name}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              Report
              <select
                className={select}
                value={params.get('doc') ?? ''}
                onChange={(e) => set({ doc: e.target.value || null })}
              >
                <option value="">Any</option>
                <option value="DDR">Daily drilling report</option>
                <option value="WCR">Well completion report</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              From
              <input
                type="date"
                className={select}
                value={params.get('from') ?? ''}
                onChange={(e) => set({ from: e.target.value || null })}
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              to
              <input
                type="date"
                className={select}
                value={params.get('to') ?? ''}
                onChange={(e) => set({ to: e.target.value || null })}
              />
            </label>
          </div>
          <div
            className="flex flex-wrap items-center gap-1.5"
            role="group"
            aria-label="Event types"
          >
            <span className="text-xs text-muted">Problems:</span>
            {TYPE_FILTERS.map((t) => {
              const on = types.includes(t)
              return (
                <button
                  key={t}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleType(t)}
                  className={
                    on
                      ? 'rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-contrast'
                      : 'rounded-full border border-border px-2.5 py-0.5 text-xs text-text hover:bg-surface-2'
                  }
                >
                  {EVENT_TYPES[t]?.label ?? t}
                </button>
              )
            })}
          </div>
        </Card>

        {!q && (
          <Card className="space-y-2 text-sm">
            <p className="text-muted">Try one of these:</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => {
                    setDraft(ex)
                    set({ q: ex })
                  }}
                  className="rounded-full border border-border px-3 py-1 text-text hover:bg-surface-2"
                >
                  {ex}
                </button>
              ))}
            </div>
          </Card>
        )}

        {search.isError && (
          <p className="text-sm text-danger" role="alert">
            Search failed: {(search.error as Error).message}
          </p>
        )}
        {q && search.isPending && (
          <div className="space-y-3" aria-busy="true">
            <SkeletonBlock className="h-28 w-full" />
            <SkeletonBlock className="h-28 w-full" />
          </div>
        )}

        {data && (
          <section className="space-y-4" aria-label="Search results" data-testid="search-results">
            <p className="text-xs text-muted" data-testid="search-summary">
              {data.lessons.length} lessons · {data.passages.length} passages ·{' '}
              {formatNumber(data.took_ms)} ms · embeddings: {data.embedding_provider}
              {data.embedding_provider.startsWith('hash') &&
                ' (a hashing stand-in, not a language model: ranking is mostly keyword matching)'}
            </p>
            {data.no_record_found ? (
              <Card className="flex items-start gap-3" data-testid="no-record">
                <SearchX className="mt-0.5 shrink-0 text-muted" aria-hidden />
                <div className="text-sm">
                  <p className="font-semibold text-text">No record found</p>
                  <p className="text-muted">
                    Nothing in the indexed reports matches “{data.query}”
                    {request?.well_id || request?.formation || types.length
                      ? ' with these filters'
                      : ''}
                    . Nothing is made up to fill the gap: try other words or widen the filters.
                  </p>
                </div>
              </Card>
            ) : (
              <>
                {data.lessons.length > 0 && (
                  <div className="space-y-2">
                    <h2 className="flex items-center gap-2 text-sm font-semibold text-text">
                      <FileSearch size={15} aria-hidden /> Lessons from past events
                    </h2>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      {data.lessons.slice(0, allLessons ? undefined : LESSONS_SHOWN).map((l) => (
                        <LessonCardView key={l.event_id} card={l} />
                      ))}
                    </div>
                    {data.lessons.length > LESSONS_SHOWN && (
                      <Button onClick={() => setAllLessons((v) => !v)} aria-expanded={allLessons}>
                        {allLessons
                          ? 'Show fewer lessons'
                          : `Show all ${data.lessons.length} lessons`}
                      </Button>
                    )}
                  </div>
                )}
                {data.passages.length > 0 && (
                  <div className="space-y-2">
                    <h2 className="text-sm font-semibold text-text">Report passages</h2>
                    {data.passages.map((p) => (
                      <PassageCard key={p.chunk_id} p={p} />
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </div>
      <AnimatePresence>
        {copilotOpen && (
          <CopilotPanel
            key="copilot"
            chat={chat}
            context={{ well_id: wellId, alert_id: alertId }}
            wellName={wells.data?.items.find((w) => w.id === wellId)?.name}
            initialQuestion={params.get('copilot') ?? ''}
            onClearAlert={() => set({ alert: null })}
            onClose={closeCopilot}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
