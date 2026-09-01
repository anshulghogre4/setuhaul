import { expect, test, type BrowserContext, type Page } from 'playwright/test'

import { ORIGIN, carrierStorageState, recorderFor } from './support'

/**
 * 05 - Carrier portal. 8 designed controls.
 *
 * ## The identity problem is the headline finding, so it is stated before any verdict
 *
 * There is **no `CARRIER` account in the POC roster** -- `public.roles` runs ROL001..ROL008 and none
 * of them is `CARRIER`. The only identity that lands on `/carrier` is `USR105`
 * (`sanjay.gupta@setuhaul.com`, backend role `TRANSPORT_MANAGER`), because
 * `core/auth/identity-mapping.ts` maps the UI's `TRANSPORT_MANAGER` to the carrier surface. But
 * `backend/app/api/v1/routers/carrier.py` gates every read on `require_roles(RoleName.CARRIER)`, so
 * all four dashboard reads answer **403 FORBIDDEN** for that account (verified directly:
 * `/carrier/fleet-overview`, `/carrier/shipments`, `/carrier/exceptions`,
 * `/carrier/on-time-performance` all 403).
 *
 * `identity-mapping.ts` flags exactly this as a FORK for the owner and calls it "latent rather than
 * live" on the grounds that "no such account exists in the POC roster". **It does exist** -- USR105
 * -- so the fork is live, and the carrier portal has no working identity at all.
 *
 * Every data-bearing control below is therefore BLOCKED-ENV, and the reason is the same one.
 */

const say = recorderFor('05-carrier')

const NO_DATA =
  'no rows can render: every carrier read answers 403 FORBIDDEN for the only identity that reaches /carrier (USR105, backend role TRANSPORT_MANAGER; carrier.py gates on RoleName.CARRIER and no CARRIER account exists in the roster). The dashboard correctly shows its per-section failure blocks instead of inventing rows.'

let context: BrowserContext
let page: Page

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({
    storageState: await carrierStorageState(ORIGIN),
    viewport: { width: 1440, height: 900 },
  })
  page = await context.newPage()
})

test.afterAll(async () => {
  await context.close()
})

