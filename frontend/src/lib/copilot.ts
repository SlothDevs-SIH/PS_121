/**
 * Copilot answers streamed over server-sent events (B5: `POST /api/v1/copilot/chat`).
 *
 * EventSource can neither POST nor send the CSRF header, so the stream is read with `fetch`
 * and a ReadableStream reader. `SseParser` follows the SSE rules (WHATWG HTML §9.2): an event
 * ends at a blank line, `data:` lines join with "\n", lines starting with ":" are comments
 * (heartbeats), and CR, LF and CRLF all end a line, even a CRLF split across two chunks. Bytes
 * go through one streaming TextDecoder, so a UTF-8 character split across chunks survives.
 *
 * The backend sends `plan`, one `tool` per call, `token` (one line of the answer each),
 * `citations` and `done`. There is no error event: a stream that closes before `done` means the
 * answer was cut off, and is reported as such rather than shown as if complete.
 */
import { ApiError } from './api/client'
import type { components } from './api/schema'

export type CopilotCitation = components['schemas']['CopilotCitation']
export type CopilotToolCall = components['schemas']['CopilotToolCall']

/** What is on screen: "this well", "this alert". */
export interface CopilotContext {
  well_id?: number | null
  alert_id?: number | null
}

export interface PlanEvent {
  type: 'plan'
  intent: string
  tools: string[]
  entities: Record<string, unknown>
}
export interface ToolEvent extends CopilotToolCall {
  type: 'tool'
}
export interface TokenEvent {
  type: 'token'
  text: string
}
export interface CitationsEvent {
  type: 'citations'
  items: CopilotCitation[]
}
export interface DoneEvent {
  type: 'done'
  refused: boolean
  engine: string
  intent: string
  took_ms: number
  answer: string
  /** LLM engine only: sentences dropped because they cited no tool result. */
  dropped_sentences?: number
}
export type CopilotEvent = PlanEvent | ToolEvent | TokenEvent | CitationsEvent | DoneEvent

export interface SseMessage {
  event: string
  data: string
}

/** Incremental SSE parser: push byte chunks, get the complete events they finish. */
export class SseParser {
  private readonly decoder = new TextDecoder()
  private buffer = ''
  private event = ''
  private data: string[] = []

  push(chunk: Uint8Array): SseMessage[] {
    this.buffer += this.decoder.decode(chunk, { stream: true })
    const out: SseMessage[] = []
    let start = 0
    for (let i = 0; i < this.buffer.length; i++) {
      const c = this.buffer[i]
      if (c !== '\n' && c !== '\r') continue
      // A CR at the end of the chunk may be the first half of a CRLF: wait for the next one.
      if (c === '\r' && i === this.buffer.length - 1) break
      this.line(this.buffer.slice(start, i), out)
      if (c === '\r' && this.buffer[i + 1] === '\n') i++
      start = i + 1
    }
    this.buffer = this.buffer.slice(start)
    return out
  }

  private line(line: string, out: SseMessage[]) {
    if (line === '') {
      if (this.data.length) out.push({ event: this.event || 'message', data: this.data.join('\n') })
      this.event = ''
      this.data = []
      return
    }
    if (line.startsWith(':')) return
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    let value = colon < 0 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.event = value
    else if (field === 'data') this.data.push(value)
    // `id` and `retry` are for EventSource reconnection, which a POST answer does not do.
  }
}

const KINDS = new Set(['plan', 'tool', 'token', 'citations', 'done'])

/** A typed copilot event, or null for unknown or malformed ones (skipped, not fatal). */
export function toCopilotEvent(msg: SseMessage): CopilotEvent | null {
  if (!KINDS.has(msg.event)) return null
  let body: unknown
  try {
    body = JSON.parse(msg.data)
  } catch {
    return null
  }
  if (typeof body !== 'object' || body === null) return null
  const ev: Record<string, unknown> = { ...body, type: msg.event }
  if (ev.type === 'token' && typeof ev['text'] !== 'string') return null
  if (ev.type === 'citations' && !Array.isArray(ev['items'])) return null
  if (ev.type === 'plan' && !Array.isArray(ev['tools'])) return null
  return ev as unknown as CopilotEvent
}

const aborted = () => new DOMException('The answer was stopped.', 'AbortError')

