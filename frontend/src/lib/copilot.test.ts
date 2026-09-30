import { describe, expect, it, vi } from 'vitest'

import {
  byteChunks,
  errorResponse,
  LEDGER_EVENTS,
  mockCopilot,
  sse,
  sseResponse,
} from '../test/fixtures/copilot'
import { ApiError } from './api/client'
import {
  answerForClipboard,
  applyEvent,
  askCopilotHref,
  describeError,
  newTurn,
  recordHref,
  retryAfterSeconds,
  SseParser,
  streamCopilot,
  summarizeArgs,
  toCopilotEvent,
  toolOutcome,
  type CopilotCitation,
  type CopilotEvent,
} from './copilot'

const enc = new TextEncoder()

function parseAll(chunks: (string | Uint8Array)[]) {
  const p = new SseParser()
  return chunks.flatMap((c) => p.push(typeof c === 'string' ? enc.encode(c) : c))
}

describe('SseParser', () => {
  it('assembles events split mid-line and mid-event across chunks', () => {
    expect(
      parseAll(['event: tok', 'en\ndata: {"te', 'xt":"a"}\n', '\nevent: done\n', 'data: {}\n\n']),
    ).toEqual([
      { event: 'token', data: '{"text":"a"}' },
      { event: 'done', data: '{}' },
    ])
  })

  it('keeps a UTF-8 character that is split across two chunks', () => {
    const text = 'event: token\ndata: {"text":"12¼″ in the Tipam — “losses”"}\n\n'
    for (const size of [1, 2, 3, 5]) {
      const [msg] = parseAll(byteChunks(text, size))
      expect(JSON.parse(msg!.data)).toEqual({ text: '12¼″ in the Tipam — “losses”' })
    }
  })

  it('joins multi-line data, skips comments and heartbeats, accepts CRLF split across chunks', () => {
    expect(
      parseAll([
        ': heartbeat\r',
        '\n',
        'data: one\r',
        '\ndata:two\r\ndata\r\n',
        '\r',
        '\n: ping\n\n',
      ]),
    ).toEqual([{ event: 'message', data: 'one\ntwo\n' }])
    expect(parseAll(['data: x\rdata: y\r\r:c'])).toEqual([{ event: 'message', data: 'x\ny' }])
  })

  it('does not dispatch an event that the stream never finished', () => {
    expect(parseAll(['event: token\ndata: {"text":"half"}\n'])).toEqual([])
  })
})

describe('toCopilotEvent', () => {
  it('types known events and skips unknown or malformed ones', () => {
    expect(toCopilotEvent({ event: 'token', data: '{"type":"token","text":"a"}' })).toEqual({
      type: 'token',
      text: 'a',
    })
    expect(toCopilotEvent({ event: 'future', data: '{}' })).toBeNull()
    expect(toCopilotEvent({ event: 'token', data: 'not json' })).toBeNull()
    expect(toCopilotEvent({ event: 'token', data: '{"text":3}' })).toBeNull()
  })
})

