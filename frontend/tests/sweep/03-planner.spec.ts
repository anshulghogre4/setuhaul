import { expect, test, type Page } from 'playwright/test'

import { recorderFor, storageFor, verifyFacilitySwitcher } from './support'
import { apiAs } from '../support/race'

/**
 * 03 - Planner dock board. 28 designed controls.
 *
 * Identity: `planner` (`rahul.verma@setuhaul.com`, `WAREHOUSE_PLANNER`, `FAC-JAI-01`) -- the
 * roster's only warehouse planner.
 *
 * ## The structural block on every queue-row control, stated once
 *
 * `PlannerConsole` reads its facility from the signed-in identity, so this console can only ever
 * show `FAC-JAI-01`. `GET /api/v1/planner/queue` for that facility returns `count: 0` (verified
 * live). The only pending appointment anywhere in the system is `APT-C805418B046D` /
 * `SHP-RS-PENDING` at `FAC-GGN-01` -- the write-safe sandbox -- and **no `WAREHOUSE_PLANNER` exists
 * at `FAC-GGN-01`**. `ADMIN` is inside `/planner`'s role gate but has `facility_id = null`, so
 * `resolve_facility_scope(..., require_facility=True)` answers 403 "Facility not in scope"
 * (verified live). Manufacturing a Jaipur row would mean writing to the `SHP1xxx` / `SHP-D16-*`
 * demo cast, which this sweep must not do.
 *
 * The one write exercised here is `block_dock`, on a deliberately empty window, reverted in the
 * same test.
 */

const say = recorderFor('03-planner')

test.use({ storageState: storageFor('planner'), viewport: { width: 1600, height: 900 } })

const NO_ROW =
  'no queue row exists to act on: /api/v1/planner/queue for FAC-JAI-01 (the only facility this identity can scope to) returns count 0, and the sole pending appointment in the system sits at FAC-GGN-01 where no WAREHOUSE_PLANNER account exists (ADMIN gets 403 "Facility not in scope"). Creating a Jaipur row would require writing to the demo cast.'

async function openConsole(page: Page) {
  await page.goto('/planner')
  // Gate on rendered content, not on a response predicate: the console mounts behind RequireAuth
  // and a slow /auth/me makes a response-wait fail for a reason that has nothing to do with the
  // control under test.
  await expect(page.getByRole('tab', { name: 'Queue' })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText(/pending/).first()).toBeVisible({ timeout: 30_000 })
}

test('planner: shell chrome and the two tabs', async ({ page }) => {
  await openConsole(page)

  const rail = page.getByRole('navigation', { name: /^Main/ })
  const railCount = await rail.getByRole('link').count()
  await rail.getByRole('link').first().click()
  await expect(page).toHaveURL(/\/planner$/)
  say(
    'Icon rail — console + Profile',
    'NOT-IN-DESIGN',
    `the console destination works (navigates to /planner, aria-current set) and the rail renders ${railCount} item(s) with no Profile entry -- which is the RESOLVED design. 03-planner-dock-board/screens.md section 1 asserts two destinations, but this surface's own implementation-spec.md section 6 Fork H records the ruling: "Resolved 2026-08-29: owner picked (a), drop the rail Profile item. Applied here too, not just to ops -- all 14 rail Profile links removed from this surface's mockup.html; the top-bar account control is the sole entry point. This decision now applies project-wide." Same finding as ops, and it is a correct build rather than a shared gap.`,
  )

  // ---- Facility switcher --------------------------------------------------------------------
  await verifyFacilitySwitcher(page, {
    say,
    control: 'Facility switcher',
    ownFacility: 'FAC-JAI-01',
    otherFacility: 'FAC-GGN-01',
    triggerName: /Jaipur|Gurugram|Select facility/,
    // The Queue tab is the default tab, so `get_planner_queue` is this surface's scoped read.
    scopedRead: '/api/v1/planner/queue',
    settle: async (p) => {
      await expect(p.getByRole('tab', { name: 'Queue' })).toBeVisible({ timeout: 30_000 })
    },
  })

  // ---- Queue / Board tabs -------------------------------------------------------------------
  const boardTab = page.getByRole('tab', { name: 'Board' })
  const boardRead = page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
  await boardTab.click()
  const boardRes = await boardRead
  await expect(boardTab).toHaveAttribute('aria-selected', 'true')
  say(
    'Board tab',
    'WORKING',
    `switching to Board selected the tab and triggered GET /api/v1/planner/board (HTTP ${boardRes.status()}); the lanes rendered`,
  )

  const queueTab = page.getByRole('tab', { name: 'Queue' })
  await queueTab.click()
  await expect(queueTab).toHaveAttribute('aria-selected', 'true')
  say('Queue tab', 'WORKING', 'switching back selected the Queue tab (the default tab on mount)')

  // ---- Top bar ------------------------------------------------------------------------------
  await page.keyboard.press('Control+k')
  const palette = page.getByRole('dialog').filter({ has: page.getByRole('searchbox') })
  await expect(palette).toBeVisible()
  await palette.getByRole('searchbox').fill('SHP')
  await page.waitForTimeout(250)
  const results = await palette.getByRole('link').count()
  await page.keyboard.press('Escape')

  const bell = page.getByRole('button', { name: /^Notifications,/ })
  await bell.click()
  await expect(page.locator('[data-radix-popper-content-wrapper]').first()).toBeVisible()
  await page.keyboard.press('Escape')
  const helpHref = await page.getByRole('link', { name: 'Contact support' }).getAttribute('href')
  await page.getByRole('button', { name: /^Account menu/ }).click()
  await expect(page.getByRole('menu', { name: 'Account' })).toBeVisible()
  await page.keyboard.press('Escape')
  say(
    'Search / bell / help / user menu',
    'WORKING-ON-FIXTURE',
    `palette opened on Cmd/Ctrl+K and filtered to ${results} fixture rows; the bell panel, the mailto help route (${helpHref}) and the account menu all opened. Notifications, search results and the pending count are fixture-backed by the documented CHROME SEAM.`,
  )
})

