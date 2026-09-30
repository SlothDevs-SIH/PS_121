/**
 * Copilot SSE fixtures: the event sequences `backend/app/copilot/engine.py` streams, and a
 * fetch stub that answers `POST /api/v1/copilot/chat` with a real ReadableStream delivered in
 * chosen chunks (so tests can split an event, a CRLF or a UTF-8 character across reads).
 */
import { vi } from 'vitest'

type Ev = Record<string, unknown> & { type: string }

/** The events as the backend frames them: `event: <type>\ndata: <json>\n\n`. */
export function sse(events: Ev[]): string {
  return events.map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join('')
}

const enc = new TextEncoder()

/** Split a string's UTF-8 bytes into chunks of at most `size` bytes (cuts inside characters). */
export function byteChunks(text: string, size: number): Uint8Array[] {
  const bytes = enc.encode(text)
  const out: Uint8Array[] = []
  for (let i = 0; i < bytes.length; i += size) out.push(bytes.slice(i, i + size))
  return out
}

export interface StreamControl {
  /** Resolves when the client cancels the stream (abort, unmount). */
  cancelled: Promise<unknown>
  isCancelled: () => boolean
  /** Deliver more bytes (only for `open` streams). */
  push: (chunk: string | Uint8Array) => void
  close: () => void
}

/**
 * A streamed 200 response. Chunks are delivered one per read; with `open` the stream stays
 * open after them (for stop / abort tests) until `close()`.
 */
export function sseResponse(
  chunks: (string | Uint8Array)[],
  { open = false }: { open?: boolean } = {},
): { response: Response; control: StreamControl } {
  let cancelledFlag = false
  let resolveCancel: (v: unknown) => void = () => undefined
  const cancelled = new Promise((r) => (resolveCancel = r))
  let ctrl: ReadableStreamDefaultController<Uint8Array> | null = null
  const queue = chunks.map((c) => (typeof c === 'string' ? enc.encode(c) : c))
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      ctrl = c
    },
    pull(c) {
      const next = queue.shift()
      if (next) c.enqueue(next)
      else if (!open) c.close()
    },
    cancel(reason) {
      cancelledFlag = true
      resolveCancel(reason)
    },
  })
  const control: StreamControl = {
    cancelled,
    isCancelled: () => cancelledFlag,
    push: (chunk) => ctrl?.enqueue(typeof chunk === 'string' ? enc.encode(chunk) : chunk),
    close: () => ctrl?.close(),
  }
  const response = new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
  return { response, control }
}

/** A JSON error envelope, as the backend sends for every non-2xx. */
export function errorResponse(
  status: number,
  code: string,
  message: string,
  headers: Record<string, string> = {},
  details: Record<string, unknown> = {},
): Response {
  return new Response(JSON.stringify({ error: { code, message, details, request_id: 'req-c1' } }), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

type Handler = (init: RequestInit | undefined) => Response | Promise<Response>

/**
 * Answer copilot POSTs with `handler` and pass every other request to the fetch stub already
 * installed (`mockBackend` / `fullBackend`). Returns the copilot mock for call assertions.
 */
export function mockCopilot(handler: Handler) {
  const base = globalThis.fetch
  const copilot = vi.fn(async (init: RequestInit | undefined) => {
    const signal = init?.signal
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    return handler(init)
  })
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      return url.startsWith('/api/v1/copilot/chat') ? copilot(init) : base(input, init)
    }),
  )
  return copilot
}

const PAGE_CITE = {
  n: 1,
  kind: 'page',
  label: 'DDR p.2',
  document_id: 7,
  page_no: 2,
  span_ids: [102],
  filename: 'SYN-ASM-01_DDR.pdf',
  record_type: null,
  record_id: null,
}
const WELL_CITE = {
  n: 2,
  kind: 'record',
  label: 'SYN-ASM-01',
  document_id: null,
  page_no: null,
  span_ids: [],
  filename: null,
  record_type: 'well',
  record_id: 1,
}

/** "What worked for losses in the Tipam?": a ledger answer citing a page and a well. */
export const LEDGER_EVENTS: Ev[] = [
  {
    type: 'plan',
    intent: 'ledger',
    tools: ['get_ledger'],
    entities: { wells: [], formation: 'Tipam Sandstone', event_type: 'LOSS' },
  },
  {
    type: 'tool',
    name: 'get_ledger',
    args: { event_type: 'LOSS', formation: 'Tipam Sandstone' },
    facts: 2,
    empty: null,
    denied: false,
  },
  {
    type: 'token',
    text: 'Recorded treatments for losses in the Tipam Sandstone, ranked by how often they worked (Mitigation Ledger):\n',
  },
  {
    type: 'token',
    text: '**LCM pill (coarse)** worked 7 of 8 times in the 12¼″ section [1][2]\n',
  },
  {
    type: 'token',
    text: 'Observational records: associated with success, not proven to cause it.\n',
  },
  { type: 'citations', items: [PAGE_CITE, WELL_CITE] },
  {
    type: 'done',
    refused: false,
    engine: 'rules',
    intent: 'ledger',
    took_ms: 18.2,
    answer:
      'Recorded treatments for losses in the Tipam Sandstone, ranked by how often they worked (Mitigation Ledger):\n' +
      '**LCM pill (coarse)** worked 7 of 8 times in the 12¼″ section [1][2]\n' +
      'Observational records: associated with success, not proven to cause it.\n',
  },
]

/** A question the records cannot answer: the backend refuses instead of guessing. */
export const UNANSWERABLE_EVENTS: Ev[] = [
  {
    type: 'plan',
    intent: 'search',
    tools: ['search_documents'],
    entities: { wells: ['SYN-ASM-20'] },
  },
  {
    type: 'tool',
    name: 'search_documents',
    args: { query: 'rig cost per day', well_id: 20 },
    facts: 3,
    empty: null,
    denied: false,
  },
  {
    type: 'token',
    text: 'No record found: the closest report passages do not mention cost. Try Knowledge Search for the full list.\n',
  },
  { type: 'citations', items: [] },
  {
    type: 'done',
    refused: true,
    engine: 'rules',
    intent: 'search',
    took_ms: 9.4,
    answer:
      'No record found: the closest report passages do not mention cost. Try Knowledge Search for the full list.\n',
  },
]

/** PAGE (test/utils) as page 2 of document 7, for the citation above. */
export function page2(page: { status: number; body: Record<string, unknown> }) {
  return {
    status: 200,
    body: { ...page.body, page_no: 2, image_url: '/api/v1/documents/7/pages/2/image' },
  }
}
