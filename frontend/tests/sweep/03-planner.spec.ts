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
  // Scoped to the HELD plate (fixture `ttl.hold_used: true`), not `.first()`: since #64 the Hold
  // button on an ordinary row is ENABLED, so the first match would report aria-disabled=null and
  // read as a regression when it is the opposite.
  const heldPlate = page.locator('figure').filter({ hasText: 'Hold for information — spent' })
  const holdBtn = heldPlate.getByRole('button', { name: /Hold .* for information/ }).first()
  const escBtn = page.getByRole('button', { name: /Escalate /, exact: false }).first()
  const holdTitle = await holdBtn.getAttribute('title')
  const holdAria = await holdBtn.getAttribute('aria-disabled')
  const escTitle = await escBtn.getAttribute('title')
  const escAria = await escBtn.getAttribute('aria-disabled')

  // ---- Issue #88: both displacement legs render, and neither prints "undefined" ------------------
  //
  // Driven on the gallery plate rather than live for the same structural reason as everything else
  // in this test, but this one is a genuine REGRESSION guard rather than a stand-in: the row it
  // renders carries an INTERVAL_CONFLICT and a DOCK_BLOCKED conflict at once, and DOCK_BLOCKED
  // carries no shipment_id at all. Before the fix `describeDisplacement` mapped `c.shipment_id`
  // over every entry, so this exact row rendered "Confirming this displaces undefined."
  const blockedPlate = page.locator('figure').filter({ hasText: 'both displacement legs' })
  await expect(blockedPlate).toBeVisible({ timeout: 30_000 })
  const displacementText = (await blockedPlate.locator('tr[data-appointment] td').nth(4).innerText())
    .replace(/\s+/g, ' ')
    .trim()

  expect(displacementText, 'a blocked dock must never render as an undefined shipment').not.toContain(
    'undefined',
  )
  expect(displacementText, 'the outage leg must be named as a block').toContain('blocked')

  say(
    'Displacement column — both #88 legs',
    'WORKING-ON-FIXTURE',
    `regression guard for issue #88's row-side change, fixed in features/planner this session. get_planner_queue's displacement.conflicts now carries BOTH legs the write path refuses on, each tagged with conflict_type (INTERVAL_CONFLICT | DOCK_BLOCKED, planner_service.py:200-217), and a DOCK_BLOCKED entry has NO shipment_id -- its field set is dock_event_id/dock_id/event_type/reason (scheduling/snapshot.py:323-327). lib/format.ts::describeDisplacement mapped c.shipment_id over every conflict, so a blocked dock rendered "Confirming this displaces undefined." in the column §7.3 calls "the single most important field". Now rendered as: "${displacementText}" -- two distinct sentences, because the two have different recoveries (a displacement is a harm the planner may still choose to cause; an outage is not something confirming can push through). lib/types.ts::QueueConflict is now a discriminated union, which caught a stale gallery fixture at compile time on the first build after the change. An absent conflict_type degrades to INTERVAL_CONFLICT, so an older backend renders as it did before rather than as undefined.`,
  )

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
  say(
    'Counter-offer (click or O)',
    'BLOCKED-ENV',
    `${NO_ROW} CHANGED THIS SESSION: the control's destination is now U103's board picker rather than the interim dialog -- queue-tab.tsx's openCounterOffer delegates to the console, which switches to the Board tab pinned to the row (screens.md §3's one sanctioned automatic tab switch). The dialog is retained and reachable by setting plannerBoardPickerEnabled=false, which is what makes that a one-line revert. See "Click an open interval on a dock" below for the picker's own evidence.`,
  )
  say(
    'Escalate (click or E)',
    'INACTIVE-LABELED',
    `not activatable live (${NO_ROW}) but the built QueueRow rendered at /planner/_states shows the control present, focusable and labelled: aria-disabled=${escAria}, title="${escTitle}". NOTE a real divergence from the design, which marks Escalate ungated ("No"): queue-row.tsx hard-codes \`inactive\` on it with no flag at all -- §7.5.1's escalate_request(appointment_id, reason) does not exist, and the shipped POST /operations/escalate has no escalation_type for "a planner needs help deciding this request".`,
  )
  say(
    'Hold for information (click or H)',
    'WORKING-ON-FIXTURE',
    `BUILT AND FLIPPED ON this session (issue #64; plannerHoldEnabled=true). The affordance is now live rather than Inactive: it opens a dialog with a MANDATORY question field (flows-and-states.md Flow 4 step 1, "H or click Hold -> mandatory question field"), commits POST /api/v1/shipments/{id}/appointments/{id}/hold-for-information with an Idempotency-Key, and H is bound on the focused row for the first time. The one-shot cap is PREVENTED, not handled: the row's own ttl.hold_used (new on get_planner_queue, = appointments.expires_at IS NOT NULL) disables the control before a second attempt can be made, which is edge-cases.md #6's explicit requirement ("there should be no error to handle if the UI does its job"); the 409 HOLD_ALREADY_USED is still classified and rendered, because another planner can hold the same row between render and press. Verified on the built QueueRow at /planner/_states over a hold_used=true fixture: aria-disabled=${holdAria}, title="${holdTitle}". A DIVERGENCE FROM U67 IS DELIBERATE AND FLAGGED: components.md §3 specifies a PAUSE whose numeric value "freezes and hides", but the shipped tool grants ONE BOUNDED EXTENSION (expires_at = now + N) and time keeps elapsing against the new deadline -- nothing pauses and nothing resumes. The row therefore takes U67's visual language (pause icon, neutral colour off the urgency scale) but KEEPS the number, because hiding it would assert that time has stopped when it has not, inverting U67's own stated reason for hiding it. Owner fork: accept extension semantics and correct U67's copy, or build real pause/resume server-side. Live activation not exercised: ${NO_ROW}`,
  )
  say('Single-key shortcuts C / R / O / H / E', 'BLOCKED-ENV', NO_ROW)

  // ---- Undo -----------------------------------------------------------------------------------
  say(
    'Undo (post-confirm toast, 5s)',
    'MISSING',
    'deliberately not built, and stated as such in source: queue-tab.tsx\'s doConfirm carries the comment "No Undo affordance. U41\'s 5-second undo depends on the driver notification being QUEUED and dispatched only when the window closes ... a server-side mechanism that does not exist." The success toast offers no reversal. NOT BUILT THIS SESSION either, and it is not a frontend gap: U41\'s undo is a HOLD-BACK, not a reversal -- the window exists so the driver notification is never dispatched, and cancelling a dispatch that already happened is not something any client can do. Building a button that "undid" a committed confirm after the driver had been told would be a lie about capacity AND about what the driver knows. NEEDS A DESIGN/BACKEND RULING, one of: (a) confirm_request queues the driver notification with a deferred dispatch and exposes a cancel path, which is real backend work; (b) U41 is scoped to only those actions that notify nobody; or (c) U41 is withdrawn for confirm and the toast stays terminal.',
  )

  // ---- Filter by priority / ETA confidence -----------------------------------------------------
  //
  // The control is live on /planner (it renders with an empty queue, since it sits in the toolbar
  // above the rows), but its NARROWING cannot be proven against a queue of zero rows. So it is
  // driven twice: once live for presence and wiring, and once at /planner/_states over fixture
  // rows through the SAME component and the SAME predicate the route uses -- which is that
  // gallery's stated reason for existing.
  const liveFilter = page.getByRole('button', { name: 'Filter by priority or ETA confidence' })
  await expect(liveFilter).toBeVisible()
  await liveFilter.click()
  const liveMenu = page.getByRole('menu')
  await expect(liveMenu).toBeVisible()
  const axes = await liveMenu.getByRole('menuitemradio').allTextContents()
  await page.keyboard.press('Escape')

  await page.goto('/planner/_states')
  const plate = page.locator('figure').filter({ hasText: 'Filter by priority or ETA confidence' })
  await expect(plate).toBeVisible({ timeout: 30_000 })
  const rowsBefore = await plate.locator('tr[data-appointment]').count()

  // "CRITICAL only" -- one of the design's own two stated use cases.
  await plate.getByRole('button', { name: 'Filter by priority or ETA confidence' }).click()
  await page.getByRole('menuitemradio', { name: 'CRITICAL' }).click()
  await page.keyboard.press('Escape')
  const rowsCritical = await plate.locator('tr[data-appointment]').count()
  const summaryCritical = (await plate.getByText(/^Filter:/).textContent())?.trim() ?? ''

  // "LOW confidence only" -- the other. Clearing priority first keeps the two axes independent.
  await plate.getByRole('button', { name: 'Clear' }).click()
  await plate.getByRole('button', { name: 'Filter by priority or ETA confidence' }).click()
  await page.getByRole('menuitemradio', { name: 'LOW', exact: true }).last().click()
  await page.keyboard.press('Escape')
  const rowsLowConfidence = await plate.locator('tr[data-appointment]').count()
  const summaryLow = (await plate.getByText(/^Filter:/).textContent())?.trim() ?? ''
  await page.goBack()

  say(
    'Filter by priority or ETA confidence',
    'WORKING',
    `built this session. LIVE on /planner: the toolbar now carries a Filter control (accessible name "Filter by priority or ETA confidence") offering ${axes.length} single-select options across two axes -- Any priority + LOW/NORMAL/HIGH/CRITICAL, Any confidence + LOW/MEDIUM/HIGH, both vocabularies copied from the schema's own CHECK constraints (setuhaul_baseline.sql:123 and :198), not from the artboards. Its narrowing cannot be exercised live for the structural reason stated at the top of this file (FAC-JAI-01 returns count 0), so it was driven at /planner/_states over fixture rows through the same QueueFilterControl and the same lib/queue-filter.ts predicate the route calls: ${rowsBefore} rows -> ${rowsCritical} on "CRITICAL only" ("${summaryCritical}") -> ${rowsLowConfidence} on "LOW ETA confidence only" ("${summaryLow}"). Both of the design's own stated use cases therefore narrow correctly. Faithful to screens.md §2 on three specifics: membership only and never the sort (a pure predicate over an already-ordered array -- it cannot reorder, because it never sees the comparator); NO chips, because §2 explicitly says none are needed at 15-35 rows and puts the state in the toolbar text instead ("Filter: CRITICAL · 6 shown", the exact format rendered above); and radiogroup rather than the ops queue's checkbox semantics, because a row has exactly one priority and at most one confidence. One judgement recorded in code: a row with confidence=null is EXCLUDED by an active confidence filter -- "no ETA on file" is not "its confidence is LOW".`,
  )
})