test('planner: queue-tab controls', async ({ page }) => {
  await openConsole(page)

  const count = await page.locator('tr[data-appointment]').count()
  expect(count).toBe(0)

  // Toolbar-level controls that DO render with an empty queue.
  const selectAll = page.getByRole('button', { name: /Select all eligible/ })
  const refresh = page.getByRole('button', { name: 'Refresh' })

  await expect(refresh).toBeVisible()
  const reread = page.waitForResponse((r) => r.url().includes('/api/v1/planner/queue'))
  await refresh.click()
  await reread

  /**
   * The five row affordances cannot be activated live, but their *labelling* can still be checked
   * against the built component: `/planner/_states` mounts the real `QueueRow` (not a copy of its
   * markup -- that is the gallery's stated reason for existing) against fixtures. Recorded as
   * gallery evidence, explicitly not as a live activation.
   */
  await page.goto('/planner/_states')
  await expect(page.getByRole('button', { name: /Hold .* for information/ }).first()).toBeVisible({
    timeout: 30_000,
  })
  const holdBtn = page.getByRole('button', { name: /Hold .* for information/ }).first()
  const escBtn = page.getByRole('button', { name: /Escalate /, exact: false }).first()
  const holdTitle = await holdBtn.getAttribute('title')
  const holdAria = await holdBtn.getAttribute('aria-disabled')
  const escTitle = await escBtn.getAttribute('title')
  const escAria = await escBtn.getAttribute('aria-disabled')
  await page.goBack()

  say('Row selection checkbox', 'BLOCKED-ENV', NO_ROW)
  say(
    '"Select all eligible (N)"',
    'BLOCKED-ENV',
    `${NO_ROW} The control is also conditionally rendered (${await selectAll.count()} present) -- queue-tab.tsx only emits it when eligibleIds.length > 0.`,
  )
  say('Bulk confirm', 'BLOCKED-ENV', NO_ROW)
  say('Confirm (click or C)', 'BLOCKED-ENV', NO_ROW)
  say('Reject (click or R)', 'BLOCKED-ENV', NO_ROW)
  say('Reject reason category / detail / preview / send', 'BLOCKED-ENV', NO_ROW)
  say('Counter-offer (click or O)', 'BLOCKED-ENV', NO_ROW)
  say(
    'Escalate (click or E)',
    'INACTIVE-LABELED',
    `not activatable live (${NO_ROW}) but the built QueueRow rendered at /planner/_states shows the control present, focusable and labelled: aria-disabled=${escAria}, title="${escTitle}". NOTE a real divergence from the design, which marks Escalate ungated ("No"): queue-row.tsx hard-codes \`inactive\` on it with no flag at all -- §7.5.1's escalate_request(appointment_id, reason) does not exist, and the shipped POST /operations/escalate has no escalation_type for "a planner needs help deciding this request".`,
  )
  say(
    'Hold for information (click or H)',
    'INACTIVE-LABELED',
    `not activatable live (${NO_ROW}) but the built QueueRow rendered at /planner/_states shows the control present, focusable and labelled: aria-disabled=${holdAria}, title="${holdTitle}". This is plannerHoldEnabled=false -- one of the six deliberately-off flags -- and it carries its reason, so the honest gate holds.`,
  )
  say('Single-key shortcuts C / R / O / H / E', 'BLOCKED-ENV', NO_ROW)

  // ---- Undo -----------------------------------------------------------------------------------
  say(
    'Undo (post-confirm toast, 5s)',
    'MISSING',
    'deliberately not built, and stated as such in source: queue-tab.tsx\'s doConfirm carries the comment "No Undo affordance. U41\'s 5-second undo depends on the driver notification being QUEUED and dispatched only when the window closes ... a server-side mechanism that does not exist." The success toast offers no reversal.',
  )

  // ---- Filter by priority / ETA confidence -----------------------------------------------------
  const toolbarText =
    (await page.getByText(/composite urgency/).first().textContent()) ?? '(sort caption not found)'
  say(
    'Filter by priority or ETA confidence',
    'MISSING',
    `the Queue toolbar renders only a free-text Search box, a Refresh button and the sort caption ("${toolbarText.replace(/\s+/g, ' ').trim().slice(0, 120)}"). No priority or ETA-confidence filter exists anywhere in features/planner, and the design's "Filter: CRITICAL · 6 shown" toolbar text has no implementation. (Search is present but is not the designed control.)`,
  )
})

