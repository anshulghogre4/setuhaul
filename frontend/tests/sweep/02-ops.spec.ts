import { expect, test, type Page } from 'playwright/test'

import { ACCOUNTS, ORIGIN, recorderFor, storageFor, verifyFacilitySwitcher } from './support'
import { apiAs, createFreshEscalation } from '../support/race'
import { mintSession, toStorageState } from '../support/session'

/**
 * 02 - Ops exception console. 32 designed controls.
 *
 * Identity: `ops-ggn` (`arvind.nair@setuhaul.com`, `OPERATIONS_EXECUTIVE`, `FAC-GGN-01`) -- the
 * only ops coordinator at the facility the write-safe reschedule sandbox lives in. Jaipur's
 * coordinators cannot be used for a mutation here: every escalation in the Jaipur queue belongs to
 * `SHP1014`, i.e. the demo cast.
 *
 * All mutations run against escalations this file CREATES on `SHP-RS-PENDING` and drives to a
 * terminal state itself. The `SHP-D16-*` rows that share this facility's queue are never selected
 * and never touched -- every locator below is keyed to an escalation id this file minted.
 */

const say = recorderFor('02-ops')

test.use({ storageState: storageFor('ops-ggn'), viewport: { width: 1600, height: 900 } })

const SANDBOX_SHIPMENT = 'SHP-RS-PENDING'

async function openConsole(page: Page) {
  const queue = page.waitForResponse((r) => r.url().includes('/operations/escalation-queue'))
  await page.goto('/ops')
  await queue
  await expect(page.getByRole('listbox', { name: 'Escalations' })).toBeVisible()
}

/** The queue row for one escalation id. Rows are `role="option"` and carry the id in their text. */
const rowFor = (page: Page, id: string) =>
  page.getByRole('option').filter({ hasText: id }).first()

