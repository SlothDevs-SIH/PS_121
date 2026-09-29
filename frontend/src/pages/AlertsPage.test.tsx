import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { FakeWebSocket } from '../test/fakeWebSocket'
import {
  ALERT_PAGE,
  alertFixture,
  DEJAVU,
  DEJAVU_ALERT,
  fullBackend,
  ME,
  REALTIME,
  renderApp,
} from '../test/utils'

const ok = (body: unknown) => ({ status: 200, body })

function backend(extra: Record<string, { status: number; body: unknown }> = {}) {
  return fullBackend({
    'GET /api/v1/alerts': ALERT_PAGE,
    'GET /api/v1/alerts/8': ok(alertFixture(8)),
    'GET /api/v1/alerts/10': ok(DEJAVU_ALERT),
    'GET /api/v1/alerts/10/dejavu': DEJAVU,
    '/api/v1/wells/4/realtime': REALTIME,
    ...extra,
  })
}

describe('Alerts Center', () => {
  it('lists critical well control first and opens the detail with evidence', async () => {
    backend({ 'GET /api/v1/alerts/9': ok(ALERT_PAGE.body.items[1]) })
    renderApp('/alerts')
    const rows = await screen.findAllByTestId('alert-row')
    expect(rows.map((r) => r.dataset['id'])).toEqual(['9', '10', '8'])
    expect(rows[0]).toHaveTextContent('pinned')
    expect(screen.getByTestId('alert-counts')).toHaveTextContent('3 new')
    await userEvent.click(rows[2]!)
    const detail = await screen.findByTestId('alert-detail')
    expect(within(detail).getByTestId('alert-score')).toHaveTextContent('41% model probability')
    // Stream evidence: the window ending at the alert's data time.
    expect(await within(detail).findByTestId('stream-evidence')).toBeInTheDocument()
    expect(within(detail).getAllByTestId('channel-strip')).toHaveLength(2)
    const past = within(detail).getByTestId('past-event')
    expect(within(past).getByText('SYN-ASM-01')).toHaveAttribute('href', '/wells/1?tab=events')
    expect(within(past).getByTestId('evidence-link')).toHaveTextContent('DDR p.1')
    await userEvent.click(within(detail).getByRole('tab', { name: /Drivers/ }))
    expect(within(detail).getByTestId('drivers')).toHaveTextContent('Flow out − in (5 min mean)')
    await userEvent.click(within(detail).getByRole('tab', { name: /What worked/ }))
    expect(within(detail).getByTestId('recommendations')).toHaveTextContent('LCM pill (coarse)')
    expect(within(detail).getByTestId('alert-caveat')).toHaveTextContent('not proven to cause')
  })

  it('shows the Déjà Vu overlay with similarity, never probability', async () => {
    backend()
    renderApp('/alerts?id=10')
    const detail = await screen.findByTestId('alert-detail')
    expect(within(detail).getByTestId('alert-score')).toHaveTextContent(
      'similarity (not a probability)',
    )
    await userEvent.click(within(detail).getByRole('tab', { name: 'Déjà Vu' }))
    const chart = await within(detail).findByTestId('dejavu-chart')
    expect(chart).toHaveTextContent('SYN-ASM-31 (Tipam Sandstone), ending 8 min before its LOSS')
    expect(chart).toHaveTextContent('0.81')
    expect(chart).toHaveTextContent('not a probability')
    expect(within(chart).getAllByRole('img')).toHaveLength(2)
  })

  it('acknowledges optimistically and rolls back when the backend refuses', async () => {
    const fetch = backend({
      'POST /api/v1/alerts/8/ack': {
        status: 409,
        body: {
          error: {
            code: 'invalid_alert_state',
            message: 'Alert 8 is already ack.',
            details: {},
            request_id: 'r',
          },
        },
      },
    })
    renderApp('/alerts?id=8')
    const detail = await screen.findByTestId('alert-detail')
    await userEvent.click(within(detail).getByRole('button', { name: 'Acknowledge' }))
    expect(await within(detail).findByTestId('action-error')).toHaveTextContent(
      'Alert 8 is already ack.',
    )
    expect(within(detail).getByRole('button', { name: 'Acknowledge' })).toBeInTheDocument()
    expect(
      fetch.mock.calls.some(
        ([u, i]) => String(u) === '/api/v1/alerts/8/ack' && i?.method === 'POST',
      ),
    ).toBe(true)
  })

  it('dismisses only with a reason and records feedback', async () => {
    const fetch = backend({
      'POST /api/v1/alerts/8/dismiss': ok(
        alertFixture(8, { status: 'dismissed', dismiss_reason: 'handled on the rig' }),
      ),
      'POST /api/v1/alerts/8/feedback': {
        status: 201,
        body: {
          id: 1,
          alert_id: 8,
          verdict: 'useful',
          comment: null,
          user_id: 'dev',
          created_at: 'x',
        },
      },
    })
    renderApp('/alerts?id=8')
    const detail = await screen.findByTestId('alert-detail')
    await userEvent.click(within(detail).getByRole('button', { name: /Dismiss…/ }))
    const submit = within(detail).getByRole('button', { name: 'Dismiss' })
    expect(submit).toBeDisabled()
    await userEvent.type(within(detail).getByLabelText('Reason'), 'handled on the rig')
    await userEvent.click(submit)
    await waitFor(() => {
      const call = fetch.mock.calls.find(([u]) => String(u) === '/api/v1/alerts/8/dismiss')
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ reason: 'handled on the rig' })
    })
    await userEvent.click(within(detail).getByRole('button', { name: 'Useful' }))
    await waitFor(() =>
      expect(fetch.mock.calls.some(([u]) => String(u) === '/api/v1/alerts/8/feedback')).toBe(true),
    )
  })

  it('flags an alert without evidence as a defect, and a viewer cannot act', async () => {
    backend({
      'GET /api/v1/alerts/8': ok(alertFixture(8, { evidence: [] })),
      '/api/v1/me': {
        status: 200,
        body: { ...ME.body, roles: ['viewer'], permissions: ['read_knowledge', 'copilot'] },
      },
    })
    renderApp('/alerts?id=8')
    const detail = await screen.findByTestId('alert-detail')
    expect(within(detail).getByTestId('no-evidence')).toHaveTextContent('That is a defect')
    expect(
      await within(detail).findByText(/cannot act on them|not act on them/),
    ).toBeInTheDocument()
    expect(within(detail).queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
  })

  it('asks the copilot why an alert fired and shows its citations', async () => {
    const fetch = backend({
      'POST /api/v1/copilot/chat': ok({
        answer: 'Alert 8 fired on flow out − in [1].',
        citations: [
          {
            n: 1,
            kind: 'record',
            label: 'alert 8',
            document_id: null,
            page_no: null,
            span_ids: [],
            filename: null,
            record_type: 'alert',
            record_id: 8,
          },
        ],
        intent: 'alert',
        tools: [],
        refused: false,
        engine: 'rules',
        took_ms: 12,
      }),
    })
    renderApp('/alerts?id=8')
    await userEvent.click(await screen.findByTestId('why-fired'))
    expect(await screen.findByTestId('why-answer')).toHaveTextContent('[1] alert 8')
    const call = fetch.mock.calls.find(([u]) => String(u).startsWith('/api/v1/copilot/chat'))!
    expect(String(call[0])).toBe('/api/v1/copilot/chat?stream=false')
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({ alert_id: 8, well_id: 4 })
  })
})

describe('live alert toasts', () => {
  it('toasts pushed alerts and counts them in the title until Alerts is opened', async () => {
    backend()
    document.title = 'SMRITI'
    renderApp('/')
    await waitFor(() => expect(FakeWebSocket.find('/ws/alerts')).toBeDefined())
    const ws = FakeWebSocket.find('/ws/alerts')!
    act(() => {
      ws.open()
      ws.receive({
        type: 'alert',
        action: 'created',
        alert: alertFixture(12, { severity: 'critical', title: 'Possible kick' }),
      })
    })
    const toast = await screen.findByTestId('alert-toast')
    expect(toast).toHaveAttribute('role', 'alert')
    expect(toast).toHaveTextContent('Possible kick')
    await waitFor(() => expect(document.title).toBe('(1) SMRITI'))
    await userEvent.click(within(toast).getByRole('link'))
    await waitFor(() => expect(document.title).toBe('SMRITI'))
    expect(screen.queryByTestId('alert-toast')).not.toBeInTheDocument()
  })
})
