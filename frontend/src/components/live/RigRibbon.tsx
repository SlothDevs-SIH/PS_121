import { RIG_STATES, rigMeta, rigSegments } from '../../lib/liveView'

const W = 1000

/** Rig state along the same time axis as the channel strips; each state also has a code
 * in the legend, so colour is not the only cue. */
export function RigRibbon({
  times,
  states,
  domain,
}: {
  times: number[]
  states: (string | null)[]
  domain: [number, number]
}) {
  const segs = rigSegments(times, states)
  const [t0, t1] = domain
  const x = (t: number) => ((t - t0) / (t1 - t0 || 1)) * W
  const seen = [...new Set(segs.map((s) => s.state))]
  const now = rigMeta(states[states.length - 1])
  return (
    <div className="grid grid-cols-[8.5rem_1fr] items-center gap-2" data-testid="rig-ribbon">
      <div className="text-right">
        <div className="text-xs text-muted">Rig state</div>
        <div className="text-sm font-semibold text-text" data-testid="rig-state-now">
          {now.label}
        </div>
      </div>
      <div className="min-w-0">
        <svg
          viewBox={`0 0 ${W} 14`}
          preserveAspectRatio="none"
          width="100%"
          height={14}
          role="img"
          aria-label={`Rig state over the window; now ${now.label}`}
          className="block overflow-hidden rounded"
        >
          {segs.map((s) => (
            <rect
              key={`${s.from}-${s.state}`}
              x={x(s.from)}
              width={Math.max(1, x(s.to) - x(s.from))}
              y={0}
              height={14}
              fill={rigMeta(s.state).color}
            >
              <title>{rigMeta(s.state).label}</title>
            </rect>
          ))}
        </svg>
        <ul className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-muted" aria-label="Rig states">
          {seen
            .filter((s) => s in RIG_STATES)
            .map((s) => (
              <li key={s} className="inline-flex items-center gap-1">
                <span
                  className="inline-block h-2 w-3 rounded-sm"
                  style={{ background: rigMeta(s).color }}
                  aria-hidden
                />
                {rigMeta(s).code} {rigMeta(s).label}
              </li>
            ))}
        </ul>
      </div>
    </div>
  )
}
