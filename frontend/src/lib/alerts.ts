/** Alert list ordering and score wording (F4). A similarity is never called a probability. */
import type { AlertOut } from './api/client'
import { pct } from './risk'

export const SCORE_WORDS: Record<string, string> = {
  probability: 'model probability',
  similarity: 'similarity (not a probability)',
  indicator: 'physics indicator',
  prior: 'offset prior probability',
}
/** Critical well-control alerts (kick and friends, budget-exempt) always sort first. */
export function sortAlerts(items: AlertOut[]): AlertOut[] {
  return [...items].sort(
    (a, b) =>
      Number(b.budget_exempt) - Number(a.budget_exempt) ||
      Date.parse(b.t_data) - Date.parse(a.t_data) ||
      b.id - a.id,
  )
}

export function scoreText(a: AlertOut): string {
  if (a.score === null) return '—'
  const word = SCORE_WORDS[a.score_kind] ?? a.score_kind
  return a.score_kind === 'similarity' || a.score_kind === 'indicator'
    ? `${a.score.toFixed(2)} ${word}`
    : `${pct(a.score)} ${word}`
}
