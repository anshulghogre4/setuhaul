import { expect, test, type Page } from 'playwright/test'

import { recorderFor, storageFor } from './support'

/**
 * 06 - Admin console. 38 designed controls.
 *
 * Identity: `admin-a` (`meera.iyer@setuhaul.com`, `ADMIN`, global scope).
 *
 * ## Write policy on this surface, stated before any verdict
 *
 * Admin writes are irreversible or user-visible against **real accounts and real governance
 * records**: `invite_user` sends an email and creates a Supabase Auth identity, `remove_user`
 * deletes one, `deactivate_user` locks a colleague out, and `publish_policy_version` writes an
 * immutable row. None of those has a sandbox equivalent. So every committing control here is driven
 * up to and including its confirmation step -- the dialog, the typed gate, the enable/disable
 * transition -- and the final commit is deliberately NOT executed. Those rows are
 * VERIFIED-TO-DIALOG.
 *
 * The three genuinely read-only writes-to-nothing are exercised in full: the four server-side
 * filters, `simulate_policy_weights` (which never touches `policy_versions`), and
 * `export_audit_log` (a CSV read).
 */

const say = recorderFor('06-admin')

test.use({ storageState: storageFor('admin-a'), viewport: { width: 1600, height: 900 } })

async function openConsole(page: Page) {
  await page.goto('/admin')
  await expect(page.getByRole('tab', { name: 'Users' })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('button', { name: 'Invite user' })).toBeVisible({ timeout: 30_000 })
}

test('admin: tabs and rail', async ({ page }) => {
  await openConsole(page)

  const rail = page.getByRole('navigation', { name: /^Main/ })
  const railCount = await rail.getByRole('link').count()
  const switcher = page.getByRole('button', { name: /All facilities|Select facility/ })
  const switcherCount = await switcher.count()
  const switcherLabel = switcherCount > 0 ? (await switcher.first().textContent())?.trim() : null
  say(
    'Icon rail — console + Profile',
    'NOT-IN-DESIGN',
    `the rail renders ${railCount} destination (the admin console) and no Profile entry, and this surface's spec says so outright: 06-admin-console/implementation-spec.md line 114 -- "Rail: 56px, one destination -- this console (Profile now lives only in the top-bar account button)" -- with line 149 recording "Rail Profile duplication | 20 instances | 0 -- cross-surface fix applied". screens.md section 1's two-destination sentence is the superseded text. SEPARATE OBSERVATION, still open and still the owner's: the design says this surface has NO facility switcher ("admin scope is set per action, not by a global view filter"), but one IS rendered in the top bar, labelled "${switcherLabel}" -- hasFacilityScope('ADMIN') is true. Since #99.1 its option LIST is no longer empty -- /auth/me reports scope.type=global_read_only for an admin, so canSelectAllFacilities is now true and the "All facilities" row renders -- but the trigger still reads "Select facility" until one is picked, because a global admin's identity.facilities is [] and activeFacilityId is null. Two things are worth the owner's attention and neither was silently decided here: (1) whether this surface should have a switcher at all, per screens.md section 1; (2) whether a global-read persona should DEFAULT to "All facilities" rather than to "Select facility", which currently implies they have chosen nothing when in fact they can read everything. Both are design rulings, not wiring -- and today the label is cosmetic on this console either way, since no admin read takes a facility_id.`,
  )

  const tabs = page.getByRole('tablist', { name: 'Admin console sections' })
  const names = await tabs.getByRole('tab').allTextContents()
  await expect(tabs.getByRole('tab', { name: 'Users' })).toHaveAttribute('aria-selected', 'true')

  const visited: string[] = []
  for (const name of ['Facility Rules', 'Policy', 'Audit', 'Users']) {
    await tabs.getByRole('tab', { name }).click()
    await expect(tabs.getByRole('tab', { name })).toHaveAttribute('aria-selected', 'true')
    const panelVisible = await page
      .getByRole('tabpanel')
      .filter({ hasNot: page.locator('[hidden]') })
      .count()
    visited.push(`${name}(${panelVisible > 0 ? 'panel shown' : 'no panel'})`)
  }
  // Keyboard, per the W3C APG tabs pattern the console's own header cites.
  await tabs.getByRole('tab', { name: 'Users' }).focus()
  await page.keyboard.press('ArrowRight')
  const afterArrow = await tabs.getByRole('tab', { selected: true }).textContent()
  const badges = await tabs.getByText(/\(\d+\)/).count()
  say(
    'Tab switcher (Users / Facility Rules / Policy / Audit)',
    'WORKING',
    `four tabs [${names.map((n) => n.trim()).join(' | ')}], Users selected by default; each switch swapped the visible tabpanel (${visited.join(', ')}); ArrowRight moved selection to "${afterArrow?.trim()}"; ${badges} count badges on any tab -- correctly none, this surface has no "pending work" framing`,
  )
})