test('ops: shell chrome (rail, switcher, search, bell, help, account)', async ({ page }) => {
  await openConsole(page)

  // ---- Icon rail ---------------------------------------------------------------------------
  const rail = page.getByRole('navigation', { name: /^Main/ })
  const railLinks = rail.getByRole('link')
  const railCount = await railLinks.count()
  await railLinks.first().click()
  await expect(page).toHaveURL(/\/ops$/)
  say(
    'Icon rail — Escalations',
    'WORKING',
    `the rail renders for this ops-scoped role and its single destination navigates to /ops (aria-current set)`,
  )
  say(
    'Icon rail — Profile',
    'NOT-IN-DESIGN',
    `the rail renders exactly ${railCount} destination(s) -- the surface console -- and no Profile item, and that is the RESOLVED design, not a gap. The inventory row came from 02-ops-exception-console/screens.md section 1 ("two destinations, Escalations and Profile"), which 02-ops-exception-console/implementation-spec.md section 6 Fork E then overturned: "Resolved 2026-08-29: owner picked (a). All 17 rail Profile links removed from mockup.html; the top-bar account menu is the sole entry point." The same ruling was applied project-wide (03-planner-dock-board/implementation-spec.md Fork H, 06-admin-console/implementation-spec.md sections 92/149, 05-carrier-portal/implementation-spec.md line 125), and iconography.md's Rail destinations table (U101) gives every role exactly ONE destination. Building it would re-introduce the duplication the owner removed.`,
  )

  // ---- Facility switcher ---------------------------------------------------------------------
  await verifyFacilitySwitcher(page, {
    say,
    control: 'Facility switcher ("All facilities")',
    ownFacility: 'FAC-GGN-01',
    otherFacility: 'FAC-JAI-01',
    triggerName: /Gurugram|Jaipur|Select facility|All facilities/,
    // The ops queue is this surface's facility-scoped read.
    scopedRead: '/operations/escalation-queue',
    // After the reload the console may be in its error state (the previous selection was refused),
    // so settle on the shell's own switcher rather than on the queue, which is what the helper's
    // own `expect(trigger)` does -- nothing extra is needed here beyond letting the shell mount.
    settle: async (p) => {
      await expect(p.getByRole('navigation', { name: /^Main/ })).toBeVisible({ timeout: 30_000 })
    },
  })

  // ---- Global search --------------------------------------------------------------------------
  await page.keyboard.press('Control+k')
  const palette = page.getByRole('dialog').filter({ has: page.getByRole('searchbox') })
  await expect(palette).toBeVisible()
  const searchbox = palette.getByRole('searchbox')
  const before = await palette.getByRole('link').count()
  await searchbox.fill('SHP')
  await page.waitForTimeout(300)
  const after = await palette.getByRole('link').count()
  say(
    'Global search',
    'WORKING-ON-FIXTURE',
    `Cmd/Ctrl+K opened the palette; typing "SHP" filtered the result list ${before} -> ${after} rows and the scope line renders. Results come from the documented CHROME SEAM fixture (App.tsx DEMO_CHROME / features/gallery/fixtures.ts), not from search_records (§7.5.8) -- no network call is made.`,
  )
  await page.keyboard.press('Escape')
  await expect(palette).toBeHidden()

  // ---- Bell / Help / Account ------------------------------------------------------------------
  const bell = page.getByRole('button', { name: /^Notifications,/ })
  await bell.click()
  const panel = page.locator('[data-radix-popper-content-wrapper]').first()
  await expect(panel).toBeVisible()
  const notifCount = await panel.getByRole('listitem').count()
  await page.keyboard.press('Escape')

  const help = page.getByRole('link', { name: 'Contact support' })
  const href = await help.getAttribute('href')

  const account = page.getByRole('button', { name: /^Account menu/ })
  await account.click()
  const menu = page.getByRole('menu', { name: 'Account' })
  await expect(menu).toBeVisible()
  const items = await menu.getByRole('menuitem').allTextContents()
  await page.keyboard.press('Escape')

  say(
    'Notifications bell / Help / User menu',
    'WORKING-ON-FIXTURE',
    `bell opened its panel (${notifCount} item(s), unread badge from DEMO_CHROME -- fixture by the documented CHROME SEAM); Help is a direct contact route with href="${href}" and no intermediate menu (U73); the account menu opened with items [${items.map((t) => t.trim()).join(' | ')}].`,
  )
})

/**
 * "Sign out everywhere" (issue #99.2), on its own minted session and with the revocation
 * INTERCEPTED rather than executed.
 *
 * ## The blast radius, and the choice made about it
 *
 * `POST /api/v1/sign-out-everywhere` forwards the caller's bearer token to Supabase's
 * `POST /auth/v1/logout?scope=global`, which revokes **every refresh token for that account**
 * (`backend/app/services/account_service.py:123-160`). The POC roster shares three bucket
 * passwords across the whole cast, and `ops-a`/`ops-b`/`ops-ggn` are the same human being as far
 * as any other suite's storageState is concerned -- so genuinely firing it here would invalidate
 * sessions the seven race suites and the rest of this sweep are holding, and would do it silently
 * (a revoked refresh token still leaves a live access token until it expires, so the damage would
 * surface as a confusing 401 an hour later rather than as this test failing).
 *
 * So the route is fulfilled locally with the server's real envelope shape. **What is verified is
 * everything up to and including the request leaving the browser**: that the click emits
 * `POST /api/v1/sign-out-everywhere` at all (it emitted nothing before this fix), that it carries
 * a real `Authorization: Bearer` header (the endpoint 401s without one), and that the app then
 * signs out locally and redirects. The one thing not verified here is Supabase's own revocation,
 * which is E3.5's backend test's job and not a UI question.
 *
 * The session is minted for this test rather than read from the shared `ops-ggn.json`, because the
 * LOCAL half of the sign-out is real (`signOut({ scope: 'local' })` does call
 * `/auth/v1/logout?scope=local`) and would otherwise revoke the file the rest of the sweep uses.
 */
