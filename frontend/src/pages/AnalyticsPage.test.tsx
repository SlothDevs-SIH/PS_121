import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'

import { Providers } from '../app/providers'
import { makeQueryClient } from '../app/queryClient'
import { routes } from '../app/router'
import { useUiStore } from '../stores/ui'
import { fullBackend, ME } from '../test/utils'

const FORMATIONS = {
  status: 200,
  body: [
    { id: 3, name: 'Barail', synonyms: [], strat_order: 3, basin: 'Assam' },
    { id: 4, name: 'Tipam Sandstone', synonyms: [], strat_order: 4, basin: 'Assam' },
  ],
}

const nptRow = (key: string, npt_hours: number, events: number, share = 0) => ({
  key,
  events,
  wells: Math.min(events, 4),
  npt_hours,
  share_of_npt: share,
  median_npt_hours: npt_hours / events,
})

function npt(group_by: string, rows: ReturnType<typeof nptRow>[], extra = {}) {
  return {
    status: 200,
    body: {
      group_by,
      rows,
      total_events: rows.reduce((a, r) => a + r.events, 0),
      total_npt_hours: rows.reduce((a, r) => a + r.npt_hours, 0),
      events_without_npt: 2,
      synthetic: true,
      ...extra,
    },
  }
}

const RECURRING = {
  status: 200,
  body: {
    min_wells: 3,
    across_wells: [
      {
        event_type: 'LOSS',
        formation: 'Barail',
        wells: 5,
        events: 9,
        npt_hours: 212.5,
        first_year: 2011,
        last_year: 2019,
        event_ids: [1, 2, 3],
      },
    ],
    within_wells: [
      { well_id: 2, well_name: 'SYN-ASM-02', event_type: 'STUCK', events: 3, npt_hours: 40 },
    ],
    synthetic: true,
  },
}

const PROP = (k: number, n: number, mean: number) => ({
  k,
  n,
  mean,
  ci90_low: mean - 0.2,
  ci90_high: mean + 0.1,
})

const ALERT_QUALITY = {
  status: 200,
  body: {
    alerts: 12,
    by_type: { KICK: 3, LOSS: 9 },
    by_source: { model: 8, dejavu: 4 },
    by_severity: { critical: 3, warning: 9 },
    by_status: { new: 4, ack: 8 },
    feedback: { useful: 6, false_alarm: 2 },
    precision: PROP(6, 8, 0.7),
    acknowledged: PROP(8, 12, 0.64),
    median_minutes_to_ack: 2.5,
    data_hours: 30,
    alerts_per_12h: 4.8,
    note: 'Precision counts engineers’ verdicts (latest per alert).',
  },
}

function analyticsBackend(extra = {}) {
  return fullBackend({
    '/api/v1/formations': FORMATIONS,
    '/api/v1/analytics/npt?group_by=event_type': npt('event_type', [
      nptRow('LOSS', 300, 10, 0.6),
      nptRow('STUCK', 200, 5, 0.4),
    ]),
    '/api/v1/analytics/npt?group_by=formation': npt('formation', [
      nptRow('Barail', 350, 9),
      nptRow('unknown', 100, 4),
      nptRow('Tipam Sandstone', 50, 2),
    ]),
    '/api/v1/analytics/npt?group_by=field': npt('field', [
      nptRow('Upper Assam (synthetic)', 500, 15),
    ]),
    '/api/v1/analytics/npt?group_by=year&formation=Barail': npt('year', [
      nptRow('2019', 250, 6),
      nptRow('2016', 100, 3),
    ]),
    '/api/v1/analytics/npt?group_by=year&formation=Tipam+Sandstone': npt('year', [
      nptRow('2017', 50, 2),
    ]),
    // Every other breakdown (the year chart, filtered views) reads the same year rows.
    '/api/v1/analytics/npt': npt('year', [nptRow('2019', 300, 8), nptRow('2016', 200, 7)]),
    '/api/v1/analytics/recurring': RECURRING,
    '/api/v1/analytics/alerts': ALERT_QUALITY,
    ...extra,
  })
}