/**
 * **Hold for information -- the CONTRACT, exercised at the API rather than through the UI.**
 *
 * The UI path genuinely cannot be driven by this suite: `/planner` scopes to the signed-in
 * planner's own facility, `FAC-JAI-01`'s queue is empty, and the one pending appointment in the
 * system (`APT-C805418B046D` / `SHP-RS-PENDING`) sits at `FAC-GGN-01` where no
 * `WAREHOUSE_PLANNER` exists. So the button is proven on the gallery plate (above) and the two
 * behaviours the button depends on are proven here directly: that a hold **extends** the deadline
 * and marks it spent, and that a second attempt is **refused with a typed code** rather than
 * silently granting a second extension.
 *
 * `hold_for_information` is `OPS_PORTAL_ROLES`, so `ops-ggn` -- the coordinator who owns that
 * facility -- is the identity that can reach it, and is used here for that reason.
 *
 * ## Sandbox state, stated rather than hidden
 *
 * This write is **not reverted**: `expires_at` is the one-shot marker itself, so "undoing" it
 * would mean handing the request a second extension, which is precisely the thing the cap exists
 * to prevent and which no endpoint offers. `SHP-RS-PENDING` therefore carries a spent hold from
 * the first run of this test onward. That is accepted sandbox state (owner-sanctioned), and the
 * test is written to pass on every subsequent run by treating an already-spent hold as the
 * expected path rather than a failure.
 */
