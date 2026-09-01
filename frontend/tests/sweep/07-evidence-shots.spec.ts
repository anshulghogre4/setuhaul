import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test } from 'playwright/test'

import { ORIGIN, SWEEP_OUT, carrierStorageState, storageFor } from './support'

/**
 * Screenshot evidence for the DEAD and MISSING findings.
 *
 * Playwright only captures on failure, and none of these tests fail -- the findings are things the
 * app does *not* do, which is a passing test with a negative assertion. So the shots are taken
 * explicitly, one per finding, into `tests/.artifacts/sweep/shots/` (gitignored).
 *
 * Full-page shots rather than element shots on purpose: a cropped picture of a control that does
 * nothing looks identical to a picture of one that works, so the useful frame is the whole surface
 * showing that nothing else changed either.
 */

const SHOTS = resolve(SWEEP_OUT, 'shots')

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

const shot = (name: string) => ({ path: resolve(SHOTS, `${name}.png`), fullPage: true })

test.describe('DEAD — facility switcher selection is a no-op', () => {
  test.use({ storageState: storageFor('ops-ggn'), viewport: { width: 1600, height: 900 } })

  test('ops', async ({ page }) => {
    await page.goto('/ops')
    await expect(page.getByRole('listbox', { name: 'Escalations' })).toBeVisible({ timeout: 30_000 })
    const switcher = page.getByRole('button', { name: /Gurugram|Select facility/ })
    await switcher.click()
    await expect(page.getByRole('listbox', { name: 'Facility' })).toBeVisible()
    await page.screenshot(shot('DEAD-ops-facility-switcher-open'))
    await page.getByRole('listbox', { name: 'Facility' }).getByRole('option').first().click()
    await page.waitForTimeout(800)
    // The point of the frame: identical to the one before, which is the defect.
    await page.screenshot(shot('DEAD-ops-facility-switcher-after-selection'))
  })
})

test.describe('DEAD — driver state line tap', () => {
  test.use({ storageState: storageFor('driver-sandbox'), viewport: { width: 390, height: 844 } })

  test('driver', async ({ page }) => {
    await page.goto('/driver')
    await page.waitForResponse((r) => r.url().includes('/api/v1/driver/context'))
    await page.locator('a[href="/driver/t/SHP-RS-PENDING"]').click()
    const line = page.getByRole('button', { name: 'Go to the message that set this state' })
    await expect(line).toBeVisible()
    await line.click()
    await page.waitForTimeout(600)
    await page.screenshot(shot('DEAD-driver-state-line-after-tap'))
  })
})

test.describe('MISSING — ops surface', () => {
  test.use({ storageState: storageFor('ops-ggn'), viewport: { width: 1600, height: 900 } })

  test('rail has no Profile; queue header has no settings gear', async ({ page }) => {
    await page.goto('/ops')
    await expect(page.getByRole('listbox', { name: 'Escalations' })).toBeVisible({ timeout: 30_000 })
    await page.screenshot(shot('MISSING-ops-rail-no-profile-and-no-queue-gear'))
  })

  test('co-pilot has no Summarise / Fetch context / Draft a reply; detail pane has no overflow menu', async ({
    page,
  }) => {
    await page.goto('/ops')
    await expect(page.getByRole('listbox', { name: 'Escalations' })).toBeVisible({ timeout: 30_000 })
    await page.getByRole('option').first().click()
    await expect(page.getByRole('region', { name: 'Escalation detail' })).toBeVisible()
    await page.waitForTimeout(1200)
    await page.screenshot(shot('MISSING-ops-copilot-three-actions-and-overflow-menu'))
  })
})

test.describe('MISSING — planner surface', () => {
  test.use({ storageState: storageFor('planner'), viewport: { width: 1600, height: 900 } })

  test('queue toolbar has no priority/ETA filter', async ({ page }) => {
    await page.goto('/planner')
    await expect(page.getByRole('tab', { name: 'Queue' })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/composite urgency/)).toBeVisible({ timeout: 30_000 })
    await page.screenshot(shot('MISSING-planner-queue-toolbar-no-priority-eta-filter'))
  })

  test('board has no interval picker, no end-block control, no re-sequence', async ({ page }) => {
    await page.goto('/planner')
    await expect(page.getByRole('tab', { name: 'Board' })).toBeVisible({ timeout: 30_000 })
    await page.getByRole('tab', { name: 'Board' }).click()
    await page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
    await page.waitForTimeout(600)
    await page.screenshot(shot('MISSING-planner-board-no-picker-no-endblock-no-resequence'))
  })
})

test.describe('MISSING — gate surface', () => {
  test.use({ storageState: storageFor('gate-booth'), viewport: { width: 1280, height: 800 } })

  test('search screen carries no back-to-shift control', async ({ page }) => {
    await page.goto('/gate')
    await page.getByLabel('Officer name').fill('Sweep Probe Officer')
    await page.getByRole('button', { name: 'Start shift' }).click()
    await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
    await page.screenshot(shot('MISSING-gate-search-screen-no-back-control'))
    await page.getByRole('button', { name: 'End shift' }).click()
  })
})

test.describe('MISSING — admin surface', () => {
  test.use({ storageState: storageFor('admin-a'), viewport: { width: 1600, height: 900 } })

  test('rule rows carry no edit affordance', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.getByRole('tab', { name: 'Facility Rules' })).toBeVisible({ timeout: 30_000 })
    await page.getByRole('tab', { name: 'Facility Rules' }).click()
    await expect(page.getByRole('button', { name: 'Add rule' })).toBeVisible()
    await page.waitForTimeout(800)
    await page.screenshot(shot('MISSING-admin-rule-rows-no-edit'))
  })

  test('audit tab has no search box; simulation cases are a flat list', async ({ page }) => {
    await page.goto('/admin')
    await expect(page.getByRole('tab', { name: 'Audit' })).toBeVisible({ timeout: 30_000 })
    await page.getByRole('tab', { name: 'Audit' }).click()
    await page.waitForResponse((r) => r.url().includes('/admin/audit-log'))
    await page.waitForTimeout(600)
    await page.screenshot(shot('MISSING-admin-audit-tab-no-search-box'))

    await page.getByRole('tab', { name: 'Policy' }).click()
    await page.waitForResponse((r) => r.url().includes('/admin/policy/active'))
    await page.getByRole('button', { name: /Simulate against last 30 days/ }).click()
    await expect(
      page.locator('[role="status"]').filter({ hasText: /decisions in the last 30 days would flip/ }),
    ).toBeVisible({ timeout: 30_000 })
    await page.screenshot(shot('MISSING-admin-simulation-cases-flat-not-expanders'))
  })
})

test.describe('MISSING — carrier surface', () => {
  test('rail has no Profile entry', async ({ browser }) => {
    const context = await browser.newContext({
      storageState: await carrierStorageState(ORIGIN),
      viewport: { width: 1440, height: 900 },
    })
    const page = await context.newPage()
    await page.goto(`${ORIGIN}/carrier`)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 30_000 })
    await page.waitForTimeout(1500)
    await page.screenshot(shot('MISSING-carrier-rail-no-profile-403-sections'))
    await context.close()
  })
})
