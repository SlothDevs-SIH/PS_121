import { expect, test, type Page } from '@playwright/test'

// Planned screens deliberately probe skeleton endpoints that answer 501; the browser logs each one.
const EXPECTED_501 = /Failed to load resource: .* 501 \(Not Implemented\)/

/** Fail any test that logs a console error (this also catches CSP violations). */
function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !EXPECTED_501.test(msg.text())) errors.push(msg.text())
  })
  page.on('pageerror', (err) => errors.push(err.message))
  return errors
}

test('home redirects to System Status and shows a ready backend', async ({ page }) => {
  const errors = trackConsoleErrors(page)
  await page.goto('/')
  await expect(page).toHaveURL(/\/system$/)
  await expect(page.getByRole('heading', { name: 'System Status' })).toBeVisible()
  await expect(page.getByTestId('backend-status')).toContainText('Backend ready')
  const table = page.getByTestId('readiness-table')
  for (const name of ['postgres', 'redis', 'object_storage']) {
    await expect(table.getByRole('row', { name: new RegExp(name) })).toContainText('ok')
  }
  await expect(page.getByTestId('backend-phase')).toHaveText('B0')
  await expect(page.getByTestId('component-list').getByRole('listitem')).toHaveCount(16)
  expect(errors).toEqual([])
})

test('every screen in the navigation loads without errors', async ({ page }) => {
  const errors = trackConsoleErrors(page)
  await page.goto('/system')
  const links = page.getByRole('navigation', { name: 'Main' }).getByRole('link')
  const count = await links.count()
  expect(count).toBe(11)
  for (let i = 0; i < count; i++) {
    const link = links.nth(i)
    const title = (await link.locator('span').first().textContent()) ?? ''
    await link.click()
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  }
  expect(errors).toEqual([])
})

test('planned screens probe the real backend and show its phase', async ({ page }) => {
  await page.goto('/map')
  await expect(page.getByTestId('planned-phase')).toHaveText('Planned · frontend phase F1')
  await expect(page.getByTestId('endpoint-probes').getByText('501 · backend phase B1')).toHaveCount(
    2,
  )
  await page.goto('/ledger')
  await expect(page.getByTestId('endpoint-probes')).toContainText('501 · backend phase B3')
})

test('WebSockets are proxied through nginx to the backend', async ({ page }) => {
  await page.goto('/system')
  const result = await page.evaluate(
    () =>
      new Promise<{ message: string; code: number }>((resolve, reject) => {
        const ws = new WebSocket(`${location.origin.replace(/^http/, 'ws')}/ws/alerts`)
        let message = ''
        ws.onmessage = (e) => (message = String(e.data))
        ws.onclose = (e) => resolve({ message, code: e.code })
        ws.onerror = () => reject(new Error('websocket error'))
        setTimeout(() => reject(new Error('timeout')), 5000)
      }),
  )
  expect(result.code).toBe(4501)
  expect(JSON.parse(result.message).error.code).toBe('not_implemented')
})

test('theme and field mode persist across reloads', async ({ page }) => {
  await page.goto('/system')
  const html = page.locator('html')
  await page.getByTestId('theme-toggle').click() // system → light
  await page.getByTestId('theme-toggle').click() // light → dark
  await expect(html).toHaveAttribute('data-theme', 'dark')
  await page.getByTestId('mode-toggle').click()
  await expect(html).toHaveAttribute('data-mode', 'field')
  await page.reload()
  await expect(html).toHaveAttribute('data-theme', 'dark')
  await expect(html).toHaveAttribute('data-mode', 'field')
  await expect(
    page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: /Admin/ }),
  ).toHaveCount(0)
})

test('unknown routes show the not-found page', async ({ page }) => {
  await page.goto('/no-such-page')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
})

test('no horizontal scroll at phone width', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  for (const path of ['/system', '/map', '/correlation']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow, path).toBeLessThanOrEqual(0)
  }
})