test('planner: board tab — block a dock (written and reverted)', async ({ page }) => {
  await openConsole(page)
  const boardRead = page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
  await page.getByRole('tab', { name: 'Board' }).click()
  await boardRead

  // ---- "Review proposal (N)" ------------------------------------------------------------------
  const review = page.getByRole('button', { name: /Review proposal/ })
  await expect(review).toBeVisible()
  const reviewLabel = (await review.textContent())?.trim()
  await review.click()
  const reviewPopover = page.getByRole('dialog', { name: "Why this isn't available" })
  await expect(reviewPopover).toBeVisible()
  const reviewWhy = (await reviewPopover.textContent())?.replace(/\s+/g, ' ').trim() ?? ''
  say(
    '"Review proposal (N)"',
    'INACTIVE-LABELED',
    `renders as "${reviewLabel}" and activating it states the reason rather than doing nothing: "${reviewWhy.slice(0, 190)}". Gated by sequencerProposalEnabled=false (issue #49).`,
  )
  await page.keyboard.press('Escape')

  const gatedBySequencer = `behind the same sequencerProposalEnabled=false gate (issue #49); its only entry point is the proposal diff overlay, which is not built. "Review proposal (0)" above is the labelled Inactive control that states the gap.`
  say('Apply (proposal diff overlay)', 'INACTIVE-LABELED', gatedBySequencer)
  say('"Request a fresh proposal" (SNAPSHOT_DRIFT)', 'INACTIVE-LABELED', gatedBySequencer)

  // ---- "Request re-sequence" --------------------------------------------------------------------
  const resequence = page.getByRole('button', { name: /re-?sequence/i })
  say(
    '"Request re-sequence"',
    'MISSING',
    `no such control renders on the Board tab (${await resequence.count()} matches) and no propose_facility_schedule call site exists in features/planner/lib/api.ts. The Board toolbar holds exactly two controls: "Block a dock" and "Review proposal (0)". (The design itself flags this control as its own inference beyond §7.3.)`,
  )

  // ---- Board interval click / picker cancel -------------------------------------------------------
  const lanes = page.getByRole('list', { name: /Dock occupancy/ })
  await expect(lanes).toBeVisible()
  const clickableIntervals = await lanes.getByRole('button').count()
  say(
    'Click an open interval on a dock (counter-offer picker)',
    'MISSING',
    `the board renders lanes but nothing on it is activatable as an interval picker: ${clickableIntervals} buttons inside the dock-occupancy list. dock-board.tsx has no counter-offer mode at all -- its own header says the interactive picker (states 3/24/25) "is not built", and plannerCounterOfferEnabled's interim entry point is a dialog instead (features/planner/lib/flags.ts).`,
  )
  say(
    'Cancel (picker banner)',
    'MISSING',
    'there is no picker banner on the Board tab, because the board picker itself is not built (see above). The interim counter-offer dialog carries its own dismissal, but that is a different control from the design\'s pinned banner.',
  )

  // ---- "Block a dock" + the form -------------------------------------------------------------------
  await page.getByRole('button', { name: 'Block a dock' }).click()
  const form = page.getByRole('dialog').filter({ hasText: 'Block a dock' })
  await expect(form).toBeVisible()
  const dockSelect = form.getByLabel('Dock')
  await expect(dockSelect).toBeFocused()
  say(
    '"Block a dock"',
    'WORKING',
    'opened the block-dock form as a form (never a click-and-drag range select, per U107) with focus on the first field',
  )

  // Fill the fields and watch the affected-appointment set fetch LIVE, before submission.
  const options = await dockSelect.locator('option').allTextContents()
  await dockSelect.selectOption({ index: 1 })
  // A window nobody uses AND one this run has not used before: `end_dock_block` stamps an end time
  // rather than deleting the row, so re-blocking a previously-blocked window answers ALREADY_BLOCKED
  // and the success path would never be exercised on a second run. Minute-of-hour from the clock
  // keeps each run on a fresh slice of the small hours.
  const slice = new Date().getMinutes() % 50
  const from = `03:${String(slice).padStart(2, '0')}`
  const to = `03:${String(slice + 5).padStart(2, '0')}`
  await form.getByLabel('From').fill(from)
  await form.getByLabel('To').fill(to)
  const impact = await page.waitForResponse((r) => r.url().includes('/block-impact'))
  const impactBody = (await impact.json()) as { data?: { affected_count?: number } }
  const affected = impactBody.data?.affected_count ?? -1
  await expect(form.getByText(/No confirmed appointments in this window|confirmed appointment/i)).toBeVisible()
  say(
    'Block form fields (Dock, From, To, Reason)',
    'WORKING',
    `native <select> + two <input type="time"> + <textarea>; the dock list came from a real read (${options.length} options) and completing Dock/From/To fired GET .../block-impact (HTTP ${impact.status()}, affected_count=${affected}) BEFORE submission, which is Flow 7 step 2's live requirement rather than a deferred check`,
  )

  // A submit gate that is genuinely closed until the impact check has run for the current fields.
  const submit = form.getByRole('button', { name: /Block dock/ })
  const gatedNoReason = await submit.getAttribute('aria-disabled')
  const gateWhy = await submit.getAttribute('title')
  await form.getByLabel('Reason').fill('UI click-sweep probe — reverted immediately')

  // 03:00-03:30 was chosen precisely because it is empty; the run aborts rather than blocking a
  // window that would strand a real appointment.
  expect(affected, 'refusing to block a window with affected appointments').toBe(0)

  const blockRes = page.waitForResponse(
    (r) => r.url().includes('/block') && r.request().method() === 'POST',
  )
  await submit.click()
  const res = await blockRes
  const payload = (await res.json()) as {
    data?: { code?: string; dock_status_event_id?: string | null }
  }
  const eventId = payload.data?.dock_status_event_id ?? null
  const code = payload.data?.code
  say(
    '"Block dock" submit',
    'WORKING',
    `submit is gated until the impact check has run for the current field values (aria-disabled=${gatedNoReason}, title "${gateWhy}"); committing fired POST /api/v1/planner/docks/{id}/block for ${from}-${to} (HTTP ${res.status()}, code=${code}). ${
      eventId
        ? `A real outage window was created (dock_status_event_id=${eventId}) and REVERTED in this same test via POST /planner/dock-status-events/{id}/end.`
        : `The server answered ALREADY_BLOCKED, so NOTHING was written -- and that is itself the designed refusal: the form stayed open naming the conflicting block rather than closing on a failure.`
    }`,
  )

  // ---- REVERT ----------------------------------------------------------------------------------------
  if (eventId) {
    const undo = await apiAs(
      'planner',
      'POST',
      `/api/v1/planner/dock-status-events/${eventId}/end`,
    )
    console.log(`[sweep revert] end dock block ${eventId} -> HTTP ${undo.status}`)
    expect(undo.status, 'the block-dock write must be reverted').toBe(200)
  }

})

