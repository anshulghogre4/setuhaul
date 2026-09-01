import { expect, test, type Page } from 'playwright/test'

import { recorderFor, storageFor } from './support'
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
    'MISSING',
    `the console destination works (navigates to /planner, aria-current set) but the rail renders ${railCount} item(s) and carries no Profile entry -- icon-rail.tsx renders exactly one railDestinationFor(role). Same gap as ops.`,
  )

  // ---- Facility switcher --------------------------------------------------------------------
  const switcher = page.getByRole('button', { name: /Jaipur|Select facility/ })
  await switcher.click()
  const listbox = page.getByRole('listbox', { name: 'Facility' })
  await expect(listbox).toBeVisible()
  const options = await listbox.getByRole('option').count()
  const hasAll = await listbox.getByRole('option', { name: 'All facilities' }).count()
  const before = (await switcher.textContent())?.trim()
  let reqs = 0
  page.on('request', (r) => {
    if (r.url().includes('/api/v1/planner/')) reqs += 1
  })
  await listbox.getByRole('option').first().click()
  await page.waitForTimeout(600)
  const after = (await switcher.textContent())?.trim()
  say(
    'Facility switcher',
    'DEAD',
    `the trigger opens a real combobox (${options} option(s); "All facilities" correctly absent -- ${hasAll} matches -- per the single-facility rule), but selecting a facility does nothing: label "${before}" -> "${after}", ${reqs} planner read(s) re-issued. App.tsx's ShellRoute passes onFacilityChange={() => {}}.`,
  )
  await page.keyboard.press('Escape')

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

  // ---- End dock block ------------------------------------------------------------------------------
  say(
    'End dock block',
    'MISSING',
    'no UI control ends a block. `endDockBlock()` is exported from features/planner/lib/api.ts and has ZERO call sites anywhere in src/ (verified by grep); the board renders outage markers as non-interactive <span>s and there is no "Active blocks" list. So a block created here can only be ended out-of-band.',
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
