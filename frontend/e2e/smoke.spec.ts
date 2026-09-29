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

test('System Status shows a ready backend', async ({ page }) => {
  const errors = trackConsoleErrors(page)
  await page.goto('/system')
  await expect(page.getByRole('heading', { name: 'System Status' })).toBeVisible()
  await expect(page.getByTestId('backend-status')).toContainText('Backend ready')
  const table = page.getByTestId('readiness-table')
  for (const name of ['postgres', 'redis', 'object_storage']) {
    await expect(table.getByRole('row', { name: new RegExp(name) })).toContainText('ok')
  }
  await expect(page.getByTestId('backend-phase')).toHaveText(/^B\d$/)
  await expect(page.getByTestId('component-list').getByRole('listitem')).toHaveCount(18)
  expect(errors).toEqual([])
})

test('every screen in the navigation loads without errors', async ({ page }) => {
  const errors = trackConsoleErrors(page)
  await page.goto('/system')
  const links = page.getByRole('navigation', { name: 'Main' }).locator('a[data-screen]')
  const count = await links.count()
  expect(count).toBe(12)
  for (let i = 0; i < count; i++) {
    const link = links.nth(i)
    const title = (await link.getAttribute('data-title')) ?? ''
    await link.click()
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
    await expect(page.getByTestId('breadcrumb-current')).toHaveText(title)
  }
  expect(errors).toEqual([])
})

test('planned screens probe the real backend and show its phase', async ({ page }) => {
  // The analytics screen is F5, but its backend (B5) already answers.
  await page.goto('/analytics')
  await expect(page.getByTestId('planned-phase')).toHaveText('Planned · frontend phase F5')
  await expect(page.getByTestId('endpoint-probes')).toContainText('200 ok')
})

test('WebSockets are proxied through nginx to the backend', async ({ page }) => {
  await page.goto('/system')
  const message = await page.evaluate(
    () =>
      new Promise<string>((resolve, reject) => {
        const ws = new WebSocket(`${location.origin.replace(/^http/, 'ws')}/ws/alerts`)
        ws.onmessage = (e) => {
          resolve(String(e.data))
          ws.close()
        }
        ws.onerror = () => reject(new Error('websocket error'))
        setTimeout(() => reject(new Error('timeout')), 5000)
      }),
  )
  expect(JSON.parse(message).type).toBe('hello')
})

test('theme and field mode persist across reloads', async ({ page }) => {
  await page.goto('/system')
  const html = page.locator('html')
  await expect(html).toHaveAttribute('data-theme', 'deep-rig')
  await page.getByTestId('theme-toggle').click() // Deep Rig → Daylight Field
  await expect(html).toHaveAttribute('data-theme', 'daylight')
  await page.getByTestId('theme-toggle').click() // → Command Blue
  await expect(html).toHaveAttribute('data-theme', 'command-blue')
  await page.getByTestId('mode-toggle').click()
  await expect(html).toHaveAttribute('data-mode', 'field')
  await page.reload()
  await expect(html).toHaveAttribute('data-theme', 'command-blue')
  await expect(html).toHaveAttribute('data-mode', 'field')
  await expect(
    page.getByRole('navigation', { name: 'Main' }).locator('a[data-screen="admin"]'),
  ).toHaveCount(0)
})

test('unknown routes show the not-found page', async ({ page }) => {
  await page.goto('/no-such-page')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
})

test('no horizontal scroll at phone width', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  for (const path of ['/', '/system', '/map', '/documents', '/correlation']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow, path).toBeLessThanOrEqual(0)
  }
})
