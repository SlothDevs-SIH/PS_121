import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Providers } from '../../app/providers'
import { makeQueryClient } from '../../app/queryClient'
import { ME } from '../../test/utils'
import { RiskBriefButton } from './RiskBriefButton'

type Handler = (url: string) => Response | Promise<Response>

function stubFetch(brief: Handler, me: unknown = ME.body) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.startsWith('/api/v1/me'))
      return new Response(JSON.stringify(me), { headers: { 'Content-Type': 'application/json' } })
    return brief(url)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderButton(props: { wellId?: number; radiusKm?: number } = {}) {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false } })
  render(
    <Providers client={client}>
      <RiskBriefButton wellId={props.wellId ?? 7} wellName="SYN-ASM-07" radiusKm={props.radiusKm} />
    </Providers>,
  )
}

let click: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  // jsdom has no object URLs; give the static methods for the test only.
  Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:brief', configurable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
  click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})
afterEach(() => {
  vi.unstubAllGlobals()
  Reflect.deleteProperty(URL, 'createObjectURL')
  Reflect.deleteProperty(URL, 'revokeObjectURL')
})

describe('RiskBriefButton', () => {
  it('downloads the PDF and saves it under the server filename', async () => {
    const fetchMock = stubFetch(
      () =>
        new Response(new Uint8Array([37, 80, 68, 70]), {
          headers: {
            'Content-Type': 'application/pdf',
            'Content-Disposition': 'attachment; filename="SMRITI_offset_risk_brief_SYN-ASM-07.pdf"',
          },
        }),
    )
    renderButton({ radiusKm: 8 })
    await userEvent.click(screen.getByRole('button', { name: /Offset Risk Brief/ }))
    expect(
      await screen.findByText('Saved SMRITI_offset_risk_brief_SYN-ASM-07.pdf'),
    ).toBeInTheDocument()
    expect(click).toHaveBeenCalledOnce()
    expect((click.mock.contexts[0] as HTMLAnchorElement).download).toBe(
      'SMRITI_offset_risk_brief_SYN-ASM-07.pdf',
    )
    expect(fetchMock.mock.calls.map((c) => String(c[0]))).toContain(
      '/api/v1/reports/offset-brief/7?radius_km=8',
    )
  })

  it('shows progress while the brief is being made', async () => {
    let finish: (r: Response) => void = () => {}
    stubFetch(() => new Promise<Response>((resolve) => (finish = resolve)))
    renderButton()
    await userEvent.click(screen.getByRole('button', { name: /Offset Risk Brief/ }))
    expect(await screen.findByText('Preparing the brief…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Offset Risk Brief/ })).toBeDisabled()
    finish(new Response(new Uint8Array([1]), { headers: { 'Content-Type': 'application/pdf' } }))
    expect(
      await screen.findByText('Saved SMRITI_offset_risk_brief_SYN-ASM-07.pdf'),
    ).toBeInTheDocument()
  })

  it('surfaces the backend error with its request id', async () => {
    stubFetch(
      () =>
        new Response(
          JSON.stringify({
            error: { code: 'internal', message: 'render failed', details: {}, request_id: 'req-7' },
          }),
          { status: 500, headers: { 'Content-Type': 'application/json' } },
        ),
    )
    renderButton()
    await userEvent.click(screen.getByRole('button', { name: /Offset Risk Brief/ }))
    expect(await screen.findByText(/render failed \(request req-7\)/)).toBeInTheDocument()
    expect(click).not.toHaveBeenCalled()
  })

  it('is off, with the reason, for roles without the risk permission', async () => {
    stubFetch(() => new Response('', { status: 500 }), {
      ...ME.body,
      roles: ['viewer'],
      permissions: ['read_knowledge', 'copilot'],
    })
    renderButton()
    expect(await screen.findByText('Needs the drilling-engineer role')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Offset Risk Brief/ })).toBeDisabled()
  })
})