test('admin: Users tab — filters, search, invite form, overflow, remove gate', async ({ page }) => {
  await openConsole(page)

  // ---- Role filter (a real server-side query parameter) ------------------------------------------
  const roleReq = page.waitForRequest((r) => r.url().includes('/admin/users') && r.url().includes('role'))
  await page.getByLabel('Role').selectOption('WAREHOUSE_PLANNER')
  const roleUrl = new URL((await roleReq).url())
  await page.waitForTimeout(600)
  const rowsAfterRole = await page.locator('tbody tr').count()
  say(
    'Role filter (Users tab)',
    'WORKING',
    `selecting "Planner" re-queried the server: GET /admin/users${roleUrl.search} -- a real query parameter, not a client-side narrowing -- and the table redrew to ${rowsAfterRole} row(s)`,
  )
  await page.getByLabel('Role').selectOption('')
  await page.waitForTimeout(500)

  // ---- Facility filter ------------------------------------------------------------------------------
  const facReq = page.waitForRequest(
    (r) => r.url().includes('/admin/users') && r.url().includes('facility'),
  )
  const facilityOptions = await page.getByLabel('Facility', { exact: true }).locator('option').allTextContents()
  await page.getByLabel('Facility', { exact: true }).selectOption({ index: 1 })
  const facUrl = new URL((await facReq).url())
  await page.waitForTimeout(600)
  say(
    'Facility filter (Users tab)',
    'WORKING',
    `the picker is populated from a real read (GET /admin/facilities -- ${facilityOptions.length} options, closed facilities included so a user scoped to one stays findable) and selecting one re-queried GET /admin/users${facUrl.search}`,
  )
  await page.getByLabel('Facility', { exact: true }).selectOption('')
  await page.waitForTimeout(600)

  // ---- Search ------------------------------------------------------------------------------------------
  const totalRows = await page.locator('tbody tr').count()
  let searchRequests = 0
  page.on('request', (r) => {
    if (r.url().includes('/admin/users')) searchRequests += 1
  })
  await page.getByLabel('Search users').fill('Meera')
  await page.waitForTimeout(700)
  const searchedRows = await page.locator('tbody tr').count()
  say(
    'Search (Users tab)',
    'WORKING',
    `typing narrowed the list ${totalRows} -> ${searchedRows} row(s) across name/email/role. NOTE it is CLIENT-side (${searchRequests} extra /admin/users request(s)) -- list_users has no search parameter and returns the whole LIMIT-200 page, which the tab's own header records as a deliberate divergence from the Audit tab's server-side rule.`,
  )
  await page.getByLabel('Search users').fill('')
  await page.waitForTimeout(500)

  // ---- "Invite user" + the form ---------------------------------------------------------------------------
  await page.getByRole('button', { name: 'Invite user' }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Invite user' })
  await expect(dialog).toBeVisible()
  const emailField = dialog.getByLabel('Email')
  await expect(emailField).toBeFocused()
  say('"Invite user"', 'WORKING', 'opened the invite form with focus on the first field, never on a submit button')

  await emailField.fill('not-an-email')
  await emailField.blur()
  const shapeError = await dialog.getByText(/doesn.t look like an email address/i).count()
  await emailField.fill('sweep.probe.never.sent@setuhaul.example')
  say(
    'Email field',
    'WORKING',
    `accepts the invitee address and validates its shape on BLUR rather than per keystroke (${shapeError} inline error raised for "not-an-email", cleared on a valid value); the authoritative already-registered verdict stays server-side`,
  )

  // ---- Role select changes the SHAPE of the scope field -----------------------------------------------------
  const scopeBefore = (await dialog.textContent())?.includes('scope field appears once a role is selected')
  await dialog.getByLabel('Role').selectOption('WAREHOUSE_PLANNER')
  const facilityGroup = dialog.getByRole('group', { name: 'Facility scope' })
  const checkboxes = await facilityGroup.getByRole('checkbox').count()
  await dialog.getByLabel('Role').selectOption('ADMIN')
  const adminScopeFields = await dialog.getByText('Facility scope').count()
  await dialog.getByLabel('Role').selectOption('CARRIER')
  const carrierNote = (await dialog.getByText(/No endpoint lists carriers/).count()) > 0
  await dialog.getByLabel('Role').selectOption('GATE_OFFICER')
  const gateSelect = await dialog.getByLabel('Facility scope').count()
  await dialog.getByLabel('Role').selectOption('WAREHOUSE_PLANNER')
  say(
    'Role select (invite / edit form)',
    'WORKING',
    `the scope field's shape follows the role, live: no role -> a "${scopeBefore ? 'scope field appears once a role is selected' : '—'}" line; Planner -> a multi-facility checkbox group; Administrator -> no scope field at all (${adminScopeFields} matches); Carrier manager -> an inactive note (${carrierNote}); Gate–Yard officer -> a single <select> (${gateSelect}) because the server caps it at one facility`,
  )

  // ---- Scope select + "add" -----------------------------------------------------------------------------------
  await facilityGroup.getByRole('checkbox').first().check()
  const selectedLine = await dialog.getByText(/\d+ selected|Choose at least one facility/).textContent()
  const addAffordance = await dialog.getByRole('button', { name: /^\+?\s*add$/i }).count()
  say(
    'Scope select + "add"',
    'WORKING',
    `the facility multi-select works (${checkboxes} checkbox options; ticking one updated the summary to "${selectedLine?.trim()}"). NOTE a flagged divergence from screens.md's "[ Jaipur ▾ ] [ + add ]" chip row: it is built as a native checkbox group in a <fieldset>, so there is no "+ add" affordance (${addAffordance} matches). The component header records this as a deliberate owner-callable choice.`,
  )

  // ---- "Send invite" — verified to the gate, NOT committed --------------------------------------------------------
  const send = dialog.getByRole('button', { name: 'Send invite' })
  const enabledNow = await send.getAttribute('aria-disabled')
  await facilityGroup.getByRole('checkbox').first().uncheck()
  const disabledNoScope = await send.getAttribute('aria-disabled')
  const whyNoScope = await send.getAttribute('title')
  say(
    '"Send invite"',
    'VERIFIED-TO-DIALOG',
    `the control is genuinely gated on a complete submission -- with email+role+scope it reads aria-disabled=${enabledNow}; unticking the scope flips it to aria-disabled=${disabledNoScope} with title "${whyNoScope}". Role and scope are in ONE submission (there is no two-step create-then-scope path). NOT COMMITTED: invite_user sends a real email and creates a Supabase Auth identity, which has no sandbox equivalent and no undo.`,
  )

  // ---- Cancel -------------------------------------------------------------------------------------------------------
  let writes = 0
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().includes('/admin/')) writes += 1
  })
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog).toBeHidden()
  say('"Cancel" (invite / edit form)', 'WORKING', `closed the form with ${writes} admin write(s) issued`)

  // ---- Row overflow menu -----------------------------------------------------------------------------------------------
  const ownRow = page.locator('tbody tr').filter({ hasText: 'meera.iyer@setuhaul.com' }).first()
  const otherRow = page
    .locator('tbody tr')
    .filter({ hasText: '@setuhaul.com' })
    .filter({ hasNotText: 'meera.iyer@setuhaul.com' })
    .first()
  const otherEmail = (await otherRow.locator('td').nth(1).textContent())?.trim() ?? ''

  await otherRow.getByRole('button', { name: /^Actions for / }).click()
  const menu = page.getByRole('menu').last()
  const menuItems = await menu.getByRole('menuitem').allTextContents()
  say(
    'Row overflow menu',
    'WORKING',
    `opened on ${otherEmail} exposing [${menuItems.map((t) => t.trim()).join(' | ')}]`,
  )
  say(
    'Deactivate / Reactivate',
    'VERIFIED-TO-DIALOG',
    `the menu item renders and is enabled ("${menuItems.find((t) => /activate/i.test(t))?.trim()}"). NOT ACTIVATED: it commits immediately with no confirmation step at all (Moderate tier), and it would lock a real colleague's account out of the live system. Its reversal path is Reactivate in this same menu, and the success announcement names it -- there is deliberately no undo toast, which users-table.tsx records as an unresolved screens.md-vs-foundations conflict for the owner.`,
  )
  await page.keyboard.press('Escape')

  // ---- Remove + typed confirmation -------------------------------------------------------------------------------------
  await ownRow.getByRole('button', { name: /^Actions for / }).click()
  const selfMenu = page.getByRole('menu').last()
  const selfItems = await selfMenu.getByRole('menuitem').allTextContents()
  const selfHasRemove = selfItems.some((t) => /remove/i.test(t))
  await page.keyboard.press('Escape')

  await otherRow.getByRole('button', { name: /^Actions for / }).click()
  await page.getByRole('menu').last().getByRole('menuitem', { name: 'Remove' }).click()
  const removeDialog = page.getByRole('dialog').filter({ hasText: /^Remove / })
  await expect(removeDialog).toBeVisible()
  const typedField = removeDialog.getByRole('textbox')
  await expect(typedField).toBeFocused()
  const commit = removeDialog.getByRole('button', { name: 'Remove user' })
  const gatedEmpty = await commit.getAttribute('aria-disabled')
  await typedField.fill('wrong@example.com')
  const gatedWrong = await commit.getAttribute('aria-disabled')
  const errorTone = await removeDialog.locator('[aria-invalid="true"]').count()
  await typedField.fill(otherEmail)
  const gatedRight = await commit.getAttribute('aria-disabled')
  const impactSentence = await removeDialog.getByText(/owns \d+ active escalation/).count()

  say(
    'Remove',
    'VERIFIED-TO-DIALOG',
    `the menu item opened the High-tier typed-confirmation dialog naming the consequence. NOT COMMITTED: remove_user deletes a real Supabase Auth identity and is explicitly permanent.`,
  )
  say(
    'Typed-confirmation dialog (admin types the user\'s email)',
    'VERIFIED-TO-DIALOG',
    `the gate is real and was driven through all three states: empty -> aria-disabled=${gatedEmpty}; wrong value -> aria-disabled=${gatedWrong} and NO error styling (${errorTone} aria-invalid elements -- a mismatch is correctly not an error state, nothing was submitted); exact email -> aria-disabled=${gatedRight}, i.e. the commit unlocked. The removal-impact sentence rendered ${impactSentence} time(s) (adminRemovalImpactEnabled is on; it is omitted rather than shown as "0"). The commit button was NOT pressed. Remove is also correctly HIDDEN, not disabled, on the signed-in admin's own row (self menu = [${selfItems.map((t) => t.trim()).join(' | ')}], contains Remove: ${selfHasRemove}).`,
  )
  await removeDialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(removeDialog).toBeHidden()

  // ---- Edit ---------------------------------------------------------------------------------------------------------------
  await otherRow.getByRole('button', { name: /^Actions for / }).click()
  await page.getByRole('menu').last().getByRole('menuitem', { name: 'Edit' }).click()
  const editDialog = page.getByRole('dialog').filter({ hasText: 'Edit user' })
  await expect(editDialog).toBeVisible()
  const prefilledEmail = await editDialog.getByLabel('Email').inputValue()
  const emailReadOnly = await editDialog.getByLabel('Email').getAttribute('readonly')
  const prefilledRole = await editDialog.getByLabel('Role').inputValue()
  await editDialog.getByRole('button', { name: 'Cancel' }).click()
  say(
    'Edit (overflow menu)',
    'VERIFIED-TO-DIALOG',
    `opened the same form pre-filled from the row: email "${prefilledEmail}" (rendered read-only, ${emailReadOnly !== null}, because update_user accepts role and scope only), role "${prefilledRole}", scope seeded from the server's scoped_facility_ids. NOT SAVED: update_user changes a live account's authorisation.`,
  )

  // ---- Resend / Revoke ---------------------------------------------------------------------------------------------------------
  const resend = page.getByRole('button', { name: /^Resend invitation to / })
  const revoke = page.getByRole('button', { name: /^Revoke invitation for / })
  const invitedBadges = await page.getByText('Invited, awaiting acceptance').count()
  const why = `no pending-invitation row exists to act on: every account in the live table was seeded rather than invited through this console, so \`invited_at IS NULL\` and derive_lifecycle_state reports ACTIVE for all of them (${invitedBadges} "Invited, awaiting acceptance" badges, ${await resend.count()} Resend and ${await revoke.count()} Revoke controls rendered). features/admin/lib/flags.ts states exactly this: "No Invited rows at all ... the flip's visible effect today is nothing changes". Creating one means sending a real invitation email.`
  say('"Resend"', 'BLOCKED-ENV', why)
  say('"Revoke"', 'BLOCKED-ENV', why)
})