async function errorFrom(response: Response): Promise<ApiError> {
  let body: Partial<components['schemas']['ErrorBody']> | null = null
  try {
    const data: unknown = JSON.parse(await response.text())
    if (typeof data === 'object' && data !== null && 'error' in data)
      body = (data as { error: components['schemas']['ErrorBody'] }).error
  } catch {
    body = null
  }
  if (response.status === 429) {
    const header = Number(response.headers.get('Retry-After'))
    const fromBody = Number(body?.details?.['retry_after_s'])
    const retry = header > 0 ? header : fromBody > 0 ? fromBody : 60
    body = {
      code: 'rate_limited',
      message: 'Too many questions this minute.',
      ...body,
      details: { ...body?.details, retry_after_s: Math.ceil(retry) },
    }
  }
  return new ApiError(
    response.status,
    body,
    `HTTP ${response.status} ${response.statusText}`.trim(),
  )
}

/**
 * Ask the copilot and call `onEvent` for each event as it arrives. Resolves with the `done`
 * event; rejects with an ApiError (HTTP error, network, cut-off stream) or, when `signal`
 * aborts, with an AbortError (the reader is cancelled so the connection closes at once).
 */
export async function streamCopilot(
  message: string,
  context: CopilotContext,
  onEvent: (ev: CopilotEvent) => void,
  signal: AbortSignal,
): Promise<DoneEvent> {
  let response: Response
  try {
    response = await fetch('/api/v1/copilot/chat', {
      method: 'POST',
      signal,
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        // Same-origin cookie sessions: the backend's CSRF rule (see lib/api/client.ts).
        'X-Requested-With': 'smriti',
      },
      body: JSON.stringify({ message, ...context }),
    })
  } catch (cause) {
    if (signal.aborted) throw aborted()
    throw new ApiError(0, null, `Backend unreachable: ${String(cause)}`)
  }
  if (!response.ok) throw await errorFrom(response)
  if (!response.body) throw new ApiError(response.status, null, 'The answer had no body.')

  const reader = response.body.getReader()
  const cancel = () => void reader.cancel().catch(() => undefined)
  signal.addEventListener('abort', cancel, { once: true })
  const parser = new SseParser()
  let done: DoneEvent | null = null
  try {
    while (!signal.aborted) {
      let chunk: ReadableStreamReadResult<Uint8Array>
      try {
        chunk = await reader.read()
      } catch (cause) {
        if (signal.aborted) break
        throw new ApiError(
          0,
          { code: 'stream_interrupted', message: `The connection dropped: ${String(cause)}` },
          'The connection dropped.',
        )
      }
      if (chunk.done) break
      for (const msg of parser.push(chunk.value)) {
        const ev = toCopilotEvent(msg)
        if (!ev || signal.aborted) continue
        if (ev.type === 'done') done = ev
        onEvent(ev)
      }
    }
  } finally {
    signal.removeEventListener('abort', cancel)
  }
  if (signal.aborted) throw aborted()
  if (!done)
    throw new ApiError(
      0,
      { code: 'stream_incomplete', message: 'The answer stopped before it finished.' },
      'The answer stopped before it finished.',
    )
  return done
}

/** Seconds to wait before asking again, for a 429 answer; null for anything else. */
export function retryAfterSeconds(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 429) return null
  const s = Number(err.details['retry_after_s'])
  return s > 0 ? s : 60
}

/** A plain-language title and hint for a failed question. */
export function describeError(err: unknown): { title: string; detail: string } {
  if (!(err instanceof ApiError))
    return { title: 'The copilot failed', detail: err instanceof Error ? err.message : String(err) }
  const ref = err.requestId ? ` (request ${err.requestId})` : ''
  if (err.code === 'stream_incomplete' || err.code === 'stream_interrupted')
    return {
      title: 'The answer was cut off',
      detail:
        'The connection closed before the answer finished, so what arrived is incomplete. Ask again.',
    }
  if (err.status === 0)
    return {
      title: 'Backend unreachable',
      detail: 'The copilot could not be reached. Check the connection, then ask again.',
    }
  if (err.status === 401)
    return {
      title: 'Sign in to ask the copilot',
      detail: 'Your session has expired or you are not signed in. Sign in again, then ask.',
    }
  if (err.status === 403)
    return err.code === 'csrf_check_failed'
      ? { title: 'The request was refused', detail: `${err.message}${ref}` }
      : {
          title: 'Your role cannot use the copilot',
          detail: 'Ask an administrator for the copilot permission.',
        }
  if (err.status === 429)
    return {
      title: 'Too many questions this minute',
      detail: 'The copilot limits how many questions each person asks per minute.',
    }
  if (err.status === 422)
    return { title: 'The question was not accepted', detail: `${err.message}${ref}` }
  return {
    title: `The copilot failed (HTTP ${err.status})`,
    detail: `${err.message}${ref}`,
  }
}