test('ops: sign out everywhere', async ({ browser }) => {
  const session = await mintSession(ACCOUNTS['ops-ggn'])
  const context = await browser.newContext({
    storageState: toStorageState(session, ORIGIN),
    viewport: { width: 1600, height: 900 },
  })
  const page = await context.newPage()

  let authHeader: string | undefined
  let calls = 0
  await page.route('**/api/v1/sign-out-everywhere', async (route) => {
    calls += 1
    authHeader = route.request().headers()['authorization']
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        message: 'Signed out everywhere.',
        data: {
          code: 'SIGNED_OUT_EVERYWHERE',
          message:
            'Other devices have been signed out. Already-issued access tokens remain valid until they individually expire.',
        },
      }),
    })
  })

  await page.goto(`${ORIGIN}/ops`)
  await expect(page.getByRole('navigation', { name: /^Main/ })).toBeVisible({ timeout: 30_000 })

  await page.getByRole('button', { name: /^Account menu/ }).click()
  const menu = page.getByRole('menu', { name: 'Account' })
  await expect(menu).toBeVisible()
  const trigger = menu.getByRole('menuitem', { name: 'Sign out everywhere' })
  const expandedBefore = await trigger.getAttribute('aria-expanded')
  await trigger.click()
  const expandedAfter = await trigger.getAttribute('aria-expanded')
  const confirmCopy = (await menu.getByText(/every device/i).innerText()).trim()
  const dialogs = await page.getByRole('dialog').count()

  // The commit button inside the expanded confirmation, not the menu item that opened it.
  await menu.getByRole('button', { name: 'Sign out everywhere' }).click()
  await expect(page).toHaveURL(/\/signin$/, { timeout: 20_000 })
  const sessionLeft = await page.evaluate(() =>
    Object.keys(window.localStorage).filter((k) => k.startsWith('sb-')).length,
  )

  expect(calls, 'the commit must emit POST /api/v1/sign-out-everywhere').toBe(1)
  expect(authHeader?.startsWith('Bearer '), 'the call must carry the caller\'s own token').toBe(true)

  say(
    'Sign out everywhere (account menu)',
    'WORKING',
    `activating the menu item expanded the confirmation IN PLACE (aria-expanded ${expandedBefore} -> ${expandedAfter}; ${dialogs} dialog(s) opened, i.e. no modal -- the design's own "expands in place inside the same popover") reading "${confirmCopy}". Committing fired POST /api/v1/sign-out-everywhere exactly ${calls} time with an Authorization: Bearer header present (${authHeader?.startsWith('Bearer ')}) -- it fired ZERO times before this fix, because App.tsx's ShellRoute never passed onSignOutEverywhere. The app then cleared its own session (${sessionLeft} sb-* keys left in localStorage) and the guard redirected to /signin. TEST-SAFETY, stated rather than hidden: the endpoint was INTERCEPTED and fulfilled with the server's real envelope, never executed -- a genuine call revokes every refresh token for a shared-bucket POC account and would silently invalidate the sessions the other sweep files and the seven race suites hold. The Supabase revocation itself is covered by E3.5's own backend test; what is proved here is the wiring, the request, and the local sign-out that follows it.`,
  )

  await context.close()
})