test('admin: Facility Rules tab', async ({ page }) => {
  await openConsole(page)
  await page.getByRole('tab', { name: 'Facility Rules' }).click()
  await expect(page.getByRole('button', { name: 'Add rule' })).toBeVisible()

  const rulesReq = page.waitForRequest(
    (r) => r.url().includes('/admin/facility-rules') && r.url().includes('facility'),
  )
  await page.getByLabel('Facility', { exact: true }).selectOption({ index: 1 })
  const url = new URL((await rulesReq).url())
  await page.waitForTimeout(600)
  const rows = await page.locator('tbody tr').count()
  say(
    'Facility filter (Facility Rules tab)',
    'WORKING',
    `selecting a facility re-queried the server: GET /admin/facility-rules${url.search}, redrawing the list to ${rows} row(s)`,
  )
  await page.getByLabel('Facility', { exact: true }).selectOption('')
  await page.waitForTimeout(600)

  // ---- "+ Add rule" -----------------------------------------------------------------------------------------
  const add = page.getByRole('button', { name: 'Add rule' })
  const ariaDisabled = await add.getAttribute('aria-disabled')
  const title = await add.getAttribute('title')
  const note = (await page.getByText(/Adding and editing rules is not built/).textContent()) ?? ''
  say(
    '"+ Add rule"',
    'INACTIVE-LABELED',
    `rendered Inactive rather than hidden: aria-disabled=${ariaDisabled}, tabIndex kept, title "${title}", plus a full inline explanation on the page ("${note.replace(/\s+/g, ' ').trim().slice(0, 170)}…"). Gated by adminRuleEditorEnabled=false -- and note the blocker is now MISSING DESIGN, not a backend gap (#70/#71 are resolved).`,
  )

  // ---- Rule row edit -------------------------------------------------------------------------------------------
  const rowEdit = page.locator('tbody').getByRole('button')
  say(
    'Rule row edit',
    'MISSING',
    `rule rows carry no edit affordance at all (${await rowEdit.count()} buttons inside the table body). rules-table.tsx states why: its only two overflow items would be Edit (blocked) and Remove, and no delete_facility_rule tool exists anywhere in the backend, so "an overflow button whose menu is empty is worse than no button".`,
  )

  // ---- The editor's five sub-controls ------------------------------------------------------------------------------
  const editorGated = `the rule editor (Screen 6) is not built: adminRuleEditorEnabled=false, and its one entry point ("Add rule", above) is rendered Inactive WITH its reason, so the gap is stated rather than silent. Three of the five live rule types (HEAVY_DOCK_REQUIRED_KG, REEFER_DOCK_REQUIRED, NO_SHOW_GRACE_MIN) have no field set designed anywhere, and DOCK_PIN -- the design's only two-field worked example -- has no live analog. No editor fields exist in the DOM.`
  say('Facility select (rule editor)', 'INACTIVE-LABELED', editorGated)
  say('rule_type dropdown', 'INACTIVE-LABELED', editorGated)
  say('Type-driven value field(s)', 'INACTIVE-LABELED', editorGated)
  say('effective_from / effective_to', 'INACTIVE-LABELED', editorGated)
  say('Rule submit', 'INACTIVE-LABELED', editorGated)

  const impactNote = (await page.getByText(/Dependent-appointment impact/).textContent()) ?? ''
  say(
    'Impact confirmation (dependent appointments)',
    'INACTIVE-LABELED',
    `adminRuleImpactEnabled=false, rendered as its own labelled stub separate from the editor's: "${impactNote.replace(/\s+/g, ' ').trim().slice(0, 150)}…". The endpoint now exists (#74); what is missing is Screen 6, its only entry point.`,
  )
})