/**
 * "End dock block" (issue #100), driven entirely through the UI.
 *
 * ## Why this needs its own block rather than reusing the one above
 *
 * `GET /api/v1/planner/board` returns only the outage windows that **overlap the board's horizon**
 * (`planner_service._board_blocks`: `event_start_ts < window_end AND (event_end_ts IS NULL OR
 * event_end_ts > window_start)`), and the horizon is "the next four hours, or until closing time".
 * The block-dock form test above deliberately writes at 03:0x, a window nobody uses -- which is
 * almost always in the past, so it never appears in the board payload and no board-hosted control
 * could reach it. Proving the end-block affordance therefore needs a block placed INSIDE the
 * horizon, which is a different window and so a different write.
 *
 * ## Safety
 *
 * The window is 25 minutes out and five minutes long, and the form's own live impact check gates
 * it: if any confirmed appointment falls inside, the form is CANCELLED and nothing is written --
 * recorded as BLOCKED-ENV with the real count rather than blocking a real truck to make a test
 * pass. Whatever is written is ended in the same test, by the control under test, with an
 * out-of-band `apiAs` revert as the backstop if the UI path did not fire.
 */
test('planner: board tab — end a dock block through the UI', async ({ page }) => {
  await openConsole(page)
  const boardRead = page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
  await page.getByRole('tab', { name: 'Board' }).click()
  const boardPayload = (await (await boardRead).json()) as {
    data?: { horizon_end?: string; horizon_end_reason?: string }
  }
  const horizon = `${boardPayload.data?.horizon_end ?? 'unknown'} (${boardPayload.data?.horizon_end_reason ?? '?'})`

  // Local wall-clock, because the form's two <input type="time"> fields are local and
  // `toIsoWindow` combines them with today's local date.
  const start = new Date(Date.now() + 25 * 60_000)
  const end = new Date(start.getTime() + 5 * 60_000)
  const hhmm = (d: Date) =>
    `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`

  await page.getByRole('button', { name: 'Block a dock' }).click()
  const form = page.getByRole('dialog').filter({ hasText: 'Block a dock' })
  await expect(form).toBeVisible()
  await form.getByLabel('Dock').selectOption({ index: 1 })
  await form.getByLabel('From').fill(hhmm(start))
  await form.getByLabel('To').fill(hhmm(end))
  const impact = await page.waitForResponse((r) => r.url().includes('/block-impact'))
  const affected =
    ((await impact.json()) as { data?: { affected_count?: number } }).data?.affected_count ?? -1

  if (affected !== 0) {
    await form.getByRole('button', { name: 'Cancel' }).click()
    say(
      'End dock block',
      'BLOCKED-ENV',
      `refused to create the probe block: GET /block-impact reported affected_count=${affected} for ${hhmm(start)}-${hhmm(end)} on this dock, so blocking it would have stranded a real confirmed appointment. The form was cancelled and nothing was written. The control itself is built (features/planner/components/dock-board.tsx's Active blocks list) but cannot be exercised without a block inside the board horizon.`,
    )
    return
  }

  await form.getByLabel('Reason').fill('UI click-sweep probe — ended through the UI in this test')
  const blockRes = page.waitForResponse(
    (r) => r.url().includes('/block') && r.request().method() === 'POST',
  )
  await form.getByRole('button', { name: /Block dock/ }).click()
  const created = (await (await blockRes).json()) as {
    data?: { code?: string; dock_status_event_id?: string | null }
  }
  const eventId = created.data?.dock_status_event_id ?? null

  if (created.data?.code !== 'BLOCKED' || !eventId) {
    say(
      'End dock block',
      'BLOCKED-ENV',
      `could not create a probe block inside the board horizon to end: block_dock answered code=${created.data?.code ?? 'none'} for ${hhmm(start)}-${hhmm(end)} (ALREADY_BLOCKED means a previous run's window is still open on this dock). Nothing was written, so there is nothing to end.`,
    )
    return
  }

  let endedThroughUi = false
  try {
    // Flow 7 step 4: the board's outage layer updates immediately once the form closes. That is
    // now wired (`PlannerConsole` bumps `externalReloadToken` in `onBlocked`), and this wait is
    // what proves it -- before issue #100 the panel never re-read and the new block was invisible
    // until a tab switch.
    await page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
    const blocksList = page.getByRole('region', { name: 'Active blocks' })
    await expect(blocksList).toBeVisible({ timeout: 15_000 })
    const row = blocksList.getByRole('listitem').filter({ hasText: 'click-sweep probe' }).first()
    await expect(row).toBeVisible()
    const rowText = (await row.innerText()).replace(/\s+/g, ' ').trim()

    const endBtn = row.getByRole('button', { name: /^End the block on / })
    const expandedBefore = await endBtn.getAttribute('aria-expanded')
    await endBtn.click()
    const expandedAfter = await endBtn.getAttribute('aria-expanded')

    // U79: the safer action must come FIRST in DOM order, read off the document rather than
    // guessed at from visual position. The `aria-expanded` button is the row's own trigger (it
    // also reads "End block") and is excluded -- including it would compare the disclosure control
    // against the commit control, which is not the pair U79 is about.
    const order = await row.evaluate((el) =>
      Array.from(el.querySelectorAll('button'))
        .filter((b) => !b.hasAttribute('aria-expanded'))
        .map((b) => (b.textContent ?? '').trim())
        .filter((t) => t.length > 0),
    )
    const keepIdx = order.findIndex((t) => /keep it blocked/i.test(t))
    const endIdx = order.findIndex((t) => /^end block$/i.test(t))

    const endRes = page.waitForResponse(
      (r) => r.url().includes('/dock-status-events/') && r.url().endsWith('/end'),
    )
    await row.getByRole('button', { name: /^End block$/ }).click()
    const res = await endRes
    const payload = (await res.json()) as { data?: { code?: string } }
    endedThroughUi = res.status() === 200 && payload.data?.code === 'UNBLOCKED'

    // The board must re-read and the row must go, which is the visible half of `UNBLOCKED`.
    await expect(row).toBeHidden({ timeout: 15_000 })

    say(
      'End dock block',
      'WORKING',
      `the Board tab now carries an "Active blocks" list and its control ends the block. The block created moments earlier (${hhmm(start)}-${hhmm(end)}, dock_status_event_id=${eventId}) appeared in the list without a reload -- board re-read on block, which is Flow 7 step 4 and was NOT happening before -- rendering as "${rowText.slice(0, 120)}". Activating "End block" expanded an in-place confirmation (aria-expanded ${expandedBefore} -> ${expandedAfter}; no modal, per U41) whose buttons in DOM order are [${order.join(' | ')}], so the safer action precedes the committing one (U79: keepIt@${keepIdx} < endBlock@${endIdx} = ${keepIdx < endIdx}). Committing fired POST /api/v1/planner/dock-status-events/${eventId}/end (HTTP ${res.status()}, code=${payload.data?.code}) and the row disappeared on the board's own re-read. Boundary worth recording: board.blocks is horizon-filtered server-side (planner_service._board_blocks), so a block scheduled entirely outside the board's horizon (this run's horizon ended ${horizon}) still cannot be ended from this surface -- §7.5.1 has no "list active blocks" read to hang that on.`,
    )
  } finally {
    // Backstop. If the UI path did not complete for any reason, the probe block must still not
    // survive this test.
    if (!endedThroughUi) {
      const undo = await apiAs('planner', 'POST', `/api/v1/planner/dock-status-events/${eventId}/end`)
      console.log(`[sweep revert] end dock block ${eventId} -> HTTP ${undo.status}`)
      expect(undo.status, 'the probe block must be reverted').toBe(200)
    }
  }
})

test('planner: block-dock form Cancel writes nothing', async ({ page }) => {
  await openConsole(page)
  const boardRead = page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
  await page.getByRole('tab', { name: 'Board' }).click()
  await boardRead

  await page.getByRole('button', { name: 'Block a dock' }).click()
  const form = page.getByRole('dialog').filter({ hasText: 'Block a dock' })
  await expect(form).toBeVisible()

  let writes = 0
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().includes('/block')) writes += 1
  })
  // Fill the form fully, so Cancel is genuinely abandoning a submittable window rather than an
  // empty one -- "no partial counter-offer/block state exists" is the property under test.
  await form.getByLabel('Dock').selectOption({ index: 1 })
  await form.getByLabel('From').fill('04:00')
  await form.getByLabel('To').fill('04:30')
  await form.getByLabel('Reason').fill('UI click-sweep probe — cancelled, never submitted')
  await form.getByRole('button', { name: 'Cancel' }).click()
  await expect(form).toBeHidden()
  say(
    'Cancel (block form)',
    'WORKING',
    `a fully-filled form closed with ${writes} POST /block request(s) issued -- it writes nothing and leaves no partial block state`,
  )
})