describe('streamCopilot', () => {
  it('posts the question with the CSRF header and yields every event in order', async () => {
    const { response } = sseResponse(byteChunks(sse(LEDGER_EVENTS), 7))
    const copilot = mockCopilot(() => response)
    const seen: CopilotEvent[] = []
    const done = await streamCopilot(
      'What worked?',
      { well_id: 1 },
      (e) => seen.push(e),
      new AbortController().signal,
    )
    expect(seen.map((e) => e.type)).toEqual([
      'plan',
      'tool',
      'token',
      'token',
      'token',
      'citations',
      'done',
    ])
    expect(done.intent).toBe('ledger')
    const init = copilot.mock.calls[0]![0]!
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({
      'X-Requested-With': 'smriti',
      Accept: 'text/event-stream',
    })
    expect(JSON.parse(String(init.body))).toEqual({ message: 'What worked?', well_id: 1 })
  })

  it('turns a 429 into an error carrying Retry-After', async () => {
    mockCopilot(() => errorResponse(429, 'rate_limited', 'Too many', { 'Retry-After': '42' }))
    const err = await streamCopilot('q', {}, () => undefined, new AbortController().signal).catch(
      (e: unknown) => e,
    )
    expect(err).toBeInstanceOf(ApiError)
    expect(retryAfterSeconds(err)).toBe(42)
    expect(describeError(err).title).toBe('Too many questions this minute')
  })

  it('falls back to the envelope for the wait when Retry-After is missing', async () => {
    mockCopilot(() => errorResponse(429, 'rate_limited', 'Too many', {}, { retry_after_s: 7 }))
    const err = await streamCopilot('q', {}, () => undefined, new AbortController().signal).catch(
      (e: unknown) => e,
    )
    expect(retryAfterSeconds(err)).toBe(7)
  })

  it('names 401, 403, 5xx and network failures plainly', async () => {
    const cases: [() => Response | Promise<Response>, string][] = [
      [() => errorResponse(401, 'not_authenticated', 'no'), 'Sign in to ask the copilot'],
      [() => errorResponse(403, 'forbidden', 'no'), 'Your role cannot use the copilot'],
      [() => errorResponse(503, 'internal_error', 'down'), 'The copilot failed (HTTP 503)'],
      [() => Promise.reject(new TypeError('Failed to fetch')), 'Backend unreachable'],
    ]
    for (const [handler, title] of cases) {
      mockCopilot(handler)
      const err = await streamCopilot('q', {}, () => undefined, new AbortController().signal).catch(
        (e: unknown) => e,
      )
      expect(describeError(err).title).toBe(title)
      expect(retryAfterSeconds(err)).toBeNull()
    }
    expect(describeError(new ApiError(503, { message: 'down', request_id: 'r9' }, '')).detail).toBe(
      'down (request r9)',
    )
  })

  it('reports a stream that closes before "done" as cut off', async () => {
    const { response } = sseResponse([sse(LEDGER_EVENTS.slice(0, 3))])
    mockCopilot(() => response)
    const err = await streamCopilot('q', {}, () => undefined, new AbortController().signal).catch(
      (e: unknown) => e,
    )
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('stream_incomplete')
    expect(describeError(err).title).toBe('The answer was cut off')
  })

  it('cancels the stream on abort and rejects with an AbortError', async () => {
    const { response, control } = sseResponse([sse(LEDGER_EVENTS.slice(0, 2))], { open: true })
    mockCopilot(() => response)
    const ctrl = new AbortController()
    const onEvent = vi.fn()
    const pending = streamCopilot('q', {}, onEvent, ctrl.signal).catch((e: unknown) => e)
    await vi.waitFor(() => expect(onEvent).toHaveBeenCalledTimes(2))
    ctrl.abort()
    const err = await pending
    expect(err).toBeInstanceOf(DOMException)
    expect((err as DOMException).name).toBe('AbortError')
    await control.cancelled
    expect(control.isCancelled()).toBe(true)
  })
})

const cite = (extra: Partial<CopilotCitation>): CopilotCitation => ({
  n: 1,
  kind: 'record',
  label: 'x',
  document_id: null,
  page_no: null,
  span_ids: [],
  filename: null,
  record_type: null,
  record_id: null,
  ...extra,
})

describe('copilot turn helpers', () => {
  it('accumulates tokens, then takes the final answer from "done"', () => {
    let t = newTurn(1, 'q', {})
    for (const e of LEDGER_EVENTS.slice(0, 4)) t = applyEvent(t, e as unknown as CopilotEvent)
    expect(t.status).toBe('streaming')
    expect(t.intent).toBe('ledger')
    expect(t.tools).toHaveLength(1)
    expect(t.text.split('\n')).toHaveLength(3)
    for (const e of LEDGER_EVENTS.slice(4)) t = applyEvent(t, e as unknown as CopilotEvent)
    expect(t.status).toBe('done')
    expect(t.citations.map((c) => c.n)).toEqual([1, 2])
    expect(answerForClipboard(t)).toContain(
      'Sources:\n[1] DDR p.2, SYN-ASM-01_DDR.pdf\n[2] SYN-ASM-01 (database record)',
    )
  })

  it('summarises tool arguments and results in words', () => {
    expect(summarizeArgs({ event_type: 'LOSS', radius_km: 5, formation: null, query: 'mud' })).toBe(
      'problem LOSS · radius 5 km · query “mud”',
    )
    const call = { name: 'get_events', args: {}, facts: 0, empty: null, denied: false }
    expect(toolOutcome({ ...call, facts: 1 })).toBe('1 fact found')
    expect(toolOutcome(call)).toBe('nothing found')
    expect(toolOutcome({ ...call, denied: true, empty: 'Your role does not allow it' })).toBe(
      'Your role does not allow it',
    )
  })

  it('links record citations to their screens', () => {
    expect(recordHref(cite({ record_type: 'well', record_id: 3 }))).toBe('/wells/3')
    expect(recordHref(cite({ record_type: 'risk', record_id: 3 }))).toBe('/wells/3?tab=risk')
    expect(recordHref(cite({ record_type: 'alert', record_id: 9 }))).toBe('/alerts?status=all&id=9')
    expect(recordHref(cite({ record_type: 'ledger', record_id: 0 }))).toBe('/ledger')
    expect(recordHref(cite({ record_type: 'event', record_id: 5 }))).toBeNull()
    expect(recordHref(cite({ kind: 'page', document_id: 7, page_no: 1 }))).toBeNull()
  })

  it('builds the "Ask copilot" link for an alert', () => {
    expect(askCopilotHref({ id: 9, well_id: 4 })).toBe(
      '/search?copilot=Why+did+this+alert+fire%3F&alert=9&well=4',
    )
  })
})