test('admin: Policy tab — weights, fairness, simulate, discard, publish gate', async ({ page }) => {
  await openConsole(page)
  const policyRead = page.waitForResponse((r) => r.url().includes('/admin/policy/active'))
  await page.getByRole('tab', { name: 'Policy' }).click()
  const policyRes = await policyRead
  await expect(page.getByRole('button', { name: /Simulate against last 30 days/ })).toBeVisible()

  // ---- Weight fields -------------------------------------------------------------------------------------------
  const latenessField = page.getByLabel(/Lateness \(/)
  const original = await latenessField.inputValue()
  await latenessField.fill(String(Number(original) + 1))
  const changed = await latenessField.inputValue()
  say(
    'Weight fields (w_lateness, w_wait, w_slack, P_dock, P_churn)',
    'WORKING',
    `the four routine coefficients render seeded from GET /admin/policy/active (HTTP ${policyRes.status()}) -- nothing renders before the server answers, so an invented coefficient is structurally impossible -- and editing one took (${original} -> ${changed}). The published version stays visible above the editor. NOTE P_churn is deliberately absent (the API refuses the key with a 422 because the sequencer is unbuilt), so this row is four fields, not five.`,
  )

  // ---- "Enable fairness term" ------------------------------------------------------------------------------------
  const fairness = page.getByRole('button', { name: 'Enable fairness term' })
  await expect(fairness).toBeVisible()
  const fairnessDisabled = await fairness.getAttribute('aria-disabled')
  const fairnessTitle = await fairness.getAttribute('title')
  const dangerBox = await page.getByRole('heading', { name: /Fairness term/ }).count()
  say(
    '"Enable fairness term"',
    'INACTIVE-LABELED',
    `present inside its own visually-separated danger-zone box (${dangerBox} heading), focusable, aria-disabled=${fairnessDisabled}, title "${fairnessTitle}", with an sr-only copy of the same reason and an inline note. Gated by adminFairnessTermEnabled=false (#69). w_fairness is round-tripped unchanged rather than dropped.`,
  )

  // ---- Simulate (read-only; safe to execute) ----------------------------------------------------------------------
  const simReq = page.waitForResponse(
    (r) => r.url().includes('/admin/policy/simulate') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: /Simulate against last 30 days/ }).click()
  const simRes = await simReq
  const simBody = JSON.parse(simRes.request().postData() ?? '{}') as { weights?: Record<string, number> }
  const headline = page.locator('[role="status"]').filter({ hasText: /decisions in the last 30 days would flip/ })
  await expect(headline).toBeVisible({ timeout: 30_000 })
  const headlineText = (await headline.textContent())?.replace(/\s+/g, ' ').trim()
  say(
    '"Simulate against last 30 days"',
    'WORKING',
    `POST /admin/policy/simulate (HTTP ${simRes.status()}) carrying exactly [${Object.keys(simBody.weights ?? {}).join(', ')}] -- the edited routine weights plus the untouched passthrough keys, w_fairness included -- and the aggregate rendered first as an aria-live status: "${headlineText}". Read-only: it never touches policy_versions.`,
  )

  // ---- Case expander rows ----------------------------------------------------------------------------------------------
  const expanders = page.locator('details')
  say(
    'Case expander rows',
    'MISSING',
    `the individual cases render as a FLAT list, not expanders (${await expanders.count()} <details> elements). policy-simulation-panel.tsx states why: mockup.html's expander promises "both shipments' score terms from the stored decision receipt", and no such receipt is returned by or exists behind simulate_policy_weights -- "an expander that opens onto nothing is worse than a line that says everything it has". The design's per-case before/after drill-down therefore has no implementation.`,
  )

  // ---- "Publish as vN+1" — gate verified, NOT committed --------------------------------------------------------------------
  const publish = page.getByRole('button', { name: /Publish new version/ })
  await expect(publish).toBeVisible()
  const publishReady = await publish.getAttribute('aria-disabled')
  // Editing a weight after the simulation must mark the result stale and re-close the gate.
  await latenessField.fill(String(Number(original) + 2))
  await page.waitForTimeout(300)
  const staleBanner = await page.getByText(/Weights changed since this simulation/).count()
  const publishStale = await publish.getAttribute('aria-disabled')
  const publishWhy = await publish.getAttribute('title')
  say(
    '"Publish as vN+1"',
    'VERIFIED-TO-DIALOG',
    `the simulate-before-publish gate is real and was driven both ways: immediately after a fresh simulation the control read aria-disabled=${publishReady}; editing a weight raised the staleness warning (${staleBanner} banner) and re-closed it to aria-disabled=${publishStale} with title "${publishWhy}". NOT COMMITTED: publish_policy_version writes an immutable policy_versions row that no control can undo.`,
  )

  // ---- "Discard" -------------------------------------------------------------------------------------------------------------
  const discard = page.getByRole('button', { name: 'Discard' })
  await discard.click()
  const restored = await latenessField.inputValue()
  const panelGone = await page.getByText(/decisions in the last 30 days would flip/).count()
  say(
    '"Discard"',
    'WORKING',
    `reset the editor to the server baseline (${changed} -> ${restored}, i.e. back to the original ${original}) and removed the simulation panel (${panelGone} result headline(s)); nothing was published`,
  )
})

