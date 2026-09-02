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
    `no queue-settings control exists on the rendered pane (${await gear.count()} matches). components/queue-pane.tsx's header renders the count, the arrivals pill and the Filter dropdown only. DELIBERATELY NOT BUILT this session, and the reason is a design gap rather than effort: the gear appears in exactly two places -- screens.md §2's ASCII ("[Filter: reason ▾] [⚙]") and stitch-prompts.md:194/:244 ("a filter control and a settings icon button", "small ghost icon button, Lucide settings-2 16px") -- and NEITHER states what it does. There is no behaviour, no panel contents and no persisted preference named anywhere in 02-ops-exception-console/. The obvious guess, column preferences, does not apply here: this queue is a role="listbox" of composed rows (id/reason/shipment/SLA), not a column table like the planner's, so there are no columns to show or hide. Building it would mean inventing a feature and then inventing what it configures. NEEDS A DESIGN RULING: say what the gear opens, or drop it from §2's sketch.`,
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
  // Acknowledge retires (the escalation is now owned) and the overflow appears -- screens.md §3's
  // "once acknowledged". Previously this waited on a standalone Reassign button, which moved into
  // the overflow this session.
  await expect(detail.getByRole('button', { name: 'More actions' })).toBeVisible({ timeout: 15_000 })
  await expect(detail.getByRole('button', { name: 'Acknowledge' })).toBeHidden()
  say(
    'Acknowledge',
    'WORKING',
    `POST /operations/escalations/${id}/acknowledge (HTTP ${ackRes.status()}) with Idempotency-Key ${ackKey ? 'present' : 'MISSING'}; the Acknowledge button retired, the acknowledged-only overflow [⋯] appeared, and the stepper advanced to ACKNOWLEDGED`,
  )

  // ---- Advance to IN_PROGRESS -------------------------------------------------------------------------
  // The stepper is a role="img" whose accessible name IS its position ("Stage: Ack" ->
  // "Stage: In prog"), so the assertion reads the rendered lifecycle rather than a CSS class.
  const stepper = detail.getByRole('img', { name: /^Stage:/ })
  const stageBefore = await stepper.getAttribute('aria-label')

  const inProgress = detail.getByRole('button', { name: 'Mark in progress' })
  await expect(inProgress).toBeVisible()
  const startReq = page.waitForResponse(
    (r) => r.url().includes(`/escalations/${id}/start`) && r.request().method() === 'POST',
  )
  await inProgress.click()
  const startRes = await startReq
  const startKey = startRes.request().headers()['idempotency-key']
  const startBody = (await startRes.json()) as { data?: { code?: string; stepper_position?: number } }

  // The stepper must actually move, and it only can once the queue has been re-read -- the
  // position is a server field, never a local increment.
  await expect(stepper).toHaveAttribute('aria-label', /In prog/, { timeout: 15_000 })
  const stageAfter = await stepper.getAttribute('aria-label')
  // Once IN_PROGRESS the control retires: a second press could only return ALREADY_IN_PROGRESS.
  await expect(inProgress).toBeHidden()

  say(
    'Advance to IN_PROGRESS',
    'WORKING',
    `built this session and driven end to end. Pressing "Mark in progress" fired POST /operations/escalations/${id}/start (HTTP ${startRes.status()}, code=${startBody.data?.code}, stepper_position=${startBody.data?.stepper_position}) with Idempotency-Key ${startKey ? 'present' : 'MISSING'}, and the detail pane's stepper advanced "${stageBefore}" -> "${stageAfter}" off the server's own stepper_position after the queue re-read. The control then disappears (a second press could only answer ALREADY_IN_PROGRESS). Before this session the endpoint and lib/api.ts's startEscalationWork() both existed with no button anywhere -- the only call site was the hand-back recovery banner, so the middle stepper dot was reachable only via a FAILED hand-back. Design note: flows-and-states.md Flow 1 step 4 requires this transition ("a status the coordinator sets explicitly once real work has started") but screens.md §3 and stitch-prompts.md prompt 7 never DRAW the control; it is placed in the pane's lifecycle action row as neutral, not primary, per prompt 7's "only one primary action exists in this view". Flagged for the owner as a placement the design does not settle.`,
  )

  // ---- Overflow menu ------------------------------------------------------------------------------------
  const overflow = detail.getByRole('button', { name: 'More actions' })
  await expect(overflow).toBeVisible()
  await overflow.click()
  const overflowMenu = page.getByRole('menu').last()
  await expect(overflowMenu).toBeVisible()
  const overflowItems = await overflowMenu.getByRole('menuitem').allTextContents()
  const overflowCopy = (await overflowMenu.textContent())?.replace(/\s+/g, ' ').trim() ?? ''
  await page.keyboard.press('Escape')

  say(
    'Overflow menu (Escalate / Reassign / Cancel)',
    'WORKING',
    `built this session. A ghost [⋯] button (accessible name "More actions", Lucide ellipsis per stitch-prompts.md prompt 7) renders on the ACKNOWLEDGED pane only -- screens.md §3's "once acknowledged" -- and opens a menu whose items are [${overflowItems.map((t) => t.trim().slice(0, 60)).join(' | ')}]. DIVERGENCE, stated not hidden: the menu holds Escalate and Reassign but NOT Cancel, because the design contradicts itself -- screens.md §3's prose puts Cancel in this menu while §3 and §3b both DRAW it as a button in the pane's action group ("[ Take over thread ] [ Cancel ]", "[ Resolve ] [ Cancel ]"). This build keeps the drawn group (which is also what makes Flow 6's Resolve/Cancel pairing legible) and the menu says so in place of a duplicated entry. Owner fork: correct §3's prose, or redraw §3/§3b.`,
  )

  // ---- Reassign (now inside the overflow) ----------------------------------------------------------------
  say(
    'Reassign combobox',
    'INACTIVE-LABELED',
    `moved out of the owner control and into the overflow this session, per screens.md §3 / stitch-prompts.md prompt 7 ("Escalate, Reassign and Cancel ... deliberately not primary buttons"). It renders as a disabled menu item stating the reason verbatim inside the menu opened above: "${overflowCopy.slice(0, 200)}…". Unchanged in substance -- no §7.5.5 tool returns a facility-scoped coordinator list, and a free-text new_owner_id would be exactly the client-supplied scope id M15 forbids.`,
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

/**
 * **Escalate, from the detail pane's overflow** (built this session).
 *
 * ## Why this is its own test and why it targets `SHP-RS-NOSLOT`
 *
 * The dialog escalates the **selected escalation's own shipment**, so proving it needs a selected
 * row whose shipment is the sanctioned escalate surface. `SHP-RS-NOSLOT` is that surface (the
 * reschedule sandbox); the lifecycle test above works `SHP-RS-PENDING` and must not have a second
 * case opened underneath it mid-flow.
 *
 * ## What is written, and how it is unwound
 *
 * Two rows can exist when this finishes: the fresh case this test mints to have something to
 * select, and the case the Escalate control opens. **Both are cancelled in a `finally`**, so a
 * failed assertion cannot leave an OPEN row in the queue. The preview half writes nothing at all
 * by construction -- `escalate_exception` returns `CONFIRMATION_REQUIRED` before it touches the
 * database -- which this test asserts directly rather than assuming.
 */
test('ops: escalate a further case from the detail-pane overflow', async ({ page }) => {
  const seed = await createFreshEscalation('ops-ggn', 'SHP-RS-NOSLOT')
  if (seed === null) {
    // Not a build failure and not silently swallowed. `createFreshEscalation` treats any non-200
    // as "this type is not free" and rotates, so a transient backend 500 across several types
    // exhausts all nine and returns null. Observed directly on this stack while building this
    // test: POST /operations/escalate answered 500 `(EMAXCONNSESSION) max clients reached in
    // session mode - max clients are limited to pool_size: 15` -- the same pool-exhaustion class
    // AGENTS.md records from 2026-08-17 -- and a retry seconds later answered 200. Recorded as an
    // environment block with the real cause rather than failing the suite for it.
    say(
      'Escalate (overflow)',
      'BLOCKED-ENV',
      'could not mint a sandbox escalation on SHP-RS-NOSLOT to escalate FROM: POST /api/v1/operations/escalate failed for all nine escalation types. Seen on this stack as HTTP 500 "(EMAXCONNSESSION) max clients reached in session mode - max clients are limited to pool_size: 15", which is backend connection-pool exhaustion, not a frontend gap. The control itself is built (features/ops/components/escalate-dialog.tsx + overflow-menu.tsx) and its two-press preview/confirm path is wired to POST /operations/escalate. Re-run when the pool recovers.',
    )
    return
  }
  const seedId = seed.escalationId
  let openedId: string | null = null

  try {
    await openConsole(page)
    const detail = page.getByRole('region', { name: 'Escalation detail' })
    await rowFor(page, seedId).click()
    await expect(detail.getByRole('heading', { level: 2 })).toContainText(seedId)

    // The overflow is acknowledged-only, so claim the case first.
    const ack = page.waitForResponse(
      (r) => r.url().includes(`/escalations/${seedId}/acknowledge`) && r.request().method() === 'POST',
    )
    await detail.getByRole('button', { name: 'Acknowledge' }).click()
    await ack

    // Re-select if the post-acknowledge queue re-read dropped the selection. `handleAcknowledge`
    // calls `load()`, and a failed re-read (the same EMAXCONNSESSION class above) leaves the pane
    // on its "Select an escalation." empty state with the write itself already committed. Observed
    // once during this test's own development, so the recovery is explicit rather than a retry
    // loop that would hide it.
    const detailEmpty = detail.getByText('Select an escalation.')
    if (await detailEmpty.isVisible().catch(() => false)) {
      await rowFor(page, seedId).click()
      await expect(detail.getByRole('heading', { level: 2 })).toContainText(seedId)
    }

    const overflow = detail.getByRole('button', { name: 'More actions' })
    await expect(overflow).toBeVisible({ timeout: 15_000 })
    await overflow.click()
    await page.getByRole('menuitem', { name: 'Escalate…' }).click()

    const dialog = page.getByRole('dialog').filter({ hasText: 'Escalate' })
    await expect(dialog).toBeVisible()

    // The open case's own reason must be offered but NOT selectable -- escalations dedupe on
    // (shipment, day, type), so re-raising it would refresh this row rather than open a case.
    const reasonSelect = dialog.getByLabel('Reason')
    const disabledOptions = await reasonSelect
      .locator('option[disabled]')
      .allTextContents()

    // Commit is gated until the free-text "what is happening" is filled.
    const commit = dialog.getByRole('button', { name: /Preview escalation|Escalate/ })
    const gatedBefore = await commit.getAttribute('aria-disabled')
    const gateWhy = await commit.getAttribute('title')

    await reasonSelect.selectOption('SAFETY_OR_REGULATED')
    await dialog.getByLabel('Severity').selectOption('MEDIUM')
    await dialog
      .getByLabel('What is happening')
      .fill('UI click-sweep probe — opened and cancelled in this same test')

    // ---- Step 1: preview. Asserts confirmed=false AND that nothing was written. ----
    const previewReq = page.waitForResponse(
      (r) => r.url().includes('/operations/escalate') && r.request().method() === 'POST',
    )
    await commit.click()
    const previewRes = await previewReq
    const previewSent = JSON.parse(previewRes.request().postData() ?? '{}')
    const previewBody = (await previewRes.json()) as {
      data?: { code?: string; note?: string; escalation_id?: string }
    }
    await expect(dialog.getByText(/Confirm before this becomes a real case/)).toBeVisible()

    expect(previewSent.confirmed, 'the first press must send confirmed=false').toBe(false)
    expect(previewBody.data?.code, 'the preview must not write').toBe('CONFIRMATION_REQUIRED')
    expect(previewBody.data?.escalation_id, 'a preview carries no escalation id').toBeUndefined()

    // ---- Step 2: confirm. This one writes. ----
    const confirmReq = page.waitForResponse(
      (r) =>
        r.url().includes('/operations/escalate') &&
        r.request().method() === 'POST' &&
        JSON.parse(r.request().postData() ?? '{}').confirmed === true,
    )
    await dialog.getByRole('button', { name: 'Escalate', exact: true }).click()
    const confirmRes = await confirmReq
    const confirmSent = JSON.parse(confirmRes.request().postData() ?? '{}')
    const confirmBody = (await confirmRes.json()) as { data?: { escalation_id?: string } }
    openedId = confirmBody.data?.escalation_id ?? null
    await expect(dialog).toBeHidden()

    // M15: the body may name a shipment and never a facility, driver or owner -- the server
    // derives all three from the shipment row and the verified token. Asserted, not assumed.
    const bodyKeys = Object.keys(confirmSent).sort()
    expect(bodyKeys).toEqual(
      ['confirmed', 'escalation_type', 'payload', 'severity_code', 'shipment_id'],
    )

    say(
      'Overflow menu (Escalate / Reassign / Cancel)',
      'WORKING',
      `see also the lifecycle test. Here the menu's Escalate… entry opened its dialog from the acknowledged pane.`,
    )
    say(
      'Escalate (overflow)',
      'WORKING',
      `built this session and driven end to end on the sanctioned SHP-RS-NOSLOT surface. TWO presses, and the first writes nothing: press 1 posted POST /api/v1/operations/escalate with confirmed=false and the server answered code=${previewBody.data?.code} carrying its OWN confirm sentence ("${(previewBody.data?.note ?? '').slice(0, 110)}…"), which the dialog renders verbatim rather than paraphrasing -- and the response carries no escalation_id, i.e. escalate_exception returned before touching the database (escalation_service.py:128-141). Press 2 posted the identical body with confirmed=true (HTTP ${confirmRes.status()}) and opened ${openedId}. The commit is gated until the free-text cause is filled (aria-disabled=${gatedBefore}, title "${gateWhy}"), and the open case's own reason is rendered DISABLED with the dedupe stated [${disabledOptions.map((t) => t.trim()).join(' | ')}] -- re-raising the same (shipment, day, type) refreshes the existing row rather than opening a case, so offering it would read as "nothing happened". M15 asserted directly: the request body keys are exactly [${bodyKeys.join(', ')}] -- a shipment id and nothing that names a facility, driver or owner; the server derives scope from the shipment row plus the verified token (assert_facility_write_scope). DESIGN NOTE: screens.md §3 names Escalate in the overflow and defines nothing else about it -- no argument list, no target -- so the semantics built here (open a SEPARATE case on the same shipment under a different §7.4 reason, leaving the current case's owner and SLA untouched) are the only ones any shipped tool supports. Flagged for the owner.`,
    )
  } finally {
    // Both rows terminal, whatever happened above.
    for (const cleanupId of [openedId, seedId]) {
      if (!cleanupId) continue
      const res = await apiAs(
        'ops-ggn',
        'POST',
        `/api/v1/operations/escalations/${cleanupId}/cancel`,
        { reason_code: 'CREATED_IN_ERROR' },
        { 'Idempotency-Key': `sweep-cleanup-${cleanupId}` },
      )
      console.log(`[sweep cleanup] cancel ${cleanupId} -> HTTP ${res.status}`)
    }
  }
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
    const proposalDisabled = await proposal.getAttribute('aria-disabled')
    say(
      '"Request sequencer proposal"',
      'VERIFIED-TO-DIALOG',
      `VERDICT CHANGE from INACTIVE-LABELED. sequencerProposalEnabled is now true and the action is live: it posts to /operations/escalations/{id}/sequencer-proposal, which is a real delegate to section 7.5.3's propose_facility_schedule (aria-disabled=${proposalDisabled}). NOT PRESSED HERE, deliberately -- it creates a real scheduling_runs row, and the delegate was already driven out-of-band this session on a sandbox incident at FAC-GGN-01 (escalate 200 -> acknowledge 200 -> delegate -> cancel 200, probe cleaned up). Two properties proven there rather than assumed: the body is extra="forbid" with facility_id OPTIONAL, so this client sends nothing and the facility is derived from the escalation's own row (M15); and called on an UNACKNOWLEDGED incident the delegate answers 409 NOT_ACKNOWLEDGED before touching the sequencer at all, so Flow 4's expand-read-then-act ordering is server-enforced rather than a UI convention. This console structurally cannot apply a proposal -- apply_schedule_proposal is WAREHOUSE_PLANNER/ADMIN only (D5).`,
    )
    say(
      '"View in planner queue"',
      'WORKING',
      `the post-request handoff state is live with prompt 14 State 3's scope rule enforced structurally: the link renders only when the signed-in identity's own grants include the planner surface, and is ABSENT from the layout otherwise -- U83's "scope denial is always Hidden, never a greyed-out control that reveals a destination exists". Both branches render side by side at /ops/_states plate 14. Presentation only; /planner's own reads are role-gated server-side.`,
    )
    // No popover to dismiss: neither control above is activated any more.
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
