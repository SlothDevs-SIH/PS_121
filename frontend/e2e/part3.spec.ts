import { AxeBuilder } from '@axe-core/playwright'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { lowConfidenceDdr } from './pdf.ts'

// Part 3 (F2): Correlation Panel, Well 360, Knowledge Search, review queue, map proximity
// modes, and automated WCAG 2.2 AA checks. Needs the seeded field (`seed --wait` in CI).

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

/** Drilled wells, those with the most extracted events first. */
async function busyWells(request: APIRequestContext): Promise<number[]> {
  const r = await request.get('/api/v1/events?limit=500')
  const counts = new Map<number, number>()
  for (const e of (await r.json()).items as { well_id: number }[])
    counts.set(e.well_id, (counts.get(e.well_id) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id)
}

function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (msg) => msg.type() === 'error' && errors.push(msg.text()))
  page.on('pageerror', (err) => errors.push(err.message))
  return errors
}

test('correlation panel: six wells, re-aligned within a second, events open their page', async ({
  page,
  request,
}) => {
  const errors = trackConsoleErrors(page)
  const busy = await busyWells(request)
  const drilled = (await wells(request)).filter((w) => w.status !== 'planned').map((w) => w.id)
  const ids = [...new Set([...busy, ...drilled])].slice(0, 6)
  const t0 = Date.now()
  await page.goto(`/correlation?wells=${ids.join(',')}`)
  await expect(page.getByTestId('corr-header')).toHaveCount(6)
  const firstMs = Date.now() - t0

  // Changing the alignment is one API round trip plus drawing six columns. Timed in the page
  // (click → panel re-drawn → next frame): expect()'s retry polling would add up to a second.
  const realignMs = await page.evaluate(async () => {
    const panel = document.querySelector('[data-testid="correlation-panel"]')!
    const t0 = performance.now()
    const drawn = new Promise<number>((resolve) => {
      const obs = new MutationObserver(() => {
        if (panel.getAttribute('data-align') !== 'FORMATION_RELATIVE') return
        obs.disconnect()
        requestAnimationFrame(() => resolve(performance.now() - t0))
      })
      obs.observe(panel, { attributes: true })
    })
    ;(
      document.querySelector('[role="radio"][aria-label="Formation-relative"]') as HTMLElement
    ).click()
    return drawn
  })
  await expect(page.getByTestId('corr-header')).toHaveCount(6)
  test
    .info()
    .annotations.push(
      { type: 'correlation first render (ms, incl. page load)', description: String(firstMs) },
      { type: 'correlation re-align (ms)', description: String(realignMs) },
    )
  expect(realignMs).toBeLessThan(1000)

  await page.getByRole('radio', { name: 'Flatten on top' }).click()
  await expect(page.getByTestId('top-select')).toBeVisible()
  await expect(page.getByTestId('correlation-panel')).toHaveAttribute(
    'data-align',
    'FLATTEN_ON_TOP',
  )

  const marker = page.getByTestId('event-marker').first()
  await marker.scrollIntoViewIfNeeded()
  await marker.click()
  const card = page.getByTestId('event-card')
  await expect(card.getByTestId('evidence-link').first()).toBeVisible()
  await card.getByTestId('evidence-link').first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.locator('[data-highlighted="true"]').first()).toBeVisible()
  expect(errors).toEqual([])
})

test('well 360: wellbore, events with what was done, 3D trajectory', async ({ page, request }) => {
  const [id] = await busyWells(request)
  await page.goto(`/wells/${id}`)
  await expect(page.getByTestId('well-schematic')).toBeVisible()
  await expect(page.getByTestId('data-quality')).toContainText('Data quality')
  await expect(page.getByTestId('casing-table').getByTestId('evidence-link').first()).toBeVisible()

  await page.getByRole('tab', { name: /Events/ }).click()
  await page.getByTestId('event-row').first().click()
  await expect(page.getByTestId('event-detail')).toContainText(
    'Actions in the order they were tried',
  )

  await page.getByRole('tab', { name: /Trajectory/ }).click()
  const view = page.getByTestId('trajectory-3d')
  await expect(view.getByTestId('path-subject')).toBeVisible()
  await page.getByRole('radio', { name: 'Plan' }).click()
  await expect(view).toHaveAttribute('data-pitch', '90')
  const box = (await view.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 100, box.y + box.height / 2)
  await page.mouse.up()
  await expect(view).not.toHaveAttribute('data-yaw', '0') // dragging turns the camera
})

test('knowledge search: cited lessons and passages, and an honest "no record"', async ({
  page,
}) => {
  await page.goto('/search')
  await page.getByTestId('search-input').fill('lost circulation')
  await page.getByTestId('search-input').press('Enter')
  const results = page.getByTestId('search-results')
  await expect(results.getByTestId('passage').first()).toBeVisible()
  await expect(results.locator('mark').first()).toBeVisible()
  await results.getByTestId('passage').first().getByTestId('evidence-link').click()
  await expect(page.getByRole('dialog').locator('[data-highlighted="true"]').first()).toBeVisible()
  await page.keyboard.press('Escape')

  await page.goto('/search?q=zqxj%20vlkw%20pternal')
  await expect(page.getByTestId('no-record')).toContainText('No record found')
})

