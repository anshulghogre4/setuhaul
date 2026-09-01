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
 *
 * ## Updated 2026-09-01 for #99 / #100 / #102
 *
 * Three findings are no longer findings and their `DEAD-*` / `MISSING-*` shots are **gone rather
 * than kept for the record**: a screenshot named `DEAD-…` that shows working software is worse
 * than no screenshot, because the filename is what a reader trusts. The facility switcher (#99.1),
 * the driver state-line tap (#99.3) and the planner end-block control (#100) are now proved by
 * the assertions in `02-ops` / `03-planner` / `01-driver`, which is stronger evidence than a
 * still frame anyway. Two more (`MISSING-ops-rail-no-profile…`, `MISSING-gate-search-screen-no-
 * back-control`) are reclassified `NOT-IN-DESIGN` and their shots renamed to say so, because the
 * absence is correct -- see those specs' own evidence lines for the rulings.
 */

const SHOTS = resolve(SWEEP_OUT, 'shots')

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

const shot = (name: string) => ({ path: resolve(SHOTS, `${name}.png`), fullPage: true })

test.describe('MISSING — ops surface', () => {
  test.use({ storageState: storageFor('ops-ggn'), viewport: { width: 1600, height: 900 } })

  // The rail's single destination is the resolved design (Fork E, 2026-08-29), so this frame is
  // named for what it actually shows. The queue settings gear IS still a real gap.
  test('rail is single-destination by design; queue header has no settings gear', async ({ page }) => {
    await page.goto('/ops')
    await expect(page.getByRole('listbox', { name: 'Escalations' })).toBeVisible({ timeout: 30_000 })
    await page.screenshot(shot('MISSING-ops-queue-gear-and-NOT-IN-DESIGN-rail-profile'))
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

  // The end-block control landed with #100 and is proved by assertion in `03-planner`, so this
  // frame is now only about the picker and the re-sequence action.
  test('board has no interval picker and no re-sequence action', async ({ page }) => {
    await page.goto('/planner')
    await expect(page.getByRole('tab', { name: 'Board' })).toBeVisible({ timeout: 30_000 })
    await page.getByRole('tab', { name: 'Board' }).click()
    await page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
    await page.waitForTimeout(600)
    await page.screenshot(shot('MISSING-planner-board-no-picker-no-resequence'))
  })
})

test.describe('NOT-IN-DESIGN — gate surface', () => {
  test.use({ storageState: storageFor('gate-booth'), viewport: { width: 1280, height: 800 } })

  // Kept as a frame, renamed as a verdict: the search screen's shift bar matches
  // `stitch-prompts.md` section 3's verbatim copy exactly ("Nothing else on screen"), so the
  // absent back control is the design rather than a gap. See `04-gate.spec.ts` for the full
  // three-artefact citation and the fork it raises for screens.md section 2's stale sketch.
  test('search screen shift bar matches the prompt verbatim (no back control)', async ({ page }) => {
    await page.goto('/gate')
    await page.getByLabel('Officer name').fill('Sweep Probe Officer')
    await page.getByRole('button', { name: 'Start shift' }).click()
    await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
    await page.screenshot(shot('NOT-IN-DESIGN-gate-search-screen-back-control'))
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
  // The rail is single-destination by the same resolved ruling; the frame is kept because it also
  // shows the 403 sections, which ARE a real finding.
  test('403 sections (rail is single-destination by design)', async ({ browser }) => {
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