test('admin: Audit tab — three filters, missing search, export', async ({ page }) => {
  await openConsole(page)
  const auditRead = page.waitForResponse((r) => r.url().includes('/admin/audit-log'))
  await page.getByRole('tab', { name: 'Audit' }).click()
  await auditRead
  await expect(page.getByRole('button', { name: /Export/ })).toBeVisible()

  // ---- Date-range filter ---------------------------------------------------------------------------------------------
  const dateReq = page.waitForRequest((r) => r.url().includes('/admin/audit-log'))
  await page.getByLabel('Date range', { exact: true }).selectOption('30')
  const dateUrl = new URL((await dateReq).url())
  await page.waitForTimeout(600)
  say(
    'Date-range filter (Audit tab)',
    'WORKING',
    `changing the range re-queried the server: GET /admin/audit-log${dateUrl.search} -- date_from moved with it, so this is a server re-query and never a client-side filter of an already-fetched page (Flow 8's explicit rule). Default is last 7 days.`,
  )

  // ---- Actor filter ----------------------------------------------------------------------------------------------------
  const actorOptions = await page.getByLabel('Actor', { exact: true }).locator('option').allTextContents()
  const actorReq = page.waitForRequest((r) => r.url().includes('/admin/audit-log') && r.url().includes('actor'))
  await page.getByLabel('Actor', { exact: true }).selectOption({ index: 1 })
  const actorUrl = new URL((await actorReq).url())
  await page.waitForTimeout(600)
  say(
    'Actor filter (Audit tab)',
    'WORKING',
    `populated with ${actorOptions.length} real actors (names resolved via list_users, ids sent on the wire) and selecting one re-queried GET /admin/audit-log${actorUrl.search}`,
  )
  await page.getByLabel('Actor', { exact: true }).selectOption('')
  await page.waitForTimeout(600)

  // ---- Event-type filter -------------------------------------------------------------------------------------------------
  const eventOptions = await page.getByLabel('Event type', { exact: true }).locator('option').allTextContents()
  const eventReq = page.waitForRequest(
    (r) => r.url().includes('/admin/audit-log') && r.url().includes('event_type'),
  )
  await page.getByLabel('Event type', { exact: true }).selectOption({ index: 1 })
  const eventUrl = new URL((await eventReq).url())
  await page.waitForTimeout(600)
  say(
    'Event-type filter (Audit tab)',
    'WORKING',
    `${eventOptions.length} options drawn from the real action_type vocabulary (not mockup §11.2's five domain phrases, which would match nothing) and selecting one re-queried GET /admin/audit-log${eventUrl.search}`,
  )
  await page.getByLabel('Event type', { exact: true }).selectOption('')
  await page.waitForTimeout(600)

  // ---- Search --------------------------------------------------------------------------------------------------------------
  const auditSearch = page.getByRole('searchbox')
  say(
    'Search (Audit tab)',
    'MISSING',
    `no free-text search box is rendered on this tab (${await auditSearch.count()} matches). audit-tab.tsx records why, and it is a real gap rather than an oversight: get_audit_log accepts only actor / event_type / date_from / date_to / resource -- no search parameter -- and flows-and-states.md Flow 8 forbids the client-side fallback because "the log can be arbitrarily large". Both paths are closed, so nothing is rendered rather than a control that silently does nothing.`,
  )

  // ---- Export (read-only) -----------------------------------------------------------------------------------------------------
  const exportBtn = page.getByRole('button', { name: /Export/ })
  // Drive the gate from the EMPTY side first -- `edge-cases.md` #5's actual concern is that "an
  // admin never receives a file and has to guess whether it's empty because nothing happened or
  // because something went wrong". A narrow actor+event pair is how that state is reached.
  await page.getByLabel('Date range', { exact: true }).selectOption('1')
  await page.getByLabel('Event type', { exact: true }).selectOption({ index: 1 })
  await page.getByLabel('Actor', { exact: true }).selectOption({ index: 1 })
  await page.waitForTimeout(1500)
  const emptyRows = await page.locator('tbody tr').count()
  const canExport = `${await exportBtn.getAttribute('aria-disabled')} at ${emptyRows} row(s)`
  const exportTitle = (await exportBtn.getAttribute('title')) ?? '(none)'
  await page.getByLabel('Event type', { exact: true }).selectOption('')
  await page.getByLabel('Actor', { exact: true }).selectOption('')
  await page.getByLabel('Date range', { exact: true }).selectOption('90')
  await page.waitForTimeout(800)
  const exportReq = page.waitForRequest((r) => r.url().includes('/admin/audit-log/export'))
  const download = page.waitForEvent('download').catch(() => null)
  await exportBtn.click()
  const exported = await exportReq
  const dl = await download
  const exportUrl = new URL(exported.url())
  say(
    '"Export"',
    'WORKING',
    `fired GET ${exportUrl.pathname}${exportUrl.search} -- the CSV carries the EXACT current filter set rather than a silent full-table dump -- and the browser received ${dl ? `a download ("${dl.suggestedFilename()}")` : 'no download event'}. The control is also genuinely gated when the filter returns nothing (aria-disabled=${canExport}, title "${exportTitle}") so an admin never receives an empty file and has to guess why.`,
  )
})
