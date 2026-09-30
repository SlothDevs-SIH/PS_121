import { ApiError } from '../../lib/api/client'
import { Badge } from '../ui/Badge'

/** A failed data view, per FRONTEND_PLAN §3.5: planned phase, unreachable, not allowed, or
 * the backend's message with its request id for support. */
export function QueryProblem({ error, what }: { error: unknown; what: string }) {
  if (error instanceof ApiError && error.plannedPhase)
    return <Badge tone="warn">Planned for backend phase {error.plannedPhase}</Badge>
  if (error instanceof ApiError && error.status === 0)
    return (
      <p className="text-sm text-danger" role="alert">
        Backend unreachable: {what} could not be loaded.
      </p>
    )
  if (error instanceof ApiError && (error.status === 401 || error.status === 403))
    return (
      <p className="text-sm text-muted" role="note">
        Your role does not include {what}.
      </p>
    )
  const message = error instanceof Error ? error.message : String(error)
  const requestId = error instanceof ApiError ? error.requestId : null
  return (
    <p className="text-sm text-danger" role="alert">
      {what[0]?.toUpperCase()}
      {what.slice(1)} could not be loaded: {message}
      {requestId && (
        <>
          {' '}
          (request <code className="select-all">{requestId}</code>)
        </>
      )}
    </p>
  )
}
