import { AxeBuilder } from '@axe-core/playwright'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// Part 4 (F3): Mitigation Ledger, risk curves on Well 360 / the map panel / the correlation
// hazard strip, and WCAG 2.2 AA checks on them. Needs the seeded field (`seed --wait` in CI).

interface WellRow {
  id: number
  name: string
  status: string
}

async function wells(request: APIRequestContext): Promise<WellRow[]> {
  const r = await request.get('/api/v1/wells?limit=500')
  expect(r.ok()).toBe(true)
  return (await r.json()).items as WellRow[]
}

function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => msg.type() === 'error' && errors.push(msg.text()))
  page.on('pageerror', (err) => errors.push(err.message))
  return errors
}

test('mitigation ledger: the planted ranking, in the API order, with cases and pages', async ({
  page,
  request,
}) => {
  const errors = trackConsoleErrors(page)
  const api = await (await request.get('/api/v1/ledger?event_type=LOSS')).json()
  const ranked = api.ranked as { action_code: string; posterior_mean: number }[]
  expect(ranked.length).toBeGreaterThan(0)
  // The backend ranks by posterior mean; the screen must show exactly that order.
  const means = ranked.map((e) => e.posterior_mean)
  expect([...means].sort((a, b) => b - a)).toEqual(means)

  await page.goto('/ledger?type=LOSS')
  await expect(page.getByRole('heading', { level: 1, name: 'Mitigation Ledger' })).toBeVisible()
  await expect(page.getByTestId('ledger-caveat')).toContainText('not causal')
  const rows = page.getByTestId('ledger-ranked').getByTestId('ledger-action')
  await expect(rows).toHaveCount(ranked.length)
  expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-code')))).toEqual(
    ranked.map((e) => e.action_code),
  )
  await expect(page.getByTestId('interval-bar').first()).toHaveAttribute(
    'aria-label',
    /credible interval/,
  )
  // Expand the top action: its cases link to wells and to report pages.
  await rows.first().click()
  const cases = page.getByTestId('ledger-cases')
  await expect(cases.getByRole('link').first()).toHaveAttribute('href', /\/wells\/\d+/)
  await expect(cases.getByRole('button', { name: /p\.\d+/ }).first()).toBeVisible()
  // Another problem: the URL and the data follow.
  await page.getByTestId('ledger-type').selectOption('STUCK')
  await expect(page).toHaveURL(/type=STUCK/)
  await expect(page.getByTestId('ledger-scope')).toContainText('Stuck pipe')
  expect(errors).toEqual([])
})

test('risk curves: well 360, map panel and the correlation hazard strip', async ({
  page,
  request,
}) => {
  const errors = trackConsoleErrors(page)
  const drilling = (await wells(request)).find((w) => w.status === 'drilling')!
  const profile = await (await request.get(`/api/v1/wells/${drilling.id}/risk-profile`)).json()
  expect(profile.intervals.some((iv: { prognosed: boolean }) => iv.prognosed)).toBe(true)

  await page.goto(`/wells/${drilling.id}?tab=risk`)
  const curve = page.getByTestId('risk-curve')
  await expect(curve).toBeVisible()
  await expect(curve.getByRole('img').first()).toHaveAttribute('aria-label', /peaks at \d+%/)
  await expect(curve.getByTestId('risk-bit')).toBeVisible() // a drilling well's TD
  await expect(curve).toContainText('prognosed from offsets')
  const toLedger = page.getByTestId('risk-peaks').getByRole('link').first()
  await toLedger.click()
  await expect(page).toHaveURL(/\/ledger\?type=\w+&fm=/)
  await expect(page.getByTestId('ledger-caveat')).toBeVisible()

  await page.goto(`/map?well=${drilling.id}`)
  await expect(page.getByTestId('risk-curve')).toBeVisible()

  await page.goto(`/correlation?wells=${drilling.id}`)
  const strip = page.getByTestId('hazard-strip')
  await expect(strip).toHaveCount(1)
  await expect(strip.locator('rect').first()).toBeVisible()
  expect(errors).toEqual([])
})

for (const theme of ['deep-rig', 'daylight', 'command-blue']) {
  test(`F3 views pass automated WCAG 2.2 AA checks (${theme})`, async ({ page, request }) => {
    await page.addInitScript((t) => window.localStorage.setItem('smriti.theme', t), theme)
    const drilling = (await wells(request)).find((w) => w.status === 'drilling')!
    const views: [string, string, (() => Promise<void>)?][] = [
      [
        '/ledger?type=LOSS',
        'ledger-ranked',
        async () => page.getByTestId('ledger-action').first().click(),
      ],
      [`/wells/${drilling.id}?tab=risk`, 'risk-curve'],
    ]
    for (const [url, testId, act] of views) {
      await page.goto(url)
      await expect(page.getByTestId(testId).first()).toBeVisible()
      if (act) await act()
      const result = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
        .analyze()
      expect(
        result.violations.map(
          (v) =>
            `${url}: ${v.id} ${v.nodes
              .map((n) => n.target.join(' '))
              .slice(0, 3)
              .join(' | ')}`,
        ),
      ).toEqual([])
    }
  })
}
