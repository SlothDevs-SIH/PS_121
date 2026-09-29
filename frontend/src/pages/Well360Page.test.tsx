import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import {
  DOCUMENTS,
  eventDetail,
  fullBackend,
  LESSON,
  OFFSETS,
  renderApp,
  RISK_PROFILE,
  TIMELINE,
  TRAJECTORY_1,
  wellDetail,
} from '../test/utils'

const EV_REF = { document_id: 7, page_no: 1, span_ids: [102], filename: 'WCR.pdf', doc_type: 'WCR' }

function detail() {
  const base = wellDetail(1).body
  return {
    status: 200,
    body: {
      ...base,
      aliases: ['SYN ASM 1'],
      data_quality: {
        score: 0.8,
        checks: [
          { name: 'surveys', ok: true, detail: 'measured surveys' },
          { name: 'datum', ok: false, detail: 'RKB elevation assumed' },
        ],
      },
      formation_tops: [
        {
          formation: 'Tipam Sandstone',
          strat_order: 4,
          top_md_m: 2280,
          top_tvd_m: 2270,
          top_tvdss_m: 2150,
        },
      ],
      casing: [
        {
          id: 36,
          od_in: 9.625,
          hole_size_in: 12.25,
          shoe_md_m: 2360,
          shoe_tvd_m: 2350,
          shoe_tvdss_m: 2230,
          planned_shoe_md_m: null,
          grade: null,
          weight_ppf: null,
          confidence: 0.95,
          verified: false,
          evidence: [EV_REF],
          cement: [
            {
              id: 36,
              toc_md_m: 700,
              toc_tvdss_m: 580,
              returns: 'partial',
              slurry_density_sg: 1.9,
              volume_m3: null,
              bond_quality: null,
              remedial: null,
              confidence: 0.95,
              verified: false,
              evidence: [EV_REF],
            },
          ],
        },
      ],
      mud: [
        {
          id: 5,
          md_from_m: 800,
          md_to_m: 2360,
          tvdss_from_m: 680,
          tvdss_to_m: 2230,
          hole_size_in: 12.25,
          mud_type: 'water-based',
          mw_sg: 1.18,
          ecd_sg: null,
          confidence: 0.95,
          verified: true,
          evidence: [EV_REF],
        },
      ],
      lessons: [LESSON],
    },
  }
}

function backend() {
  return fullBackend({
    '/api/v1/wells/1': detail(),
    '/api/v1/wells/1/events/timeline': TIMELINE,
    '/api/v1/wells/1/trajectory': TRAJECTORY_1,
    '/api/v1/wells/1/offsets': { status: 200, body: { ...OFFSETS.body, well_id: 1, offsets: [] } },
    '/api/v1/events/11': eventDetail(11),
    'GET /api/v1/documents': DOCUMENTS,
    '/api/v1/wells/1/risk-profile': RISK_PROFILE,
  })
}

