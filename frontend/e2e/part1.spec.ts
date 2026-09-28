import { expect, test } from '@playwright/test'

import { makePdf } from './pdf.ts'

// Needs the seeded synthetic field (`make seed`), like the demo.

test('well map: offsets react to the radius and are shareable via the URL', async ({ page }) => {
  await page.goto('/map?well=')
  await expect(page.getByRole('heading', { name: 'Well Map' })).toBeVisible()
  await expect(page.getByTestId('synthetic-badge')).toBeVisible()
  await page.getByLabel('Active well').selectOption({ label: 'SYN-ASM-01 (completed)' })
  await expect(page).toHaveURL(/well=\d+/)
  const count = page.getByTestId('offset-count')
  await expect(count).toContainText('within 5 km')
  const before = Number((await count.textContent())?.split(' ')[0])

  const slider = page.getByLabel(/Radius/)
  await slider.focus()
  await page.keyboard.press('End')
  await expect(page.getByTestId('radius-value')).toHaveText('20')
  await expect(page).toHaveURL(/r=20/)
  await expect(count).toContainText('within 20 km')
  const after = Number((await count.textContent())?.split(' ')[0])
  expect(after).toBeGreaterThanOrEqual(before)
  expect(after).toBeGreaterThan(0)

  // Leaflet drew the wells as vector markers (no image assets, CSP-safe).
  await expect(page.locator('.leaflet-interactive').first()).toBeVisible()
  const firstDistance = page
    .getByTestId('offset-table')
    .locator('tbody tr')
    .first()
    .locator('td')
    .nth(1)
  await expect(firstDistance).toHaveText(/\d+( m| km)$/)
})

test('units toggle switches depth labels to oilfield units', async ({ page }) => {
  await page.goto('/map')
  await expect(page.getByTestId('active-well-summary')).toContainText(' m MD')
  await page.getByTestId('units-toggle').click()
  await expect(page.getByTestId('active-well-summary')).toContainText(' ft MD')
})

test('upload → OCR/text extraction → evidence viewer with highlighted lines', async ({ page }) => {
  const nonce = `e2e-${Date.now()}`
  const pdf = makePdf([
    'DAILY DRILLING REPORT',
    'SYNTHETIC DATA - NOT OIL INDIA DATA',
    'Well: SYN-ASM-01    Rig: Rig SYN-1    Report No: 77    Date: 2021-03-04',
    `Browser test ${nonce}`,
  ])
  await page.goto('/ingest')
  await page
    .getByTestId('file-input')
    .setInputFiles({ name: `${nonce}.pdf`, mimeType: 'application/pdf', buffer: pdf })
  await expect(page.getByTestId('upload-results')).toContainText('queued')

  const row = page.getByTestId('documents-table').locator('tr', { hasText: `${nonce}.pdf` })
  await expect(row).toContainText('processed', { timeout: 60_000 })
  await expect(row).toContainText('SYN-ASM-01')
  await expect(row).toContainText('2021-03-04')

  await row.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText(`${nonce}.pdf`)
  await expect(dialog.getByRole('img')).toBeVisible()
  const line = dialog.getByRole('button', { name: /Line 1: DAILY DRILLING REPORT/ })
  await line.click()
  await expect(line).toHaveAttribute('data-highlighted', 'true')
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
})

test('runtime config and CSP are served by the web server', async ({ request }) => {
  const cfg = await request.get('/config.json')
  expect(cfg.ok()).toBe(true)
  expect(await cfg.json()).toEqual({ mapTileUrl: '', mapTileAttribution: '' })
  const res = await request.get('/map')
  expect(res.headers()['content-security-policy']).toContain("img-src 'self' data: blob:")
})
