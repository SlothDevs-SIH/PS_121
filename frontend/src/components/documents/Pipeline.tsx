import { Check, CircleAlert, LoaderCircle, X } from 'lucide-react'

import type { DocumentSummary } from '../../lib/api/client'
import { cn } from '../../lib/cn'
import { pipelineSteps, type StepState } from '../../lib/documents'

const STEP_TONE: Record<StepState, string> = {
  done: 'bg-ok text-ok-bg',
  active: 'bg-info text-info-bg',
  waiting: 'bg-surface-2 text-muted',
  warn: 'bg-warn text-warn-bg',
  failed: 'bg-danger text-danger-bg',
  skipped: 'bg-surface-2 text-muted',
}

function StepIcon({ state }: { state: StepState }) {
  if (state === 'done') return <Check size={10} strokeWidth={3} />
  if (state === 'active') return <LoaderCircle size={10} className="animate-spin" />
  if (state === 'failed') return <X size={10} strokeWidth={3} />
  if (state === 'warn') return <CircleAlert size={10} />
  return null
}

const SHORT: Record<string, string> = {
  Uploaded: 'Upload',
  'Text & OCR': 'Text',
  Extraction: 'Extract',
  Indexed: 'Index',
}

export function PipelineTimeline({
  doc,
  compact = false,
}: {
  doc: DocumentSummary
  compact?: boolean
}) {
  const steps = pipelineSteps(doc)
  return (
    <ol
      className={cn('grid grid-cols-4', compact ? 'min-w-24 gap-0' : 'gap-0')}
      aria-label="Processing stages"
      data-testid="pipeline"
    >
      {steps.map((s, i) => (
        <li key={s.label} className="flex min-w-0 flex-col" title={`${s.label}: ${s.note}`}>
          <span className="flex items-center">
            <span
              className={cn(
                'grid size-4 shrink-0 place-items-center rounded-full',
                STEP_TONE[s.state],
              )}
              data-state={s.state}
              aria-label={`${s.label}: ${s.state}`}
            >
              <StepIcon state={s.state} />
            </span>
            {i < steps.length - 1 && (
              <span
                aria-hidden
                className={cn('h-px flex-1', s.state === 'done' ? 'bg-ok' : 'bg-border')}
              />
            )}
          </span>
          {!compact && (
            <span className="mt-1 truncate text-[0.65rem] text-muted">{SHORT[s.label]}</span>
          )}
        </li>
      ))}
    </ol>
  )
}
