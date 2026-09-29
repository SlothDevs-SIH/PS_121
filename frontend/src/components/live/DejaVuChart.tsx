import type { DejaVuOverlay } from '../../lib/api/client'
import { DEJAVU_CHANNELS, extent, linePath } from '../../lib/liveView'

const W = 300
const H = 64

/**
 * Déjà Vu overlay: per matcher channel, the live 30 minutes (solid) over the matched 30
 * minutes of the past incident's run-up (dashed), on a shared scale. The similarity is a
 * similarity, not a probability, and the caption says so.
 */
export function DejaVuChart({ overlay }: { overlay: DejaVuOverlay }) {
  const n = overlay.matched[overlay.channels[0] ?? 'torque']?.length ?? 0
  const xs = Array.from({ length: n }, (_, i) => i)
  const x = (i: number) => (i / Math.max(1, n - 1)) * W
  return (
    <figure className="space-y-2" data-testid="dejavu-chart">
      <figcaption className="text-sm text-muted">
        Solid: this well, the 30 min before the alert. Dashed:{' '}
        {overlay.matched_well_name ?? 'a past well'}
        {overlay.formation ? ` (${overlay.formation})` : ''}, ending{' '}
        {overlay.minutes_before_event.toFixed(0)} min before its {overlay.event_type}. Similarity{' '}
        <span className="num font-semibold text-text">{overlay.similarity.toFixed(2)}</span> — not a
        probability.
      </figcaption>
      {overlay.live === null && (
        <p className="text-sm text-warn" data-testid="dejavu-no-live">
          This well’s samples for the alert were replaced by a later replay; only the matched run-up
          is shown.
        </p>
      )}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {overlay.channels.map((c) => {
          const meta = DEJAVU_CHANNELS[c] ?? { label: c, unit: '' }
          const live = overlay.live?.[c] ?? []
          const past = overlay.matched[c] ?? []
          const [lo, hi] = extent([...live, ...past])
          const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
          return (
            <div key={c} className="rounded-lg border border-border p-2">
              <div className="mb-1 flex justify-between text-xs">
                <span className="font-medium text-text">{meta.label}</span>
                <span className="text-muted">{meta.unit}</span>
              </div>
              <svg
                viewBox={`0 0 ${W} ${H}`}
                preserveAspectRatio="none"
                width="100%"
                height={H}
                role="img"
                aria-label={`${meta.label}: live window against the matched past window`}
              >
                <path
                  d={linePath(xs, past, x, y)}
                  fill="none"
                  stroke="var(--text-muted)"
                  strokeDasharray="5 4"
                  strokeWidth={1.5}
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d={linePath(xs, live, x, y)}
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={1.8}
                  vectorEffect="non-scaling-stroke"
                />
              </svg>
            </div>
          )
        })}
      </div>
    </figure>
  )
}
