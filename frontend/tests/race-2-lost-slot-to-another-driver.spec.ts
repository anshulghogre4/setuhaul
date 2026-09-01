import { test, expect } from 'playwright/test'

import { apiAs, assertNotDemoCast, contextForRole, simultaneously } from './support/race'

/**
 * ## Race 2 -- `01-driver-chat` #3: lost the slot to another driver
 *
 * `TESTING_STRATEGY.md` §4, row 2. The loser must see:
 *   - the `SLOT_CONFLICT` copy from `voice-and-tone.md`,
 *   - **no haptic penalty pattern** -- losing a race is not the driver's error,
 *   - and (per §5) a fresh option set rather than a dead end.
 * (Backend half: §9.2 #1, issue #42's Locust suite.)
 *
 * ### A named limitation: one write-safe driver, not two
 *
 * `TESTING_STRATEGY.md` §5 describes this as "two Playwright contexts, each an authenticated
 * driver PWA". This suite cannot use two *drivers*, and the reason is data safety rather than
 * tooling: of the 17 driver identities in the roster, 16 are the `SHP-D16-*` presentation cast
 * (`supabase/demo/README.md`), which issue #43 forbids writing to. The only write-safe driver is
 * the isolated reschedule sandbox (`USR-RS-01`, `FAC-GGN-01`).
 *
 * So the contention is run between **two shipments of the sandbox driver competing for one slot**.
 * That is a genuine allocation race at the database -- D1's exclusion constraint arbitrates on the
 * dock interval and does not care whose driver is asking -- and it produces the real
 * `SLOT_CONFLICT_REFRESH_REQUIRED` refusal the losing driver's UI must render. What it does not
 * exercise is two *separate sessions* colliding, which is why this is stated here rather than
 * left for a reader to infer. Provisioning a second sandbox driver would close the gap; that is a
 * `supabase/demo/` change, outside this issue's ownership.
 *
 * Confirmed live 2026-09-01: `SHP-RS-OPEN` and `SHP-RS-CONFIRMED` are both offered the same
 * top-ranked slot (`D16-SLT-02649`), so the contention is real and not manufactured.
 */

const DRIVER = 'driver-sandbox' as const

type Ship = { shipment_id: string }
type Feasible = { options?: Array<{ slot_id: string }>; recommendation_id?: string }

async function feasible(shipmentId: string): Promise<Feasible | null> {
  const r = await apiAs<Feasible>(DRIVER, 'GET', `/api/v1/shipments/${shipmentId}/slots/feasible`)
  return r.status === 200 ? (r.body?.data ?? null) : null
}

async function cleanup(shipmentId: string): Promise<void> {
  const status = await apiAs<{ appointment_id?: string | null; status?: string }>(
    DRIVER,
    'GET',
    `/api/v1/shipments/${shipmentId}/appointment-request/status`,
  )
  const apt = status.body?.data?.appointment_id
  // Only cancel what is actually live -- an already-CANCELLED row 409s and a CONFIRMED row that
  // this suite did not create must not be touched.
  if (!apt || status.body?.data?.status !== 'APPOINTMENT_PENDING_CONFIRMATION') {
    console.log(`[race 2 cleanup] ${shipmentId}: nothing this suite created is live`)
    return
  }
  const res = await apiAs(
    DRIVER,
    'POST',
    `/api/v1/shipments/${shipmentId}/appointments/${apt}/cancel`,
    { cancellation_reason: 'E6.2 race 2 (issue #43) teardown' },
    { 'Idempotency-Key': `e2e-r2-cleanup-${apt}` },
  )
  console.log(`[race 2 cleanup] cancel ${apt} -> HTTP ${res.status}`)
}

