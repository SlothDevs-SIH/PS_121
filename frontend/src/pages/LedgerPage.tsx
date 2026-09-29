import { ChevronDown, ChevronRight, Info, Scale } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { ConfidenceValue } from '../components/ConfidenceValue'
import { EvidenceLink } from '../components/evidence/EvidenceLink'
import { IntervalBar } from '../components/risk/IntervalBar'
import { SyntheticBadge } from '../components/SyntheticBadge'
import { Badge } from '../components/ui/Badge'
import { Card, CardTitle } from '../components/ui/Card'
import { SkeletonBlock } from '../components/ui/Skeleton'
import type { LedgerCase, LedgerEntry } from '../lib/api/client'
import { useFormations, useLedger } from '../lib/api/hooks'
import { eventMeta } from '../lib/eventTypes'
import { formatNumber } from '../lib/format/units'
import { pct } from '../lib/risk'

/** Event types that have mitigations in the ledger's vocabulary. */
const LEDGER_TYPES = [
  'LOSS',
  'KICK',
  'STUCK',
  'TIGHT',
  'TORQUE',
  'INSTAB',
  'BALLING',
  'OVERP',
  'GAS',
  'CEMENT',
] as const
const SEVERITIES = ['low', 'medium', 'high'] as const
const OUTCOME_TONE = { success: 'ok', partial: 'warn', fail: 'danger', unknown: 'neutral' } as const

function CaseList({ cases }: { cases: LedgerCase[] }) {
  if (cases.length === 0) return <p className="text-sm text-muted">No recorded uses.</p>
  return (
    <ul className="space-y-1.5" data-testid="ledger-cases">
      {cases.map((c) => (
        <li
          key={c.mitigation_id}
          className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border px-3 py-1.5 text-sm"
        >
          <Link
            to={`/wells/${c.well_id}?tab=events`}
            className="font-medium text-accent hover:underline"
          >
            {c.well_name}
          </Link>
          <span className="text-muted">
            {c.event_date ?? 'date —'} · {c.formation ?? 'formation —'} ·{' '}
            {c.severity ?? 'severity —'}
          </span>
          <span className="text-muted">tried {c.seq === 1 ? 'first' : `as #${c.seq}`}</span>
          <ConfidenceValue verified={c.verified} confidence={c.verified ? 1 : 0.7}>
            <Badge tone={OUTCOME_TONE[c.outcome]}>{c.outcome}</Badge>
          </ConfidenceValue>
          {c.recurred && (
            <Badge tone="warn" title="The same problem came back soon after: counted as partial">
              recurred (recorded {c.recorded_outcome})
            </Badge>
          )}
          {c.npt_hours_after !== null && (
            <span className="num text-muted">{formatNumber(c.npt_hours_after, 1)} h NPT after</span>
          )}
          <span className="ml-auto flex flex-wrap gap-2">
            {c.evidence.length === 0 ? (
              <span className="text-xs text-muted">no citation</span>
            ) : (
              c.evidence.slice(0, 2).map((e) => (
                <EvidenceLink
                  key={`${e.document_id}-${e.page_no}`}
                  documentId={e.document_id}
                  pageNo={e.page_no}
                  spanIds={e.span_ids}
                  title={e.filename ?? undefined}
                >
                  {e.doc_type ?? 'doc'} p.{e.page_no}
                </EvidenceLink>
              ))
            )}
          </span>
        </li>
      ))}
    </ul>
  )
}