describe('Well 360', () => {
  it('shows the well, its data-quality reasons and cited casing and mud', async () => {
    backend()
    renderApp('/wells/1')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Well 360: SYN-ASM-01' }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('well-facts')).toHaveTextContent('also written SYN ASM 1')
    const dq = screen.getByTestId('data-quality')
    expect(dq).toHaveTextContent('Data quality 80%')
    expect(dq).toHaveTextContent('RKB elevation assumed')
    const casing = await screen.findByTestId('casing-table')
    expect(casing).toHaveTextContent('9⅝″')
    expect(casing).toHaveTextContent('partial returns')
    expect(within(casing).getAllByTestId('evidence-link').length).toBeGreaterThan(0)
    // Extracted, unverified values are dashed; the verified mud weight is not.
    expect(within(casing).getByText('9⅝″').closest('[data-verified]')).toHaveAttribute(
      'data-verified',
      'false',
    )
    expect(screen.getByTestId('mud-table').querySelector('[data-verified="true"]')).not.toBeNull()
    expect(screen.getByTestId('well-schematic')).toBeInTheDocument()
    expect(screen.getByTestId('correlate-link')).toHaveAttribute('href', '/correlation?wells=1')
  })

  it('lists events by date or depth and opens one with its actions', async () => {
    backend()
    renderApp('/wells/1?tab=events')
    const rows = await screen.findAllByTestId('event-row')
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining('Lost circulation'),
      expect.stringContaining('Stuck pipe'),
    ])
    await userEvent.click(rows[0]!)
    const panel = await screen.findByTestId('event-detail')
    expect(panel).toHaveTextContent('Loss rate')
    expect(panel).toHaveTextContent('Pumped fine LCM pill')
    expect(panel).toHaveTextContent('Go coarse sooner in Tipam.')
    await userEvent.click(screen.getByRole('radio', { name: 'By depth' }))
    expect(screen.getByTestId('events-strip')).toHaveAttribute('aria-label', 'Events by depth')
    expect(screen.getByTestId('npt-operations')).toHaveTextContent('Partial losses, pumped LCM')
  })

  it('draws the trajectory in 3D and switches camera presets', async () => {
    backend()
    renderApp('/wells/1?tab=trajectory')
    const view = await screen.findByTestId('trajectory-3d')
    expect(view).toHaveAttribute('data-pitch', '28')
    expect(screen.getByTestId('path-subject')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: 'Plan' }))
    expect(view).toHaveAttribute('data-pitch', '90')
    view.focus()
    await userEvent.keyboard('{ArrowDown}')
    expect(view).toHaveAttribute('data-pitch', '85')
    expect(screen.getAllByTestId('trajectory-event').length).toBe(2)
  })

  it('has lessons and documents tabs, and keyboard-navigable tabs', async () => {
    backend()
    renderApp('/wells/1')
    const tab = await screen.findByRole('tab', { name: /Overview/ })
    tab.focus()
    await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}{ArrowRight}')
    expect(screen.getByRole('tab', { name: /Lessons/ })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByTestId('lesson-card')).toHaveTextContent('Coarse LCM worked')
    await userEvent.click(screen.getByRole('tab', { name: /Documents/ }))
    expect(await screen.findByTestId('well-documents')).toHaveTextContent('SYN-ASM-01_DDR.pdf')
  })

  it('draws the offset prior by depth with prognosed intervals and ledger links', async () => {
    backend()
    renderApp('/wells/1?tab=risk')
    const curve = await screen.findByTestId('risk-curve')
    expect(
      within(curve).getByRole('img', { name: /Tight hole peaks at 46% in Girujan Clay/ }),
    ).toBeInTheDocument()
    expect(within(curve).getByText(/prognosed from offsets/)).toBeInTheDocument()
    expect(within(curve).queryByTestId('risk-bit')).toBeNull() // TD is marked on drilling wells only
    // Legend toggles focus on one series
    const loss = within(curve).getByRole('button', { name: /Lost circulation/ })
    await userEvent.click(loss)
    expect(loss).toHaveAttribute('aria-pressed', 'true')
    const peaks = screen.getByTestId('risk-peaks')
    expect(within(peaks).getByText(/What worked for lost circulation/)).toHaveAttribute(
      'href',
      '/ledger?type=LOSS&fm=Tipam%20Sandstone',
    )
    expect(within(peaks).getByText('(prognosed)')).toBeInTheDocument()
    // The numbers are in a table as well as on the chart
    const table = screen.getByTestId('risk-table')
    expect(within(table).getByText(/prognosed ±4.6 m/)).toBeInTheDocument()
    expect(within(table).getByRole('row', { name: /Tipam Sandstone/ })).toHaveTextContent('36%')
  })

  it('says plainly when the well does not exist', async () => {
    fullBackend()
    renderApp('/wells/999')
    expect(await screen.findByRole('alert')).toHaveTextContent('There is no well with id 999.')
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Pick a well on the map' })).toBeInTheDocument(),
    )
  })
})
