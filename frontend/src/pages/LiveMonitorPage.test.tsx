import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { FakeWebSocket } from '../test/fakeWebSocket'
import {
  ALERT_PAGE,
  fullBackend,
  liveFrame,
  ME,
  REALTIME,
  renderApp,
  RISK_PROFILE,
} from '../test/utils'

const live = () =>
  fullBackend({
    '/api/v1/wells/4/realtime': REALTIME,
    '/api/v1/wells/4/risk-profile': RISK_PROFILE,
    'GET /api/v1/alerts': ALERT_PAGE,
  })

async function socket() {
  await waitFor(() => expect(FakeWebSocket.find('/ws/wells/4/live')).toBeDefined())
  const ws = FakeWebSocket.find('/ws/wells/4/live')!
  act(() => {
    ws.open()
    ws.receive({ type: 'hello', well_id: 4, wellbore_id: 41, replay: null })
  })
  return ws
}

describe('Live Well Monitor', () => {
  it('opens the drilling well and paints the REST window, then live frames', async () => {
    live()
    renderApp('/live')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Live Well Monitor' }),
    ).toBeInTheDocument()
    expect(await screen.findAllByTestId('channel-strip')).toHaveLength(8)
    expect(screen.getByTestId('latest-hookload_kn')).toHaveTextContent('903')
    const ws = await socket()
    expect(screen.getByTestId('live-connection')).toHaveTextContent('Live')
    act(() =>
      ws.receive({
        type: 'frame',
        frame: liveFrame(),
      }),
    )
    expect(screen.getByTestId('tile-bit')).toHaveTextContent('2,295.1')
    expect(screen.getByTestId('latest-torque_knm')).toHaveTextContent('13.4')
    expect(screen.getByTestId('rig-state-now')).toHaveTextContent('Drilling')
    // Look-ahead from the offset risk profile: 30 m to Tipam with its loss prior.
    expect(screen.getByTestId('look-ahead-next')).toHaveTextContent('Tipam Sandstone')
    expect(screen.getByTestId('look-ahead-distance')).toHaveTextContent('30 m TVD (prognosed ±5 m)')
    expect(screen.getByTestId('look-ahead-hazard')).toHaveTextContent(
      'Lost circulation 36% in offsets',
    )
    const loss = within(screen.getByTestId('risk-gauges'))
      .getAllByTestId('risk-gauge')
      .find((g) => g.dataset['type'] === 'LOSS')!
    expect(within(loss).getByRole('meter')).toHaveAttribute(
      'aria-valuetext',
      '31%, alert threshold 25%, steady',
    )
    expect(screen.getByTestId('dejavu-now')).toHaveTextContent('similarity 0.46 (not a probability')
    expect(screen.getByText('SYNTHETIC data')).toBeInTheDocument()
    // The well's open alerts link to the Alerts Center.
    expect(within(screen.getByTestId('live-alerts')).getAllByRole('link')[0]).toHaveAttribute(
      'href',
      '/alerts?id=8',
    )
  })

  it('badges a channel the stream flags as bad data', async () => {
    live()
    renderApp('/live?well=4')
    const ws = await socket()
    act(() =>
      ws.receive({ type: 'frame', frame: liveFrame({ quality: { spp_kpa: 'unit_jump' } }) }),
    )
    expect(screen.getByTestId('quality-spp_kpa')).toHaveTextContent('Unit changed at source?')
    expect(screen.queryByTestId('quality-torque_knm')).not.toBeInTheDocument()
  })

  it('shows the replay banner and a stale warning from the stream status', async () => {
    live()
    renderApp('/live?well=4')
    const ws = await socket()
    act(() =>
      ws.receive({
        type: 'status',
        stale: true,
        replay: {
          id: 5,
          status: 'running',
          speed: 60,
          position: 120,
          total_rows: 1918,
          data_now: null,
        },
      }),
    )
    expect(screen.getByTestId('replay-banner')).toHaveTextContent('REPLAY ×60 · row 120 of 1918')
    expect(screen.getByTestId('stale-banner')).toHaveTextContent('last received, not current')
    act(() => ws.receive({ type: 'frame', frame: liveFrame() }))
    expect(screen.queryByTestId('stale-banner')).not.toBeInTheDocument()
  })

  it('offers replay control only to roles with control_replay', async () => {
    const calls = live()
    renderApp('/live')
    const controls = await screen.findByTestId('replay-controls')
    await userEvent.selectOptions(within(controls).getByLabelText('Speed'), '300')
    await userEvent.click(within(controls).getByRole('button', { name: /Start replay/ }))
    await waitFor(() =>
      expect(
        calls.mock.calls.some(([u, i]) => String(u) === '/api/v1/replay' && i?.method === 'POST'),
      ).toBe(true),
    )
    const body = calls.mock.calls.find(
      ([u, i]) => String(u) === '/api/v1/replay' && i?.method === 'POST',
    )![1]!.body
    expect(JSON.parse(String(body))).toEqual({ well_id: 4, action: 'start', speed: 300 })
  })

  it('hides replay control from a field engineer', async () => {
    live()
    fullBackend({
      '/api/v1/wells/4/realtime': REALTIME,
      '/api/v1/wells/4/risk-profile': RISK_PROFILE,
      'GET /api/v1/alerts': ALERT_PAGE,
      '/api/v1/me': {
        status: 200,
        body: {
          ...ME.body,
          roles: ['field_engineer'],
          permissions: ['read_knowledge', 'copilot', 'read_live', 'act_alerts'],
        },
      },
    })
    renderApp('/live')
    await screen.findAllByTestId('channel-strip')
    expect(screen.queryByTestId('replay-controls')).not.toBeInTheDocument()
  })

  it('says why when the socket is refused', async () => {
    live()
    renderApp('/live')
    await waitFor(() => expect(FakeWebSocket.find('/ws/wells/4/live')).toBeDefined())
    act(() => FakeWebSocket.find('/ws/wells/4/live')!.close(4403))
    expect(await screen.findByText('Your role cannot see live data')).toBeInTheDocument()
  })
})