test('planner: hold for information — extension granted once, second attempt typed-refused', async () => {
  const SANDBOX_SHIPMENT = 'SHP-RS-PENDING'
  const SANDBOX_APPOINTMENT = 'APT-C805418B046D'
  const path = `/api/v1/shipments/${SANDBOX_SHIPMENT}/appointments/${SANDBOX_APPOINTMENT}/hold-for-information`

  const first = await apiAs<Record<string, unknown>>('ops-ggn', 'POST', path,
    { question: 'UI click-sweep probe — what is your revised ETA?' },
    { 'Idempotency-Key': `sweep-hold-${Date.now()}` },
  )

  if (first.status === 200) {
    const d = first.body?.data as Record<string, string> | undefined
    const grew = Date.parse(String(d?.new_deadline)) > Date.parse(String(d?.previous_deadline))
    expect(grew, 'the hold must move the deadline forward').toBe(true)
    expect(d?.hold_used).toBe(true)

    // The one-shot cap, proven rather than assumed.
    const second = await apiAs<Record<string, unknown>>('ops-ggn', 'POST', path,
      { question: 'UI click-sweep probe — second attempt, must be refused' },
      { 'Idempotency-Key': `sweep-hold-2-${Date.now()}` },
    )
    const code = (second.body?.errors ?? [])[0]?.code
    expect(second.status, 'a second hold must be refused').toBe(409)
    expect(code).toBe('HOLD_ALREADY_USED')

    say(
      'Hold for information — backend contract',
      'WORKING',
      `driven against the live stack. First call: POST ${path} -> HTTP 200, previous_deadline=${d?.previous_deadline} -> new_deadline=${d?.new_deadline} (extension_minutes=${d?.extension_minutes}, hold_used=${d?.hold_used}) -- the deadline genuinely moved FORWARD, which is what makes the row's "held" treatment an extension rather than a pause. Second call: HTTP ${second.status} code=${code}, i.e. the one-shot cap is enforced server-side and typed, so the UI's disabled-Hold is a convenience over a real guarantee rather than the only thing preventing a double extension. SANDBOX STATE, not reverted and not revertible: expires_at IS the one-shot marker, so undoing it would grant a second extension -- ${SANDBOX_SHIPMENT} carries a spent hold from now on, which is accepted sandbox state.`,
    )
  } else if (first.status === 404) {
    // The route exists in the tree (`routers/scheduling.py:414`) but not on the process answering
    // :8000 -- confirmed by reading the live OpenAPI document, whose only `hold` path is
    // `/api/v1/holds/{hold_id}/confirm`. That is a stale long-running uvicorn started before #64
    // landed, not a contract failure, and restarting it is out of this suite's scope (other
    // suites are holding sessions against it).
    say(
      'Hold for information — backend contract',
      'BLOCKED-ENV',
      `POST ${path} answered HTTP 404 because the RUNNING backend on :8000 predates issue #64: its live /openapi.json contains no hold-for-information path (only /api/v1/holds/{hold_id}/confirm). The route IS present in the tree at backend/app/api/v1/routers/scheduling.py:414 with allocation.hold_for_information behind it, and the frontend is wired to it. Re-run after the local backend is restarted; nothing was written.`,
    )
    return
  } else {
    const code = (first.body?.errors ?? [])[0]?.code
    expect(first.status, 'the only expected non-200 here is the one-shot refusal').toBe(409)
    expect(code).toBe('HOLD_ALREADY_USED')
    say(
      'Hold for information — backend contract',
      'WORKING',
      `driven against the live stack. ${SANDBOX_SHIPMENT}'s single extension was already spent by an earlier run of this test, so the FIRST call answered HTTP ${first.status} code=${code} -- which is itself the property under test: the cap is enforced server-side and typed, and it survives across sessions because it is the persisted expires_at marker rather than in-memory state. The grant path is proven by the run that first spent it.`,
    )
  }
})

