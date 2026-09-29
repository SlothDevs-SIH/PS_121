import { expect, test, type Page } from '@playwright/test'

// Part 2: design system, shell, MapLibre, Documents Library, Dashboard. Needs the seeded
// synthetic field with extraction and indexing done (`seed --wait` in CI).

function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  page.on('pageerror', (err) => errors.push(err.message))
  return errors
}

async function kpiValue(page: Page, id: string): Promise<number> {
  const el = page.getByTestId(id).locator('[data-value]')
  await expect(el).toBeVisible()
  return Number(await el.getAttribute('data-value'))
}

test('dashboard: live KPIs, a WebGL map under the strict CSP, extracted events', async ({
  page,
}) => {
  const errors = trackConsoleErrors(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible()
  expect(await kpiValue(page, 'kpi-wells')).toBeGreaterThan(0)
  expect(await kpiValue(page, 'kpi-events')).toBeGreaterThan(0)
  await expect(page.getByTestId('kpi-documents')).toContainText('/')
  await expect(page.getByTestId('recent-events').getByRole('listitem').first()).toBeVisible()
  await expect(page.getByText(/Nothing here is simulated/)).toBeVisible()
  // MapLibre rendered wells: its worker came from our own origin (no blob: under the CSP).
  await expect(
    page.getByTestId('dashboard-map').locator('.well-marker, .cluster-marker').first(),
  ).toBeVisible({ timeout: 15_000 })
  expect(errors).toEqual([])
})

test('well-type switcher filters the dashboard and sidebar links open the map', async ({
  page,
}) => {
  await page.goto('/')
  const all = await kpiValue(page, 'kpi-wells')
  await page.getByTestId('well-type-switcher').first().getByRole('radio', { name: 'Gas' }).click()
  await expect(page.getByTestId('kpi-wells')).toContainText('Gas wells')
  await expect.poll(() => kpiValue(page, 'kpi-wells')).toBeLessThan(all)
  await page.reload()
  await expect(page.getByTestId('kpi-wells')).toContainText('Gas wells') // remembered
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: /Oil wells/ })
    .click()
  await expect(page).toHaveURL(/\/map\?type=oil/)
  await expect(
    page.getByTestId('well-type-switcher').first().getByRole('radio', { name: 'Oil' }),
  ).toHaveAttribute('aria-checked', 'true')
})

test('command palette jumps to a well on the map', async ({ page }) => {
  await page.goto('/system')
  await page.keyboard.press('Control+k')
  const dialog = page.getByRole('dialog', { name: 'Command palette' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('combobox').fill('SYN-ASM-07')
  const well = dialog.locator('[data-kind="well"]', { hasText: 'SYN-ASM-07' })
  await expect(well).toBeVisible()
  await well.click()
  await expect(dialog).toBeHidden()
  await expect(page).toHaveURL(/\/map\?well=\d+/)
  await expect(page.getByLabel('Active well')).toHaveValue(/\d+/)
  await expect(page.getByLabel('Active well').locator('option:checked')).toHaveText(/SYN-ASM-07/)
})

test('map explorer: markers, fly-to selection and legend toggles', async ({ page }) => {
  const errors = trackConsoleErrors(page)
  await page.goto('/map?r=20')
  await expect(page.getByRole('heading', { name: 'Map Explorer' })).toBeVisible()
  await expect(page.getByTestId('app-shell')).toHaveAttribute('data-sidebar', 'rail')
  const markers = page.getByTestId('map-panel').locator('.well-marker, .cluster-marker')
  await expect(markers.first()).toBeVisible({ timeout: 15_000 })
  const offset = page.locator('.well-marker[data-role="offset"]').first()
  await expect(offset).toBeAttached()
  const id = await offset.getAttribute('data-well-id')
  await offset.dispatchEvent('click')
  await expect(page).toHaveURL(new RegExp(`well=${id}`))
  await expect(page.getByLabel('Active well')).toHaveValue(id ?? '')
  const before = await page.locator('.well-marker').count()
  await page.getByRole('button', { name: 'Hide oil wells' }).click()
  await expect.poll(() => page.locator('.well-marker').count()).toBeLessThan(before)
  expect(errors).toEqual([])
})

test('documents library: cards with pipeline stages, list view, viewer deep link', async ({
  page,
}) => {
  await page.goto('/documents')
  await expect(page.getByRole('heading', { level: 1, name: 'Documents Library' })).toBeVisible()
  const card = page.getByTestId('document-card').first()
  await expect(card).toBeVisible()
  await expect(card.getByLabel('Uploaded: done')).toBeVisible()
  await expect(page.getByTestId('stage-totals')).toContainText('Indexed')
  await page.getByRole('radio', { name: 'WCR' }).click()
  await expect(page.getByTestId('document-card').first()).toContainText('WCR')
  await page.getByRole('radio', { name: 'List' }).click()
  const row = page.getByTestId('documents-table').locator('tbody tr').first()
  await expect(row).toContainText('WCR')
  await row.click()
  await expect(page).toHaveURL(/doc=\d+/)
  await expect(page.getByRole('dialog')).toBeVisible()
})

test('sidebar collapses to a rail and remembers it', async ({ page, viewport }) => {
  test.skip((viewport?.width ?? 0) < 1024, 'below lg the rail is imposed, no toggle')
  await page.goto('/system')
  const shell = page.getByTestId('app-shell')
  await expect(shell).toHaveAttribute('data-sidebar', 'full')
  await page.getByTestId('sidebar-toggle').click()
  await expect(shell).toHaveAttribute('data-sidebar', 'rail')
  await page.reload()
  await expect(shell).toHaveAttribute('data-sidebar', 'rail')
  await page.getByRole('button', { name: 'Expand sidebar' }).click()
  await expect(shell).toHaveAttribute('data-sidebar', 'full')
})