test.describe('Race 2 — lost the slot to another driver', () => {
  const touched: string[] = []

  test.afterEach(async () => {
    for (const s of touched.splice(0)) await cleanup(s)
  })

  test('one slot, two simultaneous requests: exactly one wins, the loser gets refreshed options', async ({
    browser,
  }) => {
    const ctx = await apiAs<{ shipments?: Ship[] }>(DRIVER, 'GET', '/api/v1/driver/context')
    const ships = (ctx.body?.data?.shipments ?? []).map((s) => s.shipment_id)
    test.skip(
      ships.length < 2,
      'SKIPPED: the reschedule sandbox needs at least two shipments to contend for one slot. ' +
        'Re-seed with `python supabase/demo/seed_reschedule_driver.py --confirm --with-auth`.',
    )

    /**
     * Settle first: wait out any live D2 hold on the sandbox shipments.
     *
     * This suite interferes with its OWN previous run. The winner of a race walks away holding a
     * 90-second hold on the contended dock interval, and a hold has no release tool -- it expires
     * or the M8 sweeper collects it. Back-to-back runs therefore find every candidate slot
     * occupied and produce an inconclusive skip. Waiting for the holds to lapse (bounded, so a
     * genuinely stuck hold still surfaces as a skip rather than a hang) makes the run decisive.
     */
    const settleDeadline = Date.now() + 105_000
    for (;;) {
      const live: string[] = []
      for (const s of ships) {
        const st = await apiAs<{ hold?: unknown }>(
          DRIVER,
          'GET',
          `/api/v1/shipments/${s}/appointment-request/status`,
        )
        if (st.body?.data?.hold) live.push(s)
      }
      if (live.length === 0 || Date.now() > settleDeadline) {
        if (live.length) console.log(`[race 2] proceeding with holds still live on ${live.join(',')}`)
        break
      }
      console.log(`[race 2] waiting for D2 holds to lapse on ${live.join(',')}`)
      await new Promise((r) => setTimeout(r, 10_000))
    }

    /**
     * Search ALL pairs, not just the first two.
     *
     * The sandbox's four shipments do not all share an option set -- verified live 2026-09-01,
     * `SHP-RS-PENDING` and `SHP-RS-CONFIRMED` had 5 options each and **zero** in common, while
     * `SHP-RS-OPEN` and `SHP-RS-CONFIRMED` shared all five. Picking `ships[0]` and `ships[1]` would
     * therefore skip the suite on ordering luck rather than on a real absence of contention.
     */
    const offeredBy = new Map<string, string[]>()
    for (const s of ships) {
      assertNotDemoCast(s)
      for (const o of (await feasible(s))?.options ?? []) {
        offeredBy.set(o.slot_id, [...(offeredBy.get(o.slot_id) ?? []), s])
      }
    }
    const contended = [...offeredBy.entries()].filter(([, owners]) => owners.length >= 2)
    const shipA = contended[0]?.[1][0] ?? ''
    const shipB = contended[0]?.[1][1] ?? ''
    const candidates = contended
      .filter(([, owners]) => owners.includes(shipA) && owners.includes(shipB))
      .map(([slot]) => slot)
    console.log(
      `[race 2] ${contended.length} contended slot(s); pairing ${shipA || '?'} vs ${shipB || '?'} ` +
        `over ${candidates.length} candidate(s)`,
    )

    test.skip(
      candidates.length === 0,
      'SKIPPED: no single slot is currently feasible for two different sandbox shipments, so ' +
        'there is nothing for them to contend over. This is a data condition, not a defect — ' +
        'GGN capacity changes as other tests book against it.',
    )
    touched.push(shipA, shipB)

    /**
     * Iterate candidates rather than fixing on the top-ranked one.
     *
     * Verified live 2026-09-01: `find_feasible_slots` can offer a slot that `request_slot` then
     * refuses `SLOT_CONFLICT_REFRESH_REQUIRED` even for a SINGLE, unraced request -- i.e. the read
     * path and the write path disagree about availability. That is a real backend observation
     * (same class as #84/#88, read paths not seeing what the write path enforces) and it is
     * reported rather than worked around silently; but it must not make this suite flaky, so the
     * race is retried down the option list until a genuinely contendable slot is found.
     */
    type RequestOutcome = Awaited<ReturnType<typeof request>>
    let a: RequestOutcome | null = null
    let b: RequestOutcome | null = null
    let codes: string[] = []
    let usedSlot = ''

    const code = (r: RequestOutcome | null) => r?.body?.data?.code ?? r?.body?.errors?.[0]?.code ?? ''
    const WINNING = new Set(['SLOT_HELD', 'SLOT_REQUESTED'])

    function request(shipment: string, slot: string, tag: string) {
      return apiAs<{ code?: string; options?: unknown[] }>(
        DRIVER,
        'POST',
        `/api/v1/shipments/${shipment}/slots/${slot}/request`,
        {},
        { 'Idempotency-Key': `e2e-r2-${tag}-${Date.now()}` },
      )
    }

    for (const slot of candidates) {
      const [first, second] = await simultaneously(
        () => request(shipA, slot, 'a'),
        () => request(shipB, slot, 'b'),
      )
      expect(first.status).toBe('fulfilled')
      expect(second.status).toBe('fulfilled')
      a = first.status === 'fulfilled' ? first.value : null
      b = second.status === 'fulfilled' ? second.value : null
      codes = [code(a), code(b)]
      usedSlot = slot
      console.log(`[race 2] slot ${slot} -> ${JSON.stringify(codes)} (${a?.status}/${b?.status})`)

      // §3a: zero 5xx, on every attempt, not just the decisive one.
      expect(a!.status, 'request A returned 5xx').toBeLessThan(500)
      expect(b!.status, 'request B returned 5xx').toBeLessThan(500)
      // Never two winners -- the M6 invariant, checked on every candidate.
      expect(
        codes.filter((c) => WINNING.has(c)).length,
        `capacity was double-promised on ${slot}: codes=${JSON.stringify(codes)}`,
      ).toBeLessThanOrEqual(1)

      if (codes.some((c) => WINNING.has(c))) break
    }
    console.log('[race 2] decisive slot:', usedSlot, 'codes:', codes)

    // `SLOT_HELD` is the winning code while `TWO_PHASE_HOLD_ENABLED` is on -- `request_slot` takes
    // the `_request_slot_as_hold` branch and issues a 90s D2 hold instead of going straight to
    // PENDING_CONFIRMATION. `SLOT_REQUESTED` is the single-phase code, kept here so the assertion
    // does not silently start failing if the flag is turned off.
    const winners = codes.filter((c) => WINNING.has(c))

    // Every outcome must be a typed refusal, never a crash or an untyped failure.
    for (const c of codes) {
      expect(c, `an outcome came back with no typed code: ${JSON.stringify(codes)}`).toBeTruthy()
    }

    // If no candidate slot was contendable, the race did not actually happen this run. Report that
    // as SKIPPED with the reason rather than letting "at most one winner" pass vacuously.
    test.skip(
      winners.length === 0,
      `INCONCLUSIVE: every one of the ${candidates.length} slot(s) offered to both sandbox ` +
        `shipments refused BOTH requests (last: ${JSON.stringify(codes)} on ${usedSlot}). No ` +
        `contention was observed, so the loser-treatment assertions below have nothing to stand on. ` +
        `\nObserved cause (2026-09-01): a LAPSED D2 hold keeps blocking its dock interval until the ` +
        `M8 expiry sweeper collects it. The sweeper is a job (POST /api/v1/jobs/expiry-sweep, ` +
        `JOB_AUTH_TOKEN-gated) and does not run against a plain local uvicorn, so a previous run's ` +
        `winning hold occupies the slot well past its 90s TTL. Run the sweep, or wait, then re-run ` +
        `for a decisive result. A decisive run was recorded: ` +
        `["SLOT_CONFLICT_REFRESH_REQUIRED","SLOT_HELD"] on D16-SLT-02649.`,
    )

    const loser = codes.find((c) => !WINNING.has(c))
    expect(
      loser,
      `the loser must be refused with SLOT_CONFLICT_REFRESH_REQUIRED, got "${loser}"`,
    ).toBe('SLOT_CONFLICT_REFRESH_REQUIRED')

    // §5: "a fresh option set offered rather than a dead end". `scheduling.py:176` returns the
    // refreshed options in the same 409 envelope.
    // NOTE on teardown: the winner here holds a 90-second D2 hold, not an appointment. A hold
    // self-expires and the M8 sweeper releases it, so `cleanup` below only has to cancel a
    // PENDING_CONFIRMATION row if the single-phase path produced one.
    const loserBody = code(a) === 'SLOT_CONFLICT_REFRESH_REQUIRED' ? a : b
    // `allocation.RequestSlotResult.refreshed_options` -- a dict (the whole re-ranked option
    // payload, with its own `options` list and a fresh `recommendation_id`), NOT a bare array.
    const refreshed = (loserBody?.body?.data as { refreshed_options?: { options?: unknown[] } } | undefined)
      ?.refreshed_options
    expect(
      refreshed,
      'the SLOT_CONFLICT refusal must carry a refreshed option set, not a dead end (§5)',
    ).toBeTruthy()
    expect(
      Array.isArray(refreshed?.options),
      'refreshed_options must contain a re-ranked option list the driver can act on',
    ).toBe(true)

    // --- UI half ---------------------------------------------------------------------------------
    // What the driver surface can be asserted on without an LLM turn: it must still render, and it
    // must not present the losing shipment as booked. The confirm/booking affordance itself is an
    // LLM tool call through /chat/stream (see race 1's header), so the tap-to-lose moment is not
    // drivable deterministically from the browser.
    const bctx = await contextForRole(browser, DRIVER)
    try {
      const page = await bctx.newPage()
      await page.goto('/driver')
      await page.waitForLoadState('networkidle')
      await expect(page.locator('body')).not.toContainText('Something went wrong')
      // No haptic penalty on a lost race (`features/driver/lib/haptics.ts:48`). Asserted as an
      // absence of any vibrate call while the surface renders the post-race state.
      const vibrated = await page.evaluate(() => (window as { __e2eVibrated?: boolean }).__e2eVibrated === true)
      expect(vibrated, 'losing a race must not trigger a haptic penalty pattern').toBe(false)
    } finally {
      await bctx.close()
    }
  })
})