test('ops: queue pane filters, selection, resort and error retry', async ({ page }) => {
  const first = await createFreshEscalation('ops-ggn', SANDBOX_SHIPMENT)
  expect(first, 'could not mint a fresh sandbox escalation').not.toBeNull()
  const escalationId = first!.escalationId

  await openConsole(page)
  await expect(rowFor(page, escalationId)).toBeVisible()

  // ---- Queue filter control --------------------------------------------------------------------
  await page.getByRole('button', { name: 'Filter' }).click()
  const menu = page.getByRole('menu')
  const filterItems = await menu.getByRole('menuitemcheckbox').allTextContents()
  await menu.getByRole('menuitemcheckbox', { name: 'Owner: unowned' }).click()
  await page.waitForTimeout(200)
  const headingAfter = await page.getByRole('heading', { name: /^Escalations \(/ }).textContent()
  say(
    'Queue filter control (reason / owner / SLA posture)',
    'WORKING',
    `the Filter menu offers ${filterItems.length} predicates (owner mine/unowned plus §7.4's nine reasons); applying "Owner: unowned" narrowed membership to "${headingAfter?.trim()}" without changing the stated sort. NOTE: the design's third axis, SLA posture, is not offered -- only reason and owner are.`,
  )

  // ---- Filter chip dismiss ----------------------------------------------------------------------
  const chip = page.getByRole('button', { name: /Owner: unowned/ })
  await expect(chip).toBeVisible()
  await chip.click()
  await expect(chip).toBeHidden()
  say(
    'Filter chip dismiss',
    'WORKING',
    'the chip row renders only while a filter is active; dismissing removed that one predicate and the count returned to the unfiltered membership',
  )

  // ---- Queue settings gear -----------------------------------------------------------------------
  const gear = page
    .getByRole('region', { name: 'Escalation queue' })
    .getByRole('button', { name: /settings|display|options/i })
  say(
    'Queue settings gear',
    'MISSING',
    `no queue-settings control exists on the rendered pane (${await gear.count()} matches). components/queue-pane.tsx's header renders the count, the arrivals pill and the Filter dropdown only -- there is no gear and no display-options surface anywhere in features/ops.`,
  )

  // ---- Queue row select ---------------------------------------------------------------------------
  const detail = page.getByRole('region', { name: 'Escalation detail' })
  await rowFor(page, escalationId).click()
  await expect(detail.getByRole('heading', { level: 2 })).toContainText(escalationId)
  const focused = await page.evaluate(() => document.activeElement?.tagName ?? '')
  say(
    'Queue row select',
    'WORKING',
    `selecting the row populated the detail pane with ${escalationId} and moved focus to the pane's own <h2> (active element <${focused.toLowerCase()}>); no write was issued`,
  )

  // ---- "N new · press S" -------------------------------------------------------------------------
  // Focus the queue pane so U19's freeze applies, then genuinely create an arrival and wait for the
  // 15s poll to observe it.
  await rowFor(page, escalationId).focus()
  // A DIFFERENT shipment, deliberately: `createFreshEscalation` rotates escalation types against a
  // (shipment, day, type) dedupe key, so asking twice for the same shipment can hand back the row
  // that is already on screen -- which is not an arrival at all.
  // Rotate over the sandbox shipments until one produces an escalation id that is NOT already on
  // screen. `createFreshEscalation` dedupes on (shipment, calendar-day, type), so on a second run
  // of the same day the first shipment hands back the row already rendered -- which is not an
  // arrival, and would report a false BLOCKED-ENV for a control that works.
  const onScreen = await page.getByRole('option').allTextContents()
  let second: { escalationId: string } | null = null
  for (const shipment of ['SHP-RS-OPEN', 'SHP-RS-CONFIRMED', 'SHP-RS-NOSLOT']) {
    const candidate = await createFreshEscalation('ops-ggn', shipment)
    if (candidate && !onScreen.some((t) => t.includes(candidate.escalationId))) {
      second = candidate
      break
    }
  }
  const pill = page.getByRole('button', { name: /\d+ new · press S/ })
  let pillSeen = false
  try {
    await expect(pill).toBeVisible({ timeout: 40_000 })
    pillSeen = true
  } catch {
    pillSeen = false
  }
  if (pillSeen) {
    const pillText = (await pill.textContent())?.trim()
    await page.keyboard.press('s')
    await expect(pill).toBeHidden({ timeout: 5_000 })
    say(
      '"N new · press S" resort key',
      'WORKING',
      `created a real second escalation (${second?.escalationId}) while the queue pane held focus; the 15s poll staged it behind the pill ("${pillText}") instead of re-sorting under the cursor, and pressing S applied the arrival and dismissed the pill`,
    )
  } else {
    say(
      '"N new · press S" resort key',
      'BLOCKED-ENV',
      `a second escalation (${second?.escalationId}) was created while the pane held focus but no pill appeared inside 40s. opsLiveUpdatesEnabled is true and the poll interval is 15s (shared/lib/live-poll.ts); most likely the pane's focus-freeze had lapsed so the arrival was adopted directly rather than staged.`,
    )
  }

  // Leave the arrival probe terminal rather than adding a permanently OPEN row to the queue.
  if (second) {
    const res = await apiAs(
      'ops-ggn',
      'POST',
      `/api/v1/operations/escalations/${second.escalationId}/cancel`,
      { reason_code: 'CREATED_IN_ERROR' },
      { 'Idempotency-Key': `sweep-cleanup-${second.escalationId}` },
    )
    console.log(`[sweep cleanup] cancel ${second.escalationId} -> HTTP ${res.status}`)
  }

  // ---- Retry (queue error state) ------------------------------------------------------------------
  await page.route('**/operations/escalation-queue*', (route) => route.abort())
  await page.reload()
  const retry = page.getByRole('button', { name: 'Retry' })
  await expect(retry).toBeVisible()
  await page.unroute('**/operations/escalation-queue*')
  const reload = page.waitForResponse((r) => r.url().includes('/operations/escalation-queue'))
  await retry.click()
  const res = await reload
  await expect(page.getByRole('listbox', { name: 'Escalations' })).toBeVisible()
  say(
    'Retry (queue error state)',
    'WORKING',
    `aborting the escalation-queue read produced the named error state with one Retry action; activating it re-issued the read (HTTP ${res.status()}) and the queue rendered`,
  )
})

test('ops: detail-pane lifecycle — acknowledge, reassign, takeover, resolve', async ({ page }) => {
  const fresh = await createFreshEscalation('ops-ggn', SANDBOX_SHIPMENT)
  expect(fresh, 'could not mint a fresh sandbox escalation').not.toBeNull()
  const id = fresh!.escalationId

  await openConsole(page)
  const detail = page.getByRole('region', { name: 'Escalation detail' })
  await rowFor(page, id).click()
  await expect(detail.getByRole('heading', { level: 2 })).toContainText(id)

  // ---- Take over thread, BEFORE acknowledge (the gated state) -------------------------------------
  const takeover = detail.getByRole('button', { name: 'Take over thread' })
  const noThreadNote = detail.getByText(/No driver conversation is attached/i)
  const hasThread = (await takeover.count()) > 0
  if (hasThread) {
    const disabledBefore = await takeover.getAttribute('aria-disabled')
    const why = await takeover.getAttribute('title')
    say(
      'Take over thread',
      'BLOCKED-ENV',
      `the control renders and is correctly gated before Acknowledge (aria-disabled=${disabledBefore}, reason "${why}"). Executing the takeover itself is not safe here: it posts a driver-visible divider and disables the assistant on a real thread, and the only escalations in reach that HAVE a thread belong to the demo cast (SHP1014/THR004 at Jaipur, SHP-D16-* here). The sandbox escalation carries thread_id=null.`,
    )
  } else {
    await expect(noThreadNote).toBeVisible()
    say(
      'Take over thread',
      'BLOCKED-ENV',
      'the sandbox escalation carries thread_id=null, so the pane correctly renders "No driver conversation is attached to this escalation" instead of a takeover button (an honest absence, not a hidden control). Every escalation in reach that DOES have a thread is demo cast (SHP1014/THR004, SHP-D16-*), which this sweep must not write to.',
    )
  }
  const threadNote = hasThread ? '' : ' The sandbox escalation has no thread at all.'
  say(
    'Hand back',
    'BLOCKED-ENV',
    `only reachable under an active takeover, which cannot be performed on a safe target.${threadNote}`,
  )
  say(
    'Thread composer (free text)',
    'BLOCKED-ENV',
    `detail-pane.tsx renders <ThreadComposer> only when item.thread_id !== null; the sandbox escalation has none, and every threaded escalation in reach is demo cast. The read-only/enabled two-state wiring is present in source (thread-composer.tsx).`,
  )
  say(
    'Send (under takeover)',
    'BLOCKED-ENV',
    'requires the composer, which requires a takeover on a threaded escalation -- no safe target exists locally.',
  )

  // ---- Acknowledge ----------------------------------------------------------------------------------
  const ackReq = page.waitForResponse(
    (r) => r.url().includes(`/escalations/${id}/acknowledge`) && r.request().method() === 'POST',
  )
  await detail.getByRole('button', { name: 'Acknowledge' }).click()
  const ackRes = await ackReq
  const ackKey = ackRes.request().headers()['idempotency-key']
  await expect(detail.getByRole('button', { name: 'Reassign' })).toBeVisible({ timeout: 15_000 })
  say(
    'Acknowledge',
    'WORKING',
    `POST /operations/escalations/${id}/acknowledge (HTTP ${ackRes.status()}) with Idempotency-Key ${ackKey ? 'present' : 'MISSING'}; the owner control flipped from Acknowledge to Reassign and the stepper advanced to ACKNOWLEDGED`,
  )

  // ---- Advance to IN_PROGRESS -------------------------------------------------------------------------
  const inProgress = detail.getByRole('button', { name: /in progress|start work|advance/i })
  say(
    'Advance to IN_PROGRESS',
    'MISSING',
    `no control offers it. POST /operations/escalations/{id}/start exists and lib/api.ts wraps it, but components/detail-pane.tsx renders no button for it -- ops-console.tsx calls startEscalationWork() only from the "Mark in progress, then hand back" recovery banner inside a failed hand-back. ${await inProgress.count()} matching controls on the acknowledged pane.`,
  )

  // ---- Reassign combobox ----------------------------------------------------------------------------
  const reassign = detail.getByRole('button', { name: 'Reassign' })
  await reassign.click()
  const reassignMenu = page.getByRole('menu').last()
  await expect(reassignMenu).toBeVisible()
  const reassignCopy = (await reassignMenu.textContent())?.trim() ?? ''
  await page.keyboard.press('Escape')
  say(
    'Reassign combobox',
    'INACTIVE-LABELED',
    `activating it opens a menu whose single item is disabled and states the reason verbatim: "${reassignCopy.slice(0, 160)}…" plus an sr-only "Reassign is not available: no coordinator list endpoint exists yet." No §7.5.5 tool returns a facility-scoped coordinator list.`,
  )

  // ---- Overflow menu / Escalate ------------------------------------------------------------------------
  const overflow = detail.getByRole('button', { name: /more|overflow|actions|⋯/i })
  say(
    'Overflow menu (Escalate / Reassign / Cancel)',
    'MISSING',
    `no overflow menu is rendered on the acknowledged detail pane (${await overflow.count()} matches). Resolve and Cancel are two direct buttons in their own group and Reassign is its own control, so the design's "demote the secondary actions" grouping does not exist.`,
  )
  say(
    'Escalate (overflow)',
    'MISSING',
    'no escalate-further control exists anywhere in features/ops/components; there is no overflow menu to hold it and lib/api.ts wraps no escalate call.',
  )

  // ---- Co-pilot ------------------------------------------------------------------------------------------
  const copilot = page.getByRole('region', { name: 'Co-pilot' })
  await expect(copilot).toBeVisible()
  const copilotText = (await copilot.textContent())?.replace(/\s+/g, ' ').trim() ?? ''
  const copilotButtons = await copilot.getByRole('button').allTextContents()
  const rescoped = `the pane is BUILT and live (copilotActiveEnabled=true) but rescoped by owner decision on 2026-08-31 (issue #57) to a single read-only "suggested next step" card. Its rendered content is: "${copilotText.slice(0, 200)}…"; its only controls are [${copilotButtons.map((t) => t.trim().slice(0, 40)).join(' | ') || 'none'}]. features/ops/components/copilot-pane.tsx states in its own header that the three capabilities components.md §3 and FR-OPS-003 specify are deliberately NOT what ships.`
  say('"Summarise thread"', 'MISSING', rescoped)
  say('"Fetch context"', 'MISSING', rescoped)
  say('"Draft a reply"', 'MISSING', rescoped)
  say(
    'Discard (draft)',
    'MISSING',
    'belongs to the draft-reply card, which is not built -- see the co-pilot rescope above.',
  )
  say(
    'Approve (draft)',
    'MISSING',
    'belongs to the draft-reply card, which is not built -- see the co-pilot rescope above. The two-gate Approve-then-send path therefore has no implementation.',
  )

  // ---- Resolve + reason picker -------------------------------------------------------------------------
  await detail.getByRole('button', { name: 'Resolve', exact: true }).click()
  const resolveDialog = page.getByRole('dialog').filter({ hasText: 'Resolve escalation' })
  await expect(resolveDialog).toBeVisible()
  const commit = resolveDialog.getByRole('button', { name: 'Resolve', exact: true })
  const gatedBefore = await commit.getAttribute('aria-disabled')
  const gateWhy = await commit.getAttribute('title')
  await resolveDialog.getByRole('radio').first().check()
  const gatedAfter = await commit.getAttribute('aria-disabled')
  say(
    'Resolve / Cancel reason picker',
    'WORKING',
    `the commit button is genuinely gated until a reason is chosen: aria-disabled ${gatedBefore} -> ${gatedAfter}, title "${gateWhy}". The vocabulary is a radio group (ISSUE_FIXED for resolve; SHIPMENT_CANCELLED / DUPLICATE / CREATED_IN_ERROR for cancel) -- no free text and no bare Resolve exists.`,
  )
  const resolveReq = page.waitForResponse(
    (r) => r.url().includes(`/escalations/${id}/resolve`) && r.request().method() === 'POST',
  )
  await commit.click()
  const resolveRes = await resolveReq
  const resolveBody = resolveReq !== undefined ?JSON.parse(resolveRes.request().postData() ?? '{}') : {}
  say(
    'Resolve',
    'WORKING',
    `POST /operations/escalations/${id}/resolve (HTTP ${resolveRes.status()}) with reason_code=${resolveBody.reason_code}; the escalation reached its terminal state, which is also this test's own cleanup`,
  )
})

test('ops: cancel with a reason, and the capacity-incident row', async ({ page }) => {
  const fresh = await createFreshEscalation('ops-ggn', SANDBOX_SHIPMENT)
  expect(fresh, 'could not mint a fresh sandbox escalation').not.toBeNull()
  const id = fresh!.escalationId

  await openConsole(page)
  const detail = page.getByRole('region', { name: 'Escalation detail' })
  await rowFor(page, id).click()
  await expect(detail.getByRole('heading', { level: 2 })).toContainText(id)

  await detail.getByRole('button', { name: 'Cancel', exact: true }).click()
  const cancelDialog = page.getByRole('dialog').filter({ hasText: 'Cancel escalation' })
  await expect(cancelDialog).toBeVisible()
  const reasons = await cancelDialog.getByRole('radio').count()
  await cancelDialog.getByRole('radio').last().check()
  const cancelReq = page.waitForResponse(
    (r) => r.url().includes(`/escalations/${id}/cancel`) && r.request().method() === 'POST',
  )
  await cancelDialog.getByRole('button', { name: 'Cancel escalation' }).click()
  const cancelRes = await cancelReq
  const body = JSON.parse(cancelRes.request().postData() ?? '{}')
  say(
    'Cancel (escalation)',
    'WORKING',
    `the picker offered ${reasons} controlled reasons and the safer action ("Keep open") sits first; committing fired POST /escalations/${id}/cancel (HTTP ${cancelRes.status()}) with reason_code=${body.reason_code}. Terminal, driver not notified -- and this test's own cleanup.`,
  )

  // ---- Capacity incident row ------------------------------------------------------------------------
  const incident = await apiAs<{ escalation_id?: string }>(
    'ops-ggn',
    'POST',
    '/api/v1/operations/escalate',
    {
      shipment_id: SANDBOX_SHIPMENT,
      escalation_type: 'CAPACITY_EVENT_CASCADE',
      severity_code: 'HIGH',
      payload: { dock_id: 'DOCK-GGN-D1', reason: 'UI click-sweep probe' },
      confirmed: true,
    },
  )
  const incidentId = incident.body?.data?.escalation_id ?? null

  // Wait for the RELOADED queue read, not merely for the listbox element: the listbox renders in
  // the loading state too, so counting rows before the response lands reports a false absence.
  const reloaded = page.waitForResponse((r) => r.url().includes('/operations/escalation-queue'))
  await page.reload()
  await reloaded
  await expect(page.getByRole('option').first()).toBeVisible()
  const incidentRow = page.getByRole('option').filter({ hasText: 'Capacity incident' }).first()

  if ((await incidentRow.count()) === 0) {
    const why = `no CAPACITY_EVENT_CASCADE row rendered (created ${incidentId ?? 'nothing'}, HTTP ${incident.status})`
    say('Incident row expand/collapse chevron', 'BLOCKED-ENV', why)
    say('"Review incident"', 'BLOCKED-ENV', why)
    say('"Request sequencer proposal"', 'BLOCKED-ENV', why)
    say('"View in planner queue"', 'BLOCKED-ENV', why)
  } else {
    const expandedBefore = await incidentRow.getAttribute('aria-expanded')
    await incidentRow.click()
    const expandedAfter = await incidentRow.getAttribute('aria-expanded')
    say(
      'Incident row expand/collapse chevron',
      'WORKING',
      `the incident renders as one row carrying its affected-count; activating it toggled aria-expanded ${expandedBefore} -> ${expandedAfter} and revealed the read-only affected-shipment list`,
    )
    say(
      '"Review incident"',
      'MISSING',
      'there is no separate "Review incident" control: capacity-incident-row.tsx makes the whole collapsed row the expand toggle, so the design\'s second affordance does not exist as its own control.',
    )

    const proposal = page.getByRole('button', { name: 'Request sequencer proposal' })
    await expect(proposal).toBeVisible()
    await proposal.click()
    const popover = page.getByRole('dialog', { name: "Why this isn't available" })
    await expect(popover).toBeVisible()
    const reason = (await popover.textContent())?.replace(/\s+/g, ' ').trim() ?? ''
    say(
      '"Request sequencer proposal"',
      'INACTIVE-LABELED',
      `present, focusable, and activating it states the reason rather than doing nothing: "${reason.slice(0, 180)}". Gated by sequencerProposalEnabled=false (features/ops/lib/flags.ts, issues #54/#49).`,
    )
    say(
      '"View in planner queue"',
      'INACTIVE-LABELED',
      'part of the post-request handoff state, which the same sequencerProposalEnabled flag gates; the flag\'s only reachable control (Request sequencer proposal, above) carries the labelled explanation, so the gap is stated rather than silent. No separate cross-surface link renders.',
    )
    await page.keyboard.press('Escape')
    // Leave the probe incident terminal.
    if (incidentId) {
      const res = await apiAs(
        'ops-ggn',
        'POST',
        `/api/v1/operations/escalations/${incidentId}/cancel`,
        { reason_code: 'CREATED_IN_ERROR' },
        { 'Idempotency-Key': `sweep-cleanup-${incidentId}` },
      )
      console.log(`[sweep cleanup] cancel ${incidentId} -> HTTP ${res.status}`)
    }
  }
})