test('review queue: a low-confidence extraction is corrected against its page', async ({
  page,
  request,
}, info) => {
  test.skip(info.project.name !== 'desktop', 'writes to the database; run once')
  const nonce = Math.random().toString(16).slice(2, 14)
  const up = await request.post('/api/v1/documents', {
    multipart: {
      files: {
        name: `e2e-review-${nonce}.pdf`,
        mimeType: 'application/pdf',
        buffer: lowConfidenceDdr(nonce),
      },
    },
  })
  expect(up.ok()).toBe(true)
  const docId = (await up.json())[0].document_id as number
  await expect
    .poll(
      async () => {
        const d = await (await request.get(`/api/v1/documents/${docId}`)).json()
        return d.extract_status === 'done' && d.index_status !== 'running'
      },
      { timeout: 90_000, intervals: [1000] },
    )
    .toBe(true)
  const queue = await (
    await request.get(`/api/v1/review-queue?status=pending&document_id=${docId}&limit=10`)
  ).json()
  const item = queue.items[0] as { id: number; kind: string }
  expect(item.kind).toBe('event')

  const started = Date.now()
  await page.goto(`/documents?view=review&item=${item.id}`)
  await expect(page.getByTestId('review-source')).toContainText(`e2e-review-${nonce}.pdf`)
  const panel = page.getByTestId('review-panel')
  await expect(panel).toContainText('NPT code NPT-LOSS')
  await expect(page.locator('[data-highlighted="true"]').first()).toBeVisible()
  await page.keyboard.press('e')
  // A rerun's upload can merge into the event an earlier run corrected (same well, date and
  // depth), so correct relative to whatever the form holds now.
  const depth = page.getByLabel('Correct Depth')
  const before = Number(await depth.inputValue())
  await depth.fill(String(before + 2))
  await page.getByRole('button', { name: /Save correction/ }).click()
  await expect(page.getByTestId('review-notice')).toContainText('Corrected 1 field')
  test
    .info()
    .annotations.push({ type: 'review round trip (ms)', description: String(Date.now() - started) })

  const decided = await (
    await request.get(`/api/v1/review-queue?status=corrected&document_id=${docId}`)
  ).json()
  expect(decided.items.map((i: { id: number }) => i.id)).toContain(item.id)
})

test('map explorer: at-formation and closest-approach distances with their labels', async ({
  page,
  request,
}) => {
  const [id] = await busyWells(request)
  await page.goto(`/map?well=${id}&r=10`)
  await expect(page.getByTestId('offset-table')).toBeVisible()
  await page.getByTestId('proximity-mode').getByRole('radio', { name: 'At formation' }).click()
  await expect(page.getByTestId('formation-select')).toBeVisible()
  await expect(page.getByTestId('distance-label')).toContainText('entry points into')
  await expect(page).toHaveURL(/mode=AT_FORMATION/)
  await page.getByTestId('proximity-mode').getByRole('radio', { name: 'Closest approach' }).click()
  await expect(page.getByTestId('distance-label')).toContainText('Closest 3D distance')
  await page.getByTestId('tvdss-from').fill('1000')
  await page.getByTestId('tvdss-from').press('Enter')
  await expect(page.getByTestId('distance-label')).toContainText('TVDSS 1000')
})

const SCREENS: [string, string][] = [
  ['/correlation', 'correlation-panel'],
  ['/search?q=stuck%20pipe', 'search-results'],
  ['/documents?view=review', 'review-queue'],
]

for (const theme of ['deep-rig', 'daylight', 'command-blue']) {
  test(`accessibility: no WCAG 2.2 AA violations on the Part 3 screens (${theme})`, async ({
    page,
    request,
  }) => {
    await page.addInitScript((t) => window.localStorage.setItem('smriti.theme', t), theme)
    const [id] = await busyWells(request)
    const screens: [string, string][] = [
      ...SCREENS,
      [`/wells/${id}`, 'well-schematic'],
      [`/wells/${id}?tab=events`, 'event-list'],
      [`/wells/${id}?tab=trajectory`, 'trajectory-3d'],
      [`/map?well=${id}&mode=AT_FORMATION`, 'offset-table'],
    ]
    for (const [url, testId] of screens) {
      await page.goto(url)
      await expect(page.getByTestId(testId).first()).toBeVisible()
      const result = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
        // Map pins of wells on one pad overlap; WCAG 2.5.8's "equivalent" exception applies:
        // every well can also be picked from the offset table and the well picker.
        .exclude('.maplibregl-marker')
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
