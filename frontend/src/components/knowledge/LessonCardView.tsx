import { Link } from 'react-router'

import type { LessonCard } from '../../lib/api/client'
import { eventMeta, markerPath } from '../../lib/eventTypes'
import { cn } from '../../lib/cn'
import { EvidenceLink } from '../evidence/EvidenceLink'
import { Badge } from '../ui/Badge'

const STEPS: { key: keyof LessonCard; label: string }[] = [
  { key: 'problem', label: 'Problem' },
  { key: 'likely_cause', label: 'Likely cause' },
  { key: 'action_taken', label: 'What was done' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'lesson', label: 'Lesson' },
]

/**
 * A lessons-learned card (problem → cause → action → outcome → lesson), always with its
 * citations. Cards come from extracted events: unverified ones are outlined dashed (P7).
 */
export function LessonCardView({
  card,
  showWell = true,
}: {
  card: LessonCard
  showWell?: boolean
}) {
  const meta = eventMeta(card.event_type)
  return (
    <article
      className={cn(
        'space-y-2 rounded-xl border bg-surface p-4 text-sm shadow-card',
        card.verified ? 'border-border' : 'border-dashed border-muted',
      )}
      data-testid="lesson-card"
      aria-label={`Lesson: ${meta.label}${card.formation ? ` in ${card.formation}` : ''}`}
    >
      <header className="flex flex-wrap items-center gap-1.5">
        <svg width={14} height={14} viewBox="-7 -7 14 14" aria-hidden>
          <path d={markerPath(meta.shape, 5)} fill={meta.colorVar} />
        </svg>
        <span className="font-semibold text-text">{meta.label}</span>
        {showWell && (
          <Link to={`/wells/${card.well_id}`} className="text-accent hover:underline">
            {card.well_name}
          </Link>
        )}
        {card.formation && <Badge tone="neutral">{card.formation}</Badge>}
        {card.synthetic && <Badge tone="warn">SYNTHETIC</Badge>}
        {!card.verified && (
          <Badge
            tone="neutral"
            title="Generated from an extracted event that no engineer has verified yet"
          >
            unverified
          </Badge>
        )}
      </header>
      <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1">
        {STEPS.map(({ key, label }) =>
          card[key] ? (
            <div key={key} className="contents">
              <dt className="text-xs font-medium text-muted">{label}</dt>
              <dd className={cn('text-text', key === 'lesson' && 'font-medium')}>
                {String(card[key])}
              </dd>
            </div>
          ) : null,
        )}
      </dl>
      <footer className="flex flex-wrap items-center gap-3 pt-1 text-xs">
        {card.evidence.map((ev) => (
          <EvidenceLink
            key={`${ev.document_id}-${ev.page_no}`}
            documentId={ev.document_id}
            pageNo={ev.page_no}
            spanIds={ev.span_ids}
            title={ev.filename ?? undefined}
          >
            {ev.filename ?? `doc ${ev.document_id}`} p.{ev.page_no}
          </EvidenceLink>
        ))}
        {card.evidence.length === 0 && <span className="text-warn">No citation recorded</span>}
      </footer>
    </article>
  )
}