/**
 * The URL seam between this client and the sequencer routes -- the one typo class neither
 * TypeScript nor pytest can see.
 *
 * Same check `adminPolicyEditorEnabled`'s own flag comment credits for catching a path mismatch:
 * compare the template literals in `features/planner/lib/api.ts` against the running app's own
 * OpenAPI path table. It exists because this client's FIRST guess at all three paths was wrong --
 * SS7.5.3 is a tool catalog and names no URLs, so `/planner/scheduling-runs*` was invented here and
 * the backend landed `/scheduling/*`. A compile-clean client calling a 404 is exactly what this
 * asserts against.
 */
test('planner: sequencer route contract — the URL seam', async ({ request }) => {
  const res = await request.get('http://127.0.0.1:8000/openapi.json')
  const spec = (await res.json()) as { paths?: Record<string, unknown> }
  const paths = Object.keys(spec.paths ?? {})

  // Exactly the three the client calls, plus the ops delegate the other surface calls.
  const wanted = [
    '/api/v1/scheduling/proposals',
    '/api/v1/scheduling/runs/{scheduling_run_id}',
    '/api/v1/scheduling/runs/{scheduling_run_id}/apply',
    '/api/v1/operations/escalations/{escalation_id}/sequencer-proposal',
  ]
  const present = wanted.filter((p) => paths.includes(p))
  const missing = wanted.filter((p) => !paths.includes(p))
  // The pending-run LIST the Board toolbar's count needs. Expected absent -- see below.
  const listPresent = paths.some((p) => p === '/api/v1/scheduling/runs')

  if (present.length === 0) {
    say(
      'Sequencer route contract (URL seam)',
      'BLOCKED-ENV',
      `the backend answering :8000 exposes ${paths.length} paths and NONE of the four sequencer routes, so the seam could not be driven. Re-run after a restart; nothing was written.`,
    )
    return
  }

  expect(missing, `client calls a path the server does not mount: ${missing.join(', ')}`).toEqual([])
  say(
    'Sequencer route contract (URL seam)',
    'WORKING',
    `all four sequencer paths this client calls are mounted by the running app (${paths.length} paths total): ${present.join(', ')}. Verified against the server's own OpenAPI table rather than by reading source on both sides -- the one typo class neither TypeScript nor pytest can see. This row EARNED its keep: the client's first guess at all three planner paths was /planner/scheduling-runs*, invented here because section 7.5.3 is a tool catalog and names no URLs; the backend landed /scheduling/*, and the client was corrected to it. The pending-run LIST is ${listPresent ? 'ALSO present, closing the catalog gap this build reported (screens.md section 3 needs a count that section 7.5.3 defines no read for)' : 'ABSENT'}.`,
  )
})