function EntryRows({
  entry,
  rank,
  open,
  onToggle,
}: {
  entry: LedgerEntry
  rank: number | null
  open: boolean
  onToggle: () => void
}) {
  const knownTotal = entry.successes + entry.partial + entry.failures
  return (
    <Fragment>
      <tr className="border-t border-border align-middle" data-testid="ledger-row">
        <td className="py-2 pr-2 text-muted num">{rank ?? '–'}</td>
        <th scope="row" className="py-2 pr-3 text-left font-medium text-text">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            className="inline-flex items-center gap-1 text-left hover:text-accent"
            data-testid="ledger-action"
            data-code={entry.action_code}
          >
            {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
            {entry.action_label}
          </button>
        </th>
        <td className="num py-2 pr-3 whitespace-nowrap">
          {entry.successes} of {knownTotal}
          {entry.partial > 0 && <span className="text-muted"> ({entry.partial} partial)</span>}
        </td>
        <td className="py-2 pr-3">
          <div className="flex items-center gap-2">
            <IntervalBar
              value={entry.posterior_mean}
              low={entry.ci90_low}
              high={entry.ci90_high}
              raw={entry.success_rate}
              label={`${entry.action_label} worked`}
            />
            <span className="num text-xs whitespace-nowrap">
              {pct(entry.posterior_mean)}{' '}
              <span className="text-muted">
                ({pct(entry.ci90_low)}–{pct(entry.ci90_high)})
              </span>
            </span>
          </div>
        </td>
        <td className="num py-2 pr-3">
          {entry.median_npt_hours === null ? '—' : `${formatNumber(entry.median_npt_hours, 1)} h`}
        </td>
        <td className="num py-2 pr-3">{entry.n}</td>
        <td className="num py-2 pr-3 text-muted">{entry.unknown > 0 ? entry.unknown : '—'}</td>
      </tr>
      {open && (
        <tr>
          <td />
          <td colSpan={6} className="pb-3">
            <p className="mb-1.5 text-xs text-muted">{entry.summary}</p>
            {entry.by_severity.length > 1 && (
              <p className="mb-1.5 text-xs text-muted" data-testid="ledger-strata">
                By severity:{' '}
                {entry.by_severity.map((s) => `${s.severity} ${s.successes}/${s.n}`).join(' · ')}
              </p>
            )}
            <CaseList cases={entry.cases} />
          </td>
        </tr>
      )}
    </Fragment>
  )
}

function EntryTable({
  entries,
  ranked,
  testId,
}: {
  entries: LedgerEntry[]
  ranked: boolean
  testId: string
}) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const toggle = (code: string) =>
    setOpen((s) => {
      const n = new Set(s)
      if (n.has(code)) n.delete(code)
      else n.add(code)
      return n
    })
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid={testId}>
        <caption className="sr-only">
          {ranked ? 'Mitigations ranked by recorded outcome' : 'Mitigations with too few records'}
        </caption>
        <thead className="text-left text-xs text-muted">
          <tr>
            <th scope="col" className="w-8 py-1 pr-2">
              #
            </th>
            <th scope="col" className="py-1 pr-3">
              Action
            </th>
            <th scope="col" className="py-1 pr-3">
              Worked
            </th>
            <th scope="col" className="py-1 pr-3">
              Success (90% credible interval)
            </th>
            <th scope="col" className="py-1 pr-3">
              Median NPT
            </th>
            <th scope="col" className="py-1 pr-3" title="Uses with a known outcome">
              n
            </th>
            <th scope="col" className="py-1 pr-3" title="Uses whose outcome was not recorded">
              Unknown
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <EntryRows
              key={e.action_code}
              entry={e}
              rank={ranked ? i + 1 : null}
              open={open.has(e.action_code)}
              onToggle={() => toggle(e.action_code)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function LedgerPage() {
  const [params, setParams] = useSearchParams()
  const eventType = params.get('type') ?? 'LOSS'
  const formation = params.get('fm')
  const severity = params.get('sev')
  const formations = useFormations()
  const ledger = useLedger({ event_type: eventType, formation, severity })
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }
  const select = 'h-9 rounded-lg border border-border bg-surface px-2 text-sm text-text'
  const d = ledger.data

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-text">
            <Scale size={22} aria-hidden className="text-accent" /> Mitigation Ledger
          </h1>
          <p className="text-sm text-muted">
            What was tried for each problem, and how often it worked, from the drilling reports.
          </p>
        </div>
        {d?.synthetic && <SyntheticBadge />}
      </div>

      <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Ledger filters">
        <label className="flex items-center gap-2 text-xs text-muted">
          Problem
          <select
            className={select}
            value={eventType}
            onChange={(e) => set({ type: e.target.value })}
            data-testid="ledger-type"
          >
            {LEDGER_TYPES.map((t) => (
              <option key={t} value={t}>
                {eventMeta(t).label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          Formation
          <select
            className={select}
            value={formation ?? ''}
            onChange={(e) => set({ fm: e.target.value || null })}
            data-testid="ledger-formation"
          >
            <option value="">any</option>
            {(formations.data ?? []).map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          Severity
          <select
            className={select}
            value={severity ?? ''}
            onChange={(e) => set({ sev: e.target.value || null })}
          >
            <option value="">any</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div
        className="flex items-start gap-2 rounded-xl border border-warn/40 bg-warn-bg px-3 py-2 text-sm text-text"
        role="note"
        data-testid="ledger-caveat"
      >
        <Info size={16} aria-hidden className="mt-0.5 shrink-0 text-warn" />
        <p>
          <strong>Associated with better outcomes; observational data, not causal.</strong>{' '}
          {d?.caveat ?? ''} “Outcome unknown” is never counted as a success or a failure.
        </p>
      </div>

      {ledger.isError && (
        <p className="text-danger" role="alert">
          The ledger could not be loaded.
        </p>
      )}
      {!d && !ledger.isError && <SkeletonBlock className="h-72 w-full" />}
      {d && (
        <>
          <p className="text-sm text-muted" data-testid="ledger-scope">
            {eventMeta(d.event_type).label}
            {d.formation ? ` in ${d.formation}` : ''}: {d.scope.events} events in {d.scope.wells}{' '}
            wells, {d.scope.mitigations} recorded actions
            {d.scope.unknown_outcomes > 0
              ? `, ${d.scope.unknown_outcomes} with unknown outcome`
              : ''}
            .
          </p>
          <Card>
            <CardTitle>Ranked (n ≥ {d.min_n})</CardTitle>
            {d.ranked.length === 0 ? (
              <p className="text-sm text-muted" data-testid="ledger-empty">
                No action has {d.min_n} or more known outcomes in this scope — widen it (any
                formation, any severity).
              </p>
            ) : (
              <EntryTable entries={d.ranked} ranked testId="ledger-ranked" />
            )}
          </Card>
          {d.insufficient.length > 0 && (
            <Card>
              <CardTitle>Insufficient evidence (n &lt; {d.min_n}, not ranked)</CardTitle>
              <EntryTable entries={d.insufficient} ranked={false} testId="ledger-insufficient" />
            </Card>
          )}
          <details className="text-xs text-muted">
            <summary className="cursor-pointer">How outcomes are counted</summary>
            <p className="mt-1">{d.outcome_rule}</p>
          </details>
        </>
      )}
    </div>
  )
}
