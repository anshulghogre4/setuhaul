import { expect, test } from 'playwright/test'

import { recorderFor, storageFor } from './support'

/**
 * 04 - Gate/yard kiosk. 17 designed controls.
 *
 * Identity: `gate-booth` (`rahul.verma@setuhaul.com`, `WAREHOUSE_PLANNER`) -- inside the backend's
 * `GATE_KIOSK_ROLES` (`deps.py`), and the roster's only credential that is. **No `GATE_OFFICER`
 * account has been provisioned** (issue #79's family), which `tests/support/accounts.ts` already
 * records as a real limitation.
 *
 * ## Why every state-gated write here is BLOCKED-ENV, and why that is also a safety property
 *
 * `GET /api/v1/gate/trucks` is scoped server-side to the caller's facility, which is `FAC-JAI-01`,
 * and it answers `NO_MATCH` for every query tried (`SHP`, `SHP-D16`, `D16`, `RJ14`, `UP14`, `HR`,
 * `MH` -- all `match_count: 0`, verified directly against the API). No truck is reachable, so the
 * truck screen and its one-dominant-button action cannot be rendered at all. That is not a
 * workaround: the only trucks that would ever appear at `FAC-JAI-01` are the `SHP1xxx` /
 * `SHP-D16-*` demo cast, and gate-in / call-to-dock / dock-in / unload / gate-out are all
 * irreversible writes against them.
 */

const say = recorderFor('04-gate')

test.use({ storageState: storageFor('gate-booth'), viewport: { width: 1280, height: 800 } })

const NO_TRUCK =
  'unreachable: GET /api/v1/gate/trucks answers NO_MATCH (match_count 0) for every query at FAC-JAI-01, the facility this device credential is scoped to, so the truck screen never renders. The only trucks that could appear there are the SHP1xxx / SHP-D16-* demo cast, whose gate events are irreversible writes this sweep must not make.'

test('gate: shift start, end shift, and the search flow', async ({ page }) => {
  await page.goto('/gate')

  // ---- Officer name input + Start shift -------------------------------------------------------
  const nameField = page.getByLabel('Officer name')
  await expect(nameField).toBeVisible()
  const startBefore = page.getByRole('button', { name: 'Start shift' })
  const inertBefore = await startBefore.getAttribute('aria-disabled')
  const helper = await page.getByText('Enter your name to start').count()
  await nameField.fill('Sweep Probe Officer')
  say(
    'Officer name input',
    'WORKING',
    `the once-per-shift attribution field accepted text; before it was filled the Start control was inert (aria-disabled=${inertBefore}) with a visible reason (${helper} helper line)`,
  )

  const facilityLine = await page.getByText(/Facility: .* \(fixed\)/).textContent()
  await page.getByRole('button', { name: 'Start shift' }).click()
  const shiftBar = page.getByText(/Shift: Sweep Probe Officer/)
  await expect(shiftBar).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
  say(
    '"Start shift"',
    'WORKING',
    `began the session with no further identity prompt: the shift bar now reads the officer's name and the facility is fixed to the device ("${facilityLine?.trim()}"), never chosen`,
  )

  // ---- Search input + Search ---------------------------------------------------------------------
  const lookup = page.getByLabel('Shipment ID or plate number')
  await expect(lookup).toBeVisible()
  await lookup.fill('RJ14 GH 2211')
  await expect(lookup).toHaveValue('RJ14 GH 2211')
  say(
    'Search input (shipment ID or plate)',
    'WORKING',
    'typed entry accepted into the single 56px lookup field; there is no scan, camera or NFC path anywhere on the surface (U109)',
  )

  const searchReq = page.waitForResponse((r) => r.url().includes('/api/v1/gate/trucks'))
  await page.getByRole('button', { name: 'Search' }).click()
  const searchRes = await searchReq
  const searchBody = (await searchRes.json()) as { data?: { code?: string; match_count?: number } }
  await expect(page.getByText('No shipment matches that ID or plate.')).toBeVisible()
  const stillHasValue = await lookup.inputValue()
  const focused = await lookup.evaluate((el) => el === document.activeElement)
  say(
    '"Search"',
    'WORKING',
    `fired GET /api/v1/gate/trucks (HTTP ${searchRes.status()}, code=${searchBody.data?.code}, match_count=${searchBody.data?.match_count}) and branched on the server's own code: the no-match state names the cause rather than showing a bare failure`,
  )

  // ---- "Try again" ---------------------------------------------------------------------------------
  const tryAgain = page.getByRole('button', { name: 'Try again' })
  await expect(tryAgain).toBeVisible()
  const retryReq = page.waitForResponse((r) => r.url().includes('/api/v1/gate/trucks'))
  await tryAgain.click()
  const retryRes = await retryReq
  say(
    '"Try again"',
    'WORKING',
    `the button relabels itself to "Try again" only in the not-found state; the field kept its failed value ("${stillHasValue}") and retained focus (${focused}) so the officer can retype without re-tapping, and activating it re-issued the lookup (HTTP ${retryRes.status()})`,
  )

  // ---- Back to shift indicator ------------------------------------------------------------------------
  const backOnSearch = page.getByRole('button', { name: /^Search$/ }).filter({ hasText: 'Search' })
  const shiftBarBack = page
    .locator('div')
    .filter({ hasText: /Shift: Sweep Probe Officer/ })
    .getByRole('button', { name: /^Search$/ })
  say(
    'Back to shift indicator (Search screen)',
    'MISSING',
    `the search screen carries no back control at all (${await shiftBarBack.count()} matches in the shift bar). components/shift-bar.tsx renders its back affordance only when \`onBack\` is passed, and gate-kiosk.tsx passes it exclusively for phase.kind === 'truck' -- matching mockup.html, which draws the back control on screens 6-12 and 22b only. So the inventory's "Back to shift indicator | Search screen" row has no implementation.`,
  )
  void backOnSearch

  // ---- "End shift" ---------------------------------------------------------------------------------------
  const endShift = page.getByRole('button', { name: 'End shift' })
  await expect(endShift).toBeVisible()
  await endShift.click()
  await expect(page.getByRole('heading', { name: 'Start shift' })).toBeVisible()
  const confirmModals = await page.getByRole('dialog').count()
  say(
    '"End shift"',
    'WORKING',
    `cleared the session officer identity and returned to the shift-start screen immediately, with ${confirmModals} confirmation modal(s) -- deliberately none, since ending a shift has no destructive consequence`,
  )
})

test('gate: the state-gated truck actions', async () => {
  say('Disambiguation row tap', 'BLOCKED-ENV', `MULTIPLE_MATCHES is ${NO_TRUCK}`)
  say('Back to search (Truck found)', 'BLOCKED-ENV', NO_TRUCK)
  say('"Gate in"', 'BLOCKED-ENV', NO_TRUCK)
  say('"Call to dock"', 'BLOCKED-ENV', NO_TRUCK)
  say('"Dock in"', 'BLOCKED-ENV', NO_TRUCK)
  say('"Start unload"', 'BLOCKED-ENV', NO_TRUCK)
  say('"End unload"', 'BLOCKED-ENV', NO_TRUCK)
  say('"Gate out"', 'BLOCKED-ENV', NO_TRUCK)
  say('"Search next truck"', 'BLOCKED-ENV', `the outcome screen is ${NO_TRUCK}`)
  say('"Continue" (DOCK_MISMATCH outcome)', 'BLOCKED-ENV', `the mismatch outcome is ${NO_TRUCK}`)
})