/**
 * The seam above proves the routes are MOUNTED. This one proves whether they WORK -- and the
 * distinction is the whole finding of this pass.
 *
 * Read-and-propose only. `propose_facility_schedule` writes a `scheduling_runs` row and nothing
 * else (D5: *"Sequencer output is a reviewable artifact, never a silent write"* -- no
 * `dock_occupancy`, no appointment, no notification), so it is safe against the demo cast. **No
 * apply is driven anywhere in this file**: an applied run rewrites real promises.
 */
test('planner: sequencer engine — live round trip', async ({ request }) => {
  const spec = (await (await request.get('http://127.0.0.1:8000/openapi.json')).json()) as {
    paths?: Record<string, unknown>
  }
  if (!Object.keys(spec.paths ?? {}).includes('/api/v1/scheduling/proposals')) {
    say('Sequencer engine — live round trip', 'BLOCKED-ENV', 'the route is not mounted on :8000.')
    return
  }

  const propose = await apiAs<Record<string, unknown>>('planner', 'POST', '/api/v1/scheduling/proposals', {
    facility_id: 'FAC-JAI-01',
  })
  const list = await apiAs<Record<string, unknown>>(
    'planner',
    'GET',
    '/api/v1/scheduling/runs?facility_id=FAC-JAI-01&status=PROPOSED',
  )
  const err = (propose.body?.errors ?? [])[0] as { code?: string; detail?: string } | undefined
  const detail = String(err?.detail ?? '')

  if (propose.status === 500 && detail.includes('scheduling_runs') && detail.includes('does not exist')) {
    say(
      'Sequencer engine — live round trip',
      'BLOCKED-ENV',
      `THE ROUTES ARE MOUNTED AND EVERY ONE OF THEM 500s. POST /api/v1/scheduling/proposals -> HTTP 500 INTERNAL_ERROR, and GET /api/v1/scheduling/runs -> HTTP ${list.status}, both with asyncpg UndefinedTableError: relation "public.scheduling_runs" does not exist. The ops delegate fails identically on an acknowledged sandbox incident at FAC-GGN-01 (probed separately; both probe incidents were cancelled, sandbox clean). CAUSE: supabase/migrations/20260902160000_scheduling_runs.sql is written but has NOT been applied to this database -- the code shipped, the schema did not. This is exactly why "the route appears in /openapi.json" was never accepted as evidence to flip sequencerProposalEnabled: a mounted route is not a working feature, and flipping would have put a 500 behind every control on the proposal path. The failing statement is the horizon sweep (UPDATE ... SET status='SUPERSEDED' ... WHERE horizon_end <= now) which runs BEFORE the insert, so the failure is total rather than partial and no half-written run can result. NOTHING WAS WRITTEN. Apply the migration and re-run this row.`,
    )
    return
  }

  const d = (propose.body?.data ?? {}) as Record<string, unknown>
  expect(propose.status, 'propose must answer 200 in both PROPOSED and RUN_ALREADY_ACTIVE').toBe(200)
  const runId = String(d.scheduling_run_id ?? '')
  expect(runId, 'a proposal must carry a run id').not.toBe('')

  const got = await apiAs<Record<string, unknown>>('planner', 'GET', `/api/v1/scheduling/runs/${runId}`)
  const g = (got.body?.data ?? {}) as Record<string, any>
  const l = (list.body?.data ?? {}) as Record<string, any>
  say(
    'Sequencer engine — live round trip',
    'WORKING',
    `driven against the live stack, READ AND PROPOSE ONLY -- no apply, so no promise moved. POST /scheduling/proposals -> HTTP 200 code=${String(d.code)}, run ${runId}, counts ${JSON.stringify(g.counts ?? d.counts)}, objective.churn_count=${g.objective?.churn_count} promises_moved=${g.objective?.promises_moved}. GET /scheduling/runs/${runId} -> HTTP ${got.status} replayed the SAME object (status=${g.status}, policy_version=${g.policy_version}, horizon ${g.horizon?.start_ts}..${g.horizon?.end_ts} end_reason=${g.horizon?.end_reason}) -- section 7.5.3's "replayable a month later". GET /scheduling/runs (list) -> HTTP ${list.status} count=${l.count}, which is the number "[ Review proposal (N) ]" renders. The proposal is left UN-APPLIED deliberately: that is the safe honest bar, since an applied run rewrites real driver promises.`,
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
    `renders as "${reviewLabel}" and activating it states the reason rather than doing nothing: "${reviewWhy.slice(0, 190)}". Gated by sequencerProposalEnabled=false (issue #49). The live branch now distinguishes THREE count states rather than two -- count>0 (active), count===0 (Inactive with "(0)", per screens.md section 3), and count===null meaning the server has no read that can answer. That third state is a real design gap, not a defensive branch: section 7.5.3 defines propose/apply/get_scheduling_run and NO list, yet screens.md section 3 requires a count and Flow 9 requires the button to go live for an ops-handoff run this surface never observes. Rendering "(0)" for an unanswerable count would tell a planner no proposal is waiting when one may be.`,
  )
  await page.keyboard.press('Escape')

  const gatedBySequencer = `BUILT and behind the sequencerProposalEnabled=false gate (issue #49). The overlay now exists -- features/planner/components/proposal-overlay.tsx renders section 5.1's diff on the board itself (unchanged/moved/newly placed/unplaceable), the objective incl. churn_count, and both named refusals -- and every state is mountable at /planner/_states plates 19/20/21 without a backend. What is still absent is the ENGINE: no sequencer route appears in the running backend's /openapi.json, so the flag stays off and "Review proposal" above is the labelled Inactive control that states the gap. Verified structurally rather than asserted: neither the moved list nor the infeasible list renders any per-row control, because apply_schedule_proposal has no per-row argument to wire one to.`
  say('Apply (proposal diff overlay)', 'INACTIVE-LABELED', gatedBySequencer)
  say('"Request a fresh proposal" (SNAPSHOT_DRIFT)', 'INACTIVE-LABELED', gatedBySequencer)
  say(
    'Partial-apply affordance (must NOT exist)',
    'NOT-IN-DESIGN',
    `asserted as an ABSENCE, which is the correct verdict here: section 7.5.3 deliberately omits an "apply these rows" argument ("cherry-picking produces a schedule nobody validated", section 5.1), and components.md section 7 turns that into a UI rule -- "the UI does not offer a control the tool doesn't support". proposal-overlay.tsx therefore renders the moved and infeasible lists as static <li> rows with no checkbox, no per-row button and no selection state, and applyScheduleProposal's signature takes only (run id, snapshot hash, idempotency key) so there is no parameter a future control could be wired into.`,
  )

  // ---- "Request re-sequence" (issue #102's deferred control) -------------------------------------
  const resequence = page.getByRole('button', { name: /Request re-sequence/i })
  await expect(resequence).toBeVisible()
  await resequence.click()
  const resequencePopover = page.getByRole('dialog', { name: "Why this isn't available" })
  await expect(resequencePopover).toBeVisible()
  const resequenceWhy = (await resequencePopover.textContent())?.replace(/\s+/g, ' ').trim() ?? ''
  say(
    '"Request re-sequence"',
    'INACTIVE-LABELED',
    `VERDICT CHANGE from MISSING (2026-09-01 sweep). The control now renders on the Board toolbar, is focusable, and activating it states its reason rather than doing nothing: "${resequenceWhy.slice(0, 190)}". Built per flows-and-states.md Flow 9, which specifies it as the planner-side trigger calling propose_facility_schedule with trigger_reason='PLANNER_REQUESTED' -- and the design's own caveat is preserved in the component header: section 7.3 frames re-sequencing as available but does not specify this control, so screens.md section 3's toolbar sketch shows only two buttons. Closes the planner half of issue #102's deferred list. Still Inactive because no sequencer route exists on the running backend.`,
  )
  await page.keyboard.press('Escape')

  // ---- Board interval click / picker cancel -------------------------------------------------------
  //
  // Same structural block as every other queue-row control: entering the picker requires pressing
  // Counter-offer on a queue row, and this identity's queue has none. The picker's own rendering is
  // therefore driven at /planner/_states, which mounts the real BoardPickerBanner and the real
  // Board (via BoardPlate) over fixture options -- and CANNOT write, because the counterOffer call
  // lives in DockBoardPanel, which the gallery never mounts.
  const lanes = page.getByRole('list', { name: /Dock occupancy/ })
  await expect(lanes).toBeVisible()
  const atRestButtons = await lanes.getByRole('button').count()

  await page.goto('/planner/_states')
  const pickerPlate = page.locator('figure').filter({ hasText: 'Counter-offer board picker' })
  await expect(pickerPlate).toBeVisible({ timeout: 30_000 })

  const banner = pickerPlate.getByRole('region', { name: 'Counter-offer picker' })
  await expect(banner).toBeVisible()
  const bannerText = (await banner.innerText()).replace(/\s+/g, ' ').trim()

  // Every clickable interval is a real button named "Offer <dock> · <date> · <interval>".
  const offers = pickerPlate.getByRole('button', { name: /^Offer / })
  const offerCount = await offers.count()
  const offerNames = await offers.allTextContents()

  // Ineligible lanes: dimmed via the muted/disabled TOKENS (issue #90's ruling -- never an opacity
  // multiplier) and marked aria-disabled, read off the DOM rather than from a screenshot.
  const ineligibleLanes = await pickerPlate
    .locator('[role="listitem"][data-ineligible="true"]')
    .count()
  const totalLanes = await pickerPlate.locator('[role="listitem"]').count()

  // Choosing an interval reveals the reason step -- counter_offer requires reason_code, which
  // screens.md §4's sketch omits.
  await offers.first().click()
  const pressed = await offers.first().getAttribute('aria-pressed')
  const reasonCount = await banner.getByRole('radio').count()
  const sendGate = await banner
    .getByRole('button', { name: /Send counter-offer/ })
    .getAttribute('aria-disabled')

  const cancel = banner.getByRole('button', { name: 'Cancel' })
  await expect(cancel).toBeVisible()
  await cancel.click()
  const clearedAfterCancel = await offers.first().getAttribute('aria-pressed')

  // Back to /planner, and RE-SELECT the Board tab. `goBack()` remounts `PlannerConsole`, whose
  // default tab is Queue -- so without this the rest of this test (the block-dock form, which
  // lives in the Board panel) would be looking for controls inside a `hidden` tabpanel.
  await page.goBack()
  await expect(page.getByRole('tab', { name: 'Board' })).toBeVisible({ timeout: 30_000 })
  const boardReread = page.waitForResponse((r) => r.url().includes('/api/v1/planner/board'))
  await page.getByRole('tab', { name: 'Board' }).click()
  await boardReread
  await expect(page.getByRole('tab', { name: 'Board' })).toHaveAttribute('aria-selected', 'true')

  say(
    'Click an open interval on a dock (counter-offer picker)',
    'WORKING-ON-FIXTURE',
    `built this session (plannerBoardPickerEnabled, features/planner/lib/flags.ts). The Board tab at rest still exposes ${atRestButtons} focusable bars and NO picker, which is correct -- the picker only exists while a row is being counter-offered. Driven at /planner/_states through the real components: the board renders ${offerCount} clickable open intervals as real buttons at their true lane positions [${offerNames.map((t) => t.trim()).join(' | ')}], each accessibly named "Offer <dock> · <date> · <interval>"; ${ineligibleLanes} of ${totalLanes} dock lanes carry data-ineligible="true" + aria-disabled and dim via the muted/disabled tokens (issue #90's ruling -- never an opacity multiplier, which would drag the bars' measured contrast below floor), which is screens.md §4's "ineligible docks dim and become unclickable" as components.md §18 Disabled rather than Inactive. Clicking an interval set aria-pressed=${pressed} and revealed the reason step (${reasonCount} controlled codes; Send gated aria-disabled=${sendGate} until one is chosen). U25 survives intact: nothing is draggable, there is no range-select, and these are the only interactive elements the board ever adds. HONEST BOUNDARIES, both stated in the banner rather than hidden: (1) lane eligibility is Stage 1's own answer projected onto lanes -- a lane is eligible exactly when find_feasible_slots returned an interval on it -- so the picker cannot say WHY an ineligible dock is ineligible (no read returns per-dock-per-shipment constraint failures); (2) the board's horizon is "four hours or to close", while Stage 1 searches further, so options beyond it cannot be plotted -- the banner COUNTS them ("1 of 3 feasible intervals fall outside this board's horizon") and points at the interim dialog, rather than silently dropping them. LIVE ACTIVATION NOT EXERCISED: ${NO_ROW}`,
  )
  say(
    'Cancel (picker banner)',
    'WORKING-ON-FIXTURE',
    `the pinned banner screens.md §4 requires is built and names the shipment it is picking for: "${bannerText.slice(0, 150)}…". Its Cancel is present in BOTH banner states (before and after an interval is chosen), which is the half of §4 that is not negotiable -- "must always have a clean way out without committing anything" -- and activating it cleared the chosen interval (aria-pressed ${pressed} -> ${clearedAfterCancel}). On the live route Cancel additionally drops the picking context and returns to the Queue tab, undoing the automatic switch that brought the planner to the Board (planner-console.tsx's onPickerCancel); that half needs a real queue row and is covered by the same block above.`,
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
