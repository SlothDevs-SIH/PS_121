import { AxeBuilder } from '@axe-core/playwright'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// Part 5 (F4): Live Well Monitor, Alerts Center, live toasts, against the running stack.
// A real replay of the seeded drilling well drives the UI: nothing is mocked here.

interface WellRow {
  id: number
  name: string
  status: string
}

interface ReplayRow {
  id: number
  well_id: number
  status: string
}

test.describe.configure({ mode: 'serial' })

async function drillingWell(request: APIRequestContext): Promise<WellRow> {
  const r = await request.get('/api/v1/wells?status=drilling&limit=5')
  expect(r.ok()).toBe(true)
  return ((await r.json()).items as WellRow[])[0]!
}

async function waitForReplayIdle(request: APIRequestContext, wellId: number, ms = 240_000) {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    const rows = (await (await request.get('/api/v1/replay')).json()) as ReplayRow[]
    const mine = rows.filter((r) => r.well_id === wellId)
    if (!mine.some((r) => ['pending', 'running', 'paused'].includes(r.status))) return
    await new Promise((res) => setTimeout(res, 2000))
  }
  throw new Error('replay did not finish')
}

function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => msg.type() === 'error' && errors.push(msg.text()))
  page.on('pageerror', (err) => errors.push(err.message))
  return errors
}

test('replay → live monitor: frames stream in and a new alert toasts within 5 s', async ({
  page,
  request,
}, info) => {
  // Replays and acknowledgements change shared state: one project drives them.
  test.skip(info.project.name !== 'desktop', 'stateful: runs once, in the desktop project')
  test.setTimeout(300_000)
  const errors = trackConsoleErrors(page)
  const well = await drillingWell(request)
  await waitForReplayIdle(request, well.id)
  await page.goto(`/live?well=${well.id}`)
  await expect(page.getByRole('heading', { level: 1, name: 'Live Well Monitor' })).toBeVisible()
  await expect(page.getByTestId('live-connection')).toContainText('Live', { timeout: 15_000 })
  await expect(page.getByTestId('synthetic-badge').first()).toBeVisible()

  const controls = page.getByTestId('replay-controls')
  await controls.getByLabel('Speed').selectOption('1500')
  await controls.getByRole('button', { name: /Start replay/ }).click()
  await expect(page.getByTestId('replay-banner')).toContainText('REPLAY ×1500', { timeout: 20_000 })

  // Pushed frames move the data clock and the channel strips.
  const clock = page.getByTestId('tile-time')
  const first = await clock.innerText()
  await expect(clock).not.toHaveText(first, { timeout: 20_000 })
  await expect(page.getByTestId('channel-strip')).toHaveCount(8)
  await expect(page.getByTestId('rig-state-now')).not.toBeEmpty()

  // The first newly created alert arrives as a toast; time it against its created_at.
  const toast = page.getByTestId('alert-toast').filter({ hasNotText: 'updated' }).first()
  await toast.waitFor({ timeout: 240_000 })
  const seenAt = Date.now()
  const href = (await toast.getByRole('link').getAttribute('href')) ?? ''
  const id = Number(new URL(href, 'http://x').searchParams.get('id'))
  const alert = await (await request.get(`/api/v1/alerts/${id}`)).json()
  const latencyMs = seenAt - Date.parse(alert.created_at)
  info.annotations.push({ type: 'alert-to-ui-ms', description: String(latencyMs) })
  console.log(`alert ${id} (${alert.alert_type}) stored → toast visible: ${latencyMs} ms`)
  expect(latencyMs).toBeLessThanOrEqual(5000)
  expect(alert.evidence.length).toBeGreaterThan(0)

  await waitForReplayIdle(request, well.id)
  expect(errors).toEqual([])
})

test('alerts center: evidence, Déjà Vu overlay and acknowledgement round trip', async ({
  page,
  request,
}) => {
  const errors = trackConsoleErrors(page)
  const all = (await (await request.get('/api/v1/alerts?limit=200')).json()).items as {
    id: number
    status: string
    sources: string[]
  }[]
  expect(all.length).toBeGreaterThan(0)
  const dv = all.find((a) => a.sources.includes('DEJA_VU'))
  const target = dv ?? all[0]!
  await page.goto(`/alerts?status=all&id=${target.id}`)
  const detail = page.getByTestId('alert-detail')
  await expect(detail).toBeVisible()
  await expect(page.getByTestId('alert-row').first()).toBeVisible()
  await expect(detail.getByTestId('no-evidence')).toHaveCount(0)
  await expect(detail.getByTestId('stream-evidence')).toBeVisible()
  if (dv) {
    await detail.getByRole('tab', { name: 'Déjà Vu' }).click()
    const chart = detail.getByTestId('dejavu-chart')
    await expect(chart).toContainText('not a probability')
    await expect(chart.getByRole('img')).toHaveCount(7)
  }
  await detail.getByRole('tab', { name: /What worked/ }).click()
  await expect(detail.getByTestId('alert-caveat')).toBeVisible()

  // Acknowledge an alert that is still new (the UI updates at once and the backend agrees).
  const fresh = all.find((a) => a.status === 'new')
  if (fresh && test.info().project.name === 'desktop') {
    await page.goto(`/alerts?status=all&id=${fresh.id}`)
    await page.getByRole('button', { name: 'Acknowledge' }).click()
    await expect(page.getByTestId('alert-actions')).toContainText('Acknowledged by dev')
    await expect
      .poll(async () => (await (await request.get(`/api/v1/alerts/${fresh.id}`)).json()).status)
      .toBe('ack')
  }
  expect(errors).toEqual([])
})

test('dashboard shows open alerts from the stream engine', async ({ page, request }) => {
  const open = (await (await request.get('/api/v1/alerts?status=new&status=ack')).json()).items
  await page.goto('/')
  const card = page.getByTestId('dashboard-alerts')
  await expect(card).toBeVisible()
  if (open.length) await expect(card.getByRole('link').nth(1)).toBeVisible()
  else await expect(card).toContainText('No open alerts')
})

for (const theme of ['deep-rig', 'daylight', 'command-blue']) {
  test(`F4 views pass automated WCAG 2.2 AA checks (${theme})`, async ({ page, request }) => {
    await page.addInitScript((t) => window.localStorage.setItem('smriti.theme', t), theme)
    const well = await drillingWell(request)
    const alerts = (await (await request.get('/api/v1/alerts?limit=50')).json()).items as {
      id: number
      sources: string[]
    }[]
    const dv = alerts.find((a) => a.sources.includes('DEJA_VU')) ?? alerts[0]
    const views: [string, string, (() => Promise<void>)?][] = [
      [`/live?well=${well.id}`, 'risk-gauges'],
      [
        `/alerts?status=all${dv ? `&id=${dv.id}` : ''}`,
        'alert-detail',
        dv?.sources.includes('DEJA_VU')
          ? async () => {
              await page.getByRole('tab', { name: 'Déjà Vu' }).click()
              await expect(page.getByTestId('dejavu-chart')).toBeVisible()
            }
          : undefined,
      ],
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
