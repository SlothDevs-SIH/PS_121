import { Link } from 'react-router'

export function NotFound() {
  return (
    <div className="mx-auto max-w-xl space-y-2 py-10 text-center">
      <h1 className="text-2xl font-semibold text-text">Page not found</h1>
      <p className="text-muted">
        This page doesn't exist.{' '}
        <Link className="text-accent underline" to="/system">
          Go to System Status
        </Link>
      </p>
    </div>
  )
}