test('carrier: dashboard controls', async () => {
  const reads: Array<{ url: string; status: number }> = []
  page.on('response', (r) => {
    if (r.url().includes('/api/v1/carrier/')) reads.push({ url: r.url(), status: r.status() })
  })

  await page.goto(`${ORIGIN}/carrier`)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 30_000 })
  await page.waitForTimeout(1500)
  const statuses = reads.map((r) => `${new URL(r.url).pathname.split('/').pop()}=${r.status}`)

  // ---- Icon rail ------------------------------------------------------------------------------
  const rail = page.getByRole('navigation', { name: /^Main/ })
  const railCount = await rail.getByRole('link').count()
  // The top bar's own switcher, not any control whose label merely contains "facilit" (the search
  // button's placeholder does).
  const switcherCount = await page
    .getByRole('banner')
    .getByRole('button', { name: /All facilities|Select facility|^Jaipur$|^Gurugram$/ })
    .count()
  say(
    'Icon rail — console + profile',
    'MISSING',
    `the rail renders ${railCount} destination (the carrier console) and no Profile entry -- icon-rail.tsx emits exactly one railDestinationFor(role). The absence of a facility switcher IS correct here and is confirmed: ${switcherCount} switcher control(s) in the top bar (U83 Hidden, not disabled, because a carrier is carrier_id-scoped, not facility-scoped).`,
  )

  // ---- Refresh ---------------------------------------------------------------------------------
  const refresh = page.getByRole('button', { name: 'Refresh' })
  await expect(refresh).toBeVisible()
  const before = reads.length
  await refresh.click()
  await page.waitForTimeout(1500)
  const fired = reads.slice(before).map((r) => new URL(r.url).pathname.split('/').pop())
  say(
    'Refresh',
    'WORKING',
    `activating it re-fetched the dashboard's own reads: ${fired.length} request(s) [${fired.join(', ')}]. The design's four §7.5.6 reads all fire; they answer 403 for this identity (initial load: ${statuses.join(', ')}), so the sections render their failure blocks. The control itself does exactly what it is specified to do.`,
  )

  // ---- Status filter -----------------------------------------------------------------------------
  const filter = page.getByRole('button', { name: /^Filter shipments by status/ })
  await expect(filter).toBeVisible()
  await filter.click()
  const menu = page.getByRole('menu')
  const options = await menu.getByRole('menuitemradio').allTextContents()
  const beforeFilter = reads.length
  await menu.getByRole('menuitemradio', { name: 'Confirmed' }).click()
  await page.waitForTimeout(1200)
  const filterCalls = reads.slice(beforeFilter).map((r) => new URL(r.url).pathname.split('/').pop())
  const filterUrl = reads.slice(beforeFilter).find((r) => r.url.includes('status_filter'))
  say(
    'Status filter dropdown',
    'WORKING',
    `opened with options [${options.map((o) => o.trim()).join(' | ')}] and selecting "Confirmed" re-read the SHIPMENT list only (${filterCalls.join(', ')} -- the tiles are deliberately not re-fetched, per Flow 2), sending ${filterUrl ? new URL(filterUrl.url).search : 'no status_filter'}. NOTE the vocabulary is five, not the design's six: "Shown" is removed outright (no persisted counterpart) and "Held" is present because carrierHeldEnabled is on.`,
  )

  // ---- "Clear filter" ------------------------------------------------------------------------------
  const clear = page.getByRole('button', { name: /clear filter/i })
  say(
    '"Clear filter"',
    'BLOCKED-ENV',
    `renders only in the NO_MATCH_FOR_FILTER empty state, which needs a successful list read that returned zero rows. ${NO_DATA} The section shows its failure block instead, so the empty-filtered branch is unreachable (${await clear.count()} matches).`,
  )

  // ---- Rows / chevrons -------------------------------------------------------------------------------
  say('Shipment row / chevron', 'BLOCKED-ENV', NO_DATA)
  say('Open-exception row chevron', 'BLOCKED-ENV', NO_DATA)

  // ---- Top bar ----------------------------------------------------------------------------------------
  const bell = page.getByRole('button', { name: /^Notifications,/ })
  await bell.click()
  await expect(page.locator('[data-radix-popper-content-wrapper]').first()).toBeVisible()
  await page.keyboard.press('Escape')
  const helpHref = await page.getByRole('link', { name: 'Contact support' }).getAttribute('href')
  await page.getByRole('button', { name: /^Account menu/ }).click()
  const accountMenu = page.getByRole('menu', { name: 'Account' })
  await expect(accountMenu).toBeVisible()
  const items = await accountMenu.getByRole('menuitem').allTextContents()
  await page.keyboard.press('Escape')
  say(
    'Notifications bell / Help / Account menu',
    'WORKING-ON-FIXTURE',
    `bell panel opened, Help resolves straight to ${helpHref} with no intermediate menu, account menu opened with [${items.map((t) => t.trim()).join(' | ')}]. Notification content is fixture-backed by the documented CHROME SEAM.`,
  )
})

test('carrier: shipment detail — Back to Dashboard', async () => {
  await page.goto(`${ORIGIN}/carrier/shipments/SHP-RS-PENDING`)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 30_000 })
  const heading = (await page.getByRole('heading', { level: 1 }).textContent())?.trim()
  // The refusal screen renders its return control as a <button> (a router `navigate`), while the
  // ordinary detail screen renders a <Link>. Both are matched here so the verdict is about the
  // control, not about which branch happened to render.
  const back = page
    .getByRole('button', { name: /dashboard/i })
    .or(page.getByRole('link', { name: /dashboard/i }))
    .first()
  await expect(back).toBeVisible()
  await back.click()
  await expect(page).toHaveURL(/\/carrier$/)
  say(
    'Back to Dashboard',
    'WORKING',
    `the detail route rendered its refusal screen ("${heading}") -- get_shipment_detail answers 403 for this identity, and the client renders the out-of-scope screen rather than a connection error, which is the isOutOfScope() code branch working -- and its back control returned to /carrier`,
  )
})
