import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from './api/client'
import { fallbackBriefName, fetchOffsetBrief, filenameFromDisposition, saveBlob } from './reports'

const PDF = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37]) // "%PDF-1.7"

function pdfResponse(headers: Record<string, string>) {
  return new Response(PDF, {
    status: 200,
    headers: { 'Content-Type': 'application/pdf', ...headers },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('brief filename', () => {
  it('reads Content-Disposition, preferring filename*', () => {
    expect(filenameFromDisposition('attachment; filename="SMRITI_brief_SYN-01.pdf"')).toBe(
      'SMRITI_brief_SYN-01.pdf',
    )
    expect(filenameFromDisposition('attachment; filename=plain.pdf')).toBe('plain.pdf')
    expect(
      filenameFromDisposition(`attachment; filename="a.pdf"; filename*=UTF-8''Brief%20%C3%A9.pdf`),
    ).toBe('Brief é.pdf')
    expect(filenameFromDisposition('attachment')).toBeNull()
    expect(filenameFromDisposition(null)).toBeNull()
  })

  it('never lets a path through', () => {
    expect(filenameFromDisposition('attachment; filename="../../etc/x.pdf"')).toBe(
      '.._.._etc_x.pdf',
    )
  })

  it('falls back to a name built from the well', () => {
    expect(fallbackBriefName('SYN ASM/07')).toBe('SMRITI_offset_risk_brief_SYN_ASM_07.pdf')
  })
})

describe('fetchOffsetBrief', () => {
  it('fetches the PDF as a blob on the same origin with progress and the server filename', async () => {
    const fetchMock = vi.fn(async () =>
      pdfResponse({
        'Content-Length': String(PDF.byteLength),
        'Content-Disposition': 'attachment; filename="SMRITI_offset_risk_brief_SYN-ASM-07.pdf"',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const progress = vi.fn()
    const file = await fetchOffsetBrief(7, 5, 'SYN-ASM-07', progress)
    expect(file.filename).toBe('SMRITI_offset_risk_brief_SYN-ASM-07.pdf')
    expect(file.blob.size).toBe(PDF.byteLength)
    expect(file.blob.type).toBe('application/pdf')
    expect(progress).toHaveBeenLastCalledWith({ received: PDF.byteLength, total: PDF.byteLength })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/reports/offset-brief/7?radius_km=5')
    expect(init.credentials).toBe('same-origin')
    expect((init.headers as Record<string, string>)['X-Requested-With']).toBe('smriti')
  })

  it('names the file after the well when the server sends no filename', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => pdfResponse({})),
    )
    const file = await fetchOffsetBrief(3, 2.5, 'SYN-03', undefined)
    expect(file.filename).toBe('SMRITI_offset_risk_brief_SYN-03.pdf')
  })

  it('turns the error envelope into an ApiError with the request id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                code: 'forbidden',
                message: 'Needs read_risk',
                details: {},
                request_id: 'req-9',
              },
            }),
            { status: 403, headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    )
    const err = await fetchOffsetBrief(1, 5, 'W').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(403)
    expect((err as ApiError).message).toBe('Needs read_risk')
    expect((err as ApiError).requestId).toBe('req-9')
  })

  it('reports an unreachable backend as status 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    const err = await fetchOffsetBrief(1, 5, 'W').catch((e: unknown) => e)
    expect((err as ApiError).status).toBe(0)
  })
})

describe('saveBlob', () => {
  it('clicks a download link for an object URL and revokes it afterwards', () => {
    vi.useFakeTimers()
    const revoke = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:brief', configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revoke, configurable: true })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    saveBlob(new Blob(['x']), 'brief.pdf')
    expect(click).toHaveBeenCalledOnce()
    const a = click.mock.contexts[0] as HTMLAnchorElement
    expect(a.download).toBe('brief.pdf')
    expect(a.href).toBe('blob:brief')
    expect(document.querySelector('a[download]')).toBeNull()
    vi.runAllTimers()
    expect(revoke).toHaveBeenCalledWith('blob:brief')
    vi.useRealTimers()
    Reflect.deleteProperty(URL, 'createObjectURL')
    Reflect.deleteProperty(URL, 'revokeObjectURL')
  })
})