function renderAt(path: string) {
  const client = makeQueryClient()
  client.setDefaultOptions({ queries: { retry: false, refetchInterval: false } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
  )
  return router
}

describe('Analytics', () => {
  it('shows NPT charts, the heatmap, recurring problems and alert statistics', async () => {
    analyticsBackend()
    renderAt('/analytics')
    expect(await screen.findByRole('heading', { level: 1, name: 'Analytics' })).toBeInTheDocument()

    // NPT by problem: labelled bars in the API's order, each value as text.
    const byType = await screen.findByTestId('npt-chart-event_type')
    const bars = within(byType).getAllByTestId('bar-row')
    expect(bars.map((b) => b.dataset.key)).toEqual(['LOSS', 'STUCK'])
    expect(bars[0]).toHaveTextContent('Lost circulation')
    expect(bars[0]).toHaveTextContent('300.0 h')
    expect(await screen.findByTestId('npt-chart-formation')).toHaveTextContent('not recorded')
    expect(await screen.findByTestId('npt-chart-field')).toHaveTextContent('Upper Assam')
    const years = await screen.findByTestId('npt-chart-year')
    expect(within(years).getAllByTestId('column')).toHaveLength(2)
    expect(screen.getByTestId('kpi-npt')).toBeInTheDocument()
    expect(screen.getAllByText(/2 of \d+ events have no recorded NPT/).length).toBeGreaterThan(0)

    // Formation × year: known formations only, the year gap filled, every cell stated.
    const heat = await screen.findByTestId('npt-heatmap')
    const cells = within(heat).getAllByTestId('heat-cell')
    expect(cells).toHaveLength(2 * 4) // Barail, Tipam × 2016-2019
    const barail2019 = cells.find((c) => c.dataset.key === 'Barail|2019')!
    expect(barail2019.dataset.step).toBe('4')
    expect(barail2019).toHaveTextContent('250')
    expect(cells.find((c) => c.dataset.key === 'Barail|2018')!.dataset.step).toBe('-1')

    // Recurring problems with links to their evidence.
    const across = await screen.findByTestId('recurring-across')
    expect(within(across).getByText('Lost circulation')).toBeInTheDocument()
    expect(within(across).getByText('2011–2019')).toBeInTheDocument()
    expect(within(across).getByRole('link', { name: 'What worked' })).toHaveAttribute(
      'href',
      '/ledger?type=LOSS&fm=Barail',
    )
    expect(screen.getByRole('link', { name: 'SYN-ASM-02' })).toHaveAttribute(
      'href',
      '/wells/2?tab=events',
    )

    // Alert statistics: precision with its interval and sample size, alerts per shift.
    const stats = await screen.findByTestId('alert-stats')
    expect(within(stats).getByTestId('rate-precision')).toHaveTextContent('70%')
    expect(within(stats).getByTestId('rate-precision')).toHaveTextContent('6 of 8')
    expect(within(stats).getByTestId('alerts-per-shift')).toHaveTextContent('4.80 per 12 h shift')
    expect(within(stats).getByText('False alarm')).toBeInTheDocument()
    expect(screen.getAllByTestId('synthetic-badge').length).toBeGreaterThan(0)
  })

  it('keeps filters in the URL and refetches with them', async () => {
    const fetchMock = analyticsBackend()
    const router = renderAt('/analytics?min=4')
    await screen.findByTestId('npt-chart-event_type')
    expect(screen.getByTestId('recurring-min-wells')).toHaveValue('4')

    await userEvent.selectOptions(screen.getByTestId('analytics-type'), 'LOSS')
    await screen.findByRole('option', { name: 'Barail' })
    await userEvent.selectOptions(screen.getByTestId('analytics-formation'), 'Barail')
    await userEvent.selectOptions(screen.getByTestId('recurring-min-wells'), '5')

    const search = new URLSearchParams(router.state.location.search)
    expect(search.get('type')).toBe('LOSS')
    expect(search.get('fm')).toBe('Barail')
    expect(search.get('min')).toBe('5')
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]))
      expect(urls).toContain(
        '/api/v1/analytics/npt?group_by=event_type&event_type=LOSS&formation=Barail',
      )
      expect(urls).toContain('/api/v1/analytics/recurring?min_wells=5')
    })

    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(new URLSearchParams(router.state.location.search).has('type')).toBe(false)
  })

  it('reads its filters from a shared link', async () => {
    analyticsBackend()
    renderAt('/analytics?type=STUCK&fm=Tipam+Sandstone')
    await screen.findByRole('option', { name: 'Tipam Sandstone' })
    expect(screen.getByTestId('analytics-type')).toHaveValue('STUCK')
    expect(screen.getByTestId('analytics-formation')).toHaveValue('Tipam Sandstone')
    expect(
      await screen.findByRole('heading', { level: 2, name: /Stuck pipe in Tipam Sandstone/ }),
    ).toBeInTheDocument()
  })

  it('explains empty results, the well-type filter and roles without live alerts', async () => {
    useUiStore.setState({ wellType: 'gas' })
    analyticsBackend({
      '/api/v1/me': {
        status: 200,
        body: {
          ...ME.body,
          roles: ['drilling_engineer'],
          permissions: ['read_knowledge', 'copilot', 'read_risk'],
        },
      },
      '/api/v1/analytics/npt?group_by=event_type': npt('event_type', []),
      '/api/v1/analytics/recurring': {
        status: 200,
        body: { ...RECURRING.body, across_wells: [], within_wells: [] },
      },
    })
    renderAt('/analytics')
    expect(await screen.findByTestId('npt-empty')).toHaveTextContent('No events match')
    expect(screen.getByTestId('analytics-well-type-note')).toHaveTextContent('gas wells filter')
    expect(await screen.findByTestId('recurring-empty')).toBeInTheDocument()
    expect(await screen.findByTestId('alert-stats-denied')).toBeInTheDocument()
  })

  it('shows the backend error with its request id', async () => {
    analyticsBackend({
      '/api/v1/analytics/recurring': {
        status: 500,
        body: { error: { code: 'internal', message: 'boom', details: {}, request_id: 'req-42' } },
      },
    })
    renderAt('/analytics')
    const recurring = await screen.findByTestId('recurring')
    expect(await within(recurring).findByRole('alert')).toHaveTextContent('req-42')
  })
})
