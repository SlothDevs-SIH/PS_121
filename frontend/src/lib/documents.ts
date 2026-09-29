import type { DocumentSummary } from './api/client'
import { formatBytes } from './format/units'

export type StepState = 'done' | 'active' | 'waiting' | 'warn' | 'failed' | 'skipped'

/** Uploaded → Text/OCR → Extraction → Indexed, from the document's three stage columns. */
export function pipelineSteps(
  d: DocumentSummary,
): { label: string; state: StepState; note: string }[] {
  const ingest: StepState =
    d.ingest_status === 'processed'
      ? 'done'
      : d.ingest_status === 'needs_review'
        ? 'warn'
        : d.ingest_status === 'failed'
          ? 'failed'
          : d.ingest_status === 'processing'
            ? 'active'
            : 'waiting'
  const stage = (s: string): StepState =>
    s === 'done'
      ? 'done'
      : s === 'running'
        ? 'active'
        : s === 'failed'
          ? 'failed'
          : s === 'skipped'
            ? 'skipped'
            : 'waiting'
  return [
    { label: 'Uploaded', state: 'done', note: formatBytes(d.size_bytes) },
    {
      label: 'Text & OCR',
      state: ingest,
      note:
        d.ingest_status === 'needs_review'
          ? (d.error ?? 'needs review')
          : d.ingest_status.replace('_', ' '),
    },
    {
      label: 'Extraction',
      state: stage(d.extract_status),
      note:
        d.extract_status === 'done'
          ? `${d.event_count} event${d.event_count === 1 ? '' : 's'}`
          : (d.extract_error ?? d.extract_status),
    },
    { label: 'Indexed', state: stage(d.index_status), note: d.index_status },
  ]
}