// ─── One question and its answer ────────────────────────────────────────────────────────

export type TurnStatus = 'streaming' | 'done' | 'stopped' | 'error'

export interface Turn {
  id: number
  question: string
  context: CopilotContext
  status: TurnStatus
  intent: string | null
  tools: ToolEvent[]
  /** The answer so far: `token` lines appended, replaced by `done.answer` at the end. */
  text: string
  citations: CopilotCitation[]
  done: DoneEvent | null
  error: unknown
}

export function newTurn(id: number, question: string, context: CopilotContext): Turn {
  return {
    id,
    question,
    context,
    status: 'streaming',
    intent: null,
    tools: [],
    text: '',
    citations: [],
    done: null,
    error: null,
  }
}

export function applyEvent(turn: Turn, ev: CopilotEvent): Turn {
  switch (ev.type) {
    case 'plan':
      return { ...turn, intent: ev.intent }
    case 'tool':
      return { ...turn, tools: [...turn.tools, ev] }
    case 'token':
      return { ...turn, text: turn.text + ev.text }
    case 'citations':
      return { ...turn, citations: ev.items }
    case 'done':
      return { ...turn, status: 'done', done: ev, intent: ev.intent, text: ev.answer }
  }
}

// ─── Explaining an answer ───────────────────────────────────────────────────────────────

export const TOOL_LABELS: Record<string, string> = {
  search_documents: 'Searched the reports',
  get_events: 'Looked up recorded events',
  get_offset_wells: 'Found offset wells',
  get_risk_profile: 'Read the offset risk profile',
  get_ledger: 'Read the Mitigation Ledger',
  get_well_summary: 'Read the well summary',
  explain_alert: 'Explained the alert',
}

const ARG_LABELS: Record<string, string> = {
  query: 'query',
  well_id: 'well',
  alert_id: 'alert',
  radius_km: 'radius',
  formation: 'formation',
  event_type: 'problem',
  hole_size_in: 'hole size',
}

/** "problem LOSS · formation Tipam · radius 5 km" for a tool call's arguments. */
export function summarizeArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => {
      const value = Array.isArray(v) ? v.join(', ') : String(v)
      const unit = k === 'radius_km' ? ' km' : k === 'hole_size_in' ? ' in' : ''
      const quoted = k === 'query' ? `“${value}”` : value
      return `${ARG_LABELS[k] ?? k.replace(/_/g, ' ')} ${quoted}${unit}`
    })
    .join(' · ')
}

/** What a tool call returned, in words. */
export function toolOutcome(t: CopilotToolCall): string {
  if (t.denied) return t.empty ?? 'not allowed for your role'
  if (t.facts > 0) return `${t.facts} ${t.facts === 1 ? 'fact' : 'facts'} found`
  return t.empty ?? 'nothing found'
}

/** The screen a database-record citation opens, or null when there is none to open. */
export function recordHref(c: CopilotCitation): string | null {
  if (c.kind !== 'record' || c.record_id === null) return null
  switch (c.record_type) {
    case 'well':
      return `/wells/${c.record_id}`
    case 'risk':
      return `/wells/${c.record_id}?tab=risk`
    case 'alert':
      return `/alerts?status=all&id=${c.record_id}`
    case 'ledger':
      return '/ledger'
    default:
      return null
  }
}

/** A refusal without its own "No record found" lead-in, which the UI states as a heading. */
export function refusalReason(text: string): string {
  return text
    .trim()
    .replace(/^no record found[.:]?\s*/i, '')
    .replace(/^./, (c) => c.toUpperCase())
}

/** One line per source, as it would read under a copied answer. */
export function citationLine(c: CopilotCitation): string {
  if (c.kind === 'page') return `[${c.n}] ${c.label}${c.filename ? `, ${c.filename}` : ''}`
  return `[${c.n}] ${c.label} (database record)`
}

/** The answer with its sources, for the clipboard. */
export function answerForClipboard(turn: Turn): string {
  const text = turn.text.trim()
  if (!turn.citations.length) return text
  return `${text}\n\nSources:\n${turn.citations.map(citationLine).join('\n')}`
}

/** Knowledge Search with the copilot open, asking about an alert (its detail's "Ask copilot"). */
export function askCopilotHref(alert: { id: number; well_id: number | null }): string {
  const q = new URLSearchParams({ copilot: 'Why did this alert fire?', alert: String(alert.id) })
  if (alert.well_id !== null) q.set('well', String(alert.well_id))
  return `/search?${q.toString()}`
}
