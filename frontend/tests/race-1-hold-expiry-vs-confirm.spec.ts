import { test, expect } from 'playwright/test'

import { apiAs, assertNotDemoCast, contextForRole, simultaneously } from './support/race'

/**
 * ## Race 1 -- `01-driver-chat` #2: the hold expires as the driver taps confirm
 *
 * `TESTING_STRATEGY.md` §4, row 1. The loser must see:
 *   **exactly one outcome -- never both a lapse notice and a booking.**
 * (Backend half: §9.2 #2, which issue #42 owns via Locust.)
 *
 * ### What is real here and what is not -- stated rather than implied
 *
 * The **race itself is real**: two genuinely simultaneous `POST /api/v1/holds/{id}/confirm` calls
 * against a real D2 hold created by the write-safe sandbox driver, with the exclusion constraint
 * doing the arbitration. `holds.py:620` is what makes the loser's outcome `HOLD_ALREADY_ACTIONED`.
 *
 * The **UI half is asserted separately and more weakly**, and this is a genuine limitation of the
 * current frontend, not a shortcut: the driver surface has exactly two endpoints --
 * `GET /api/v1/driver/context` and `POST /api/v1/chat/stream` (verified by grep over
 * `features/driver/`). Every booking and confirm action is an **LLM tool call** through
 * `/chat/stream`. There is no deterministic UI affordance that confirms a hold, so "tap confirm at
 * the millisecond the hold lapses" cannot be driven from the browser reproducibly -- an LLM turn
 * is not a clock. What IS asserted from the browser is that the driver surface, reading the real
 * post-race `/driver/context`, renders **one** promise state and never both.
 *
 * ### The true expiry-vs-confirm timing variant
 *
 * A D2 hold lives 90 seconds. Racing confirm against the *lapse* therefore needs either a ~95s
 * wall-clock wait or an injectable clock -- `TESTING_STRATEGY.md` §9 item 3 flags exactly this
 * ("likely needs an injectable clock ... rather than timing luck"), and no such seam exists in
 * `backend/app/scheduling/holds.py`. The wall-clock version is implemented below but gated behind
 * `E2E_SLOW=1` so a normal run is not 2 minutes long. It is skipped with this reason, never
 * silently passed.
 */

const SANDBOX_DRIVER = 'driver-sandbox' as const

type Ship = { shipment_id: string }
type Feasible = { options?: Array<{ slot_id: string }>; recommendation_id?: string }
type RequestResult = { code?: string; hold?: { hold_id?: string } | null; hold_id?: string; appointment_id?: string }

async function sandboxShipments(): Promise<string[]> {
  const ctx = await apiAs<{ shipments?: Ship[] }>(SANDBOX_DRIVER, 'GET', '/api/v1/driver/context')
  return (ctx.body?.data?.shipments ?? []).map((s) => s.shipment_id)
}

/** Creates a real HELD hold on a sandbox shipment. Returns the hold id, or null if none was issued. */
async function createHold(shipmentId: string): Promise<{ holdId: string | null; code: string }> {
  assertNotDemoCast(shipmentId)
  const feasible = await apiAs<Feasible>(
    SANDBOX_DRIVER,
    'GET',
    `/api/v1/shipments/${shipmentId}/slots/feasible`,
  )
  const option = feasible.body?.data?.options?.[0]
  if (!option) return { holdId: null, code: 'NO_OPTIONS' }

  const res = await apiAs<RequestResult>(
    SANDBOX_DRIVER,
    'POST',
    `/api/v1/shipments/${shipmentId}/slots/${option.slot_id}/request`,
    { displayed_recommendation_id: feasible.body?.data?.recommendation_id ?? null },
    { 'Idempotency-Key': `e2e-r1-hold-${shipmentId}-${Date.now()}` },
  )
  const data = res.body?.data
  return { holdId: data?.hold?.hold_id ?? data?.hold_id ?? null, code: data?.code ?? '' }
}

/** Best-effort teardown: cancel whatever appointment the race produced on this shipment. */
async function cleanupShipment(shipmentId: string): Promise<void> {
  const status = await apiAs<{ appointment_id?: string | null }>(
    SANDBOX_DRIVER,
    'GET',
    `/api/v1/shipments/${shipmentId}/appointment-request/status`,
  )
  const appointmentId = status.body?.data?.appointment_id
  if (!appointmentId) {
    console.log(`[race 1 cleanup] ${shipmentId}: no appointment to cancel`)
    return
  }
  const res = await apiAs(
    SANDBOX_DRIVER,
    'POST',
    `/api/v1/shipments/${shipmentId}/appointments/${appointmentId}/cancel`,
    // `scheduling.py:45-49` -- CancelAppointmentBody forbids extras and requires
    // `cancellation_reason` (not `reason`), min_length 1.
    { cancellation_reason: 'E6.2 race 1 (issue #43) teardown' },
    { 'Idempotency-Key': `e2e-r1-cleanup-${appointmentId}` },
  )
  console.log(`[race 1 cleanup] cancel ${appointmentId} -> HTTP ${res.status}`)
}

test.describe('Race 1 — hold expiry vs confirm', () => {
  let usedShipment: string | null = null

  test.afterEach(async () => {
    if (usedShipment) await cleanupShipment(usedShipment)
    usedShipment = null
  })

  test('double confirm on one hold yields exactly one booking, never two', async ({ browser }) => {
    const ships = await sandboxShipments()
    const target = ships.find((s) => s === 'SHP-RS-OPEN') ?? ships[0]
    test.skip(
      !target,
      'SKIPPED: the reschedule sandbox driver (USR-RS-01) has no shipments. Seed it with ' +
        '`python supabase/demo/seed_reschedule_driver.py --confirm --with-auth`. This suite ' +
        'refuses to write to the SHP-D16-* demo cast.',
    )
    usedShipment = target

    const { holdId, code } = await createHold(target)
    test.skip(
      !holdId,
      `SKIPPED: no D2 hold was issued for ${target} (request_slot returned "${code}"). ` +
        `A HELD row requires TWO_PHASE_HOLD_ENABLED and a feasible slot; without one there is no ` +
        `hold to race a confirm against.`,
    )

    // Two simultaneous confirms of the SAME hold, distinct idempotency keys so the idempotency
    // layer cannot collapse them into one stored result (which would not be a race).
    const [first, second] = await simultaneously(
      () =>
        apiAs<{ code?: string }>(SANDBOX_DRIVER, 'POST', `/api/v1/holds/${holdId}/confirm`, {}, {
          'Idempotency-Key': `e2e-r1-c1-${Date.now()}`,
        }),
      () =>
        apiAs<{ code?: string }>(SANDBOX_DRIVER, 'POST', `/api/v1/holds/${holdId}/confirm`, {}, {
          'Idempotency-Key': `e2e-r1-c2-${Date.now()}`,
        }),
    )
    expect(first.status).toBe('fulfilled')
    expect(second.status).toBe('fulfilled')
    const a = first.status === 'fulfilled' ? first.value : null
    const b = second.status === 'fulfilled' ? second.value : null

    const codes = [a?.body?.data?.code ?? a?.body?.errors?.[0]?.code, b?.body?.data?.code ?? b?.body?.errors?.[0]?.code]
    console.log('[race 1] confirm outcome codes:', codes, 'statuses:', a?.status, b?.status)

    // §3a's zero-5xx rule: the refusal must be typed and explainable, not a crash.
    expect(a!.status, 'confirm A returned 5xx').toBeLessThan(500)
    expect(b!.status, 'confirm B returned 5xx').toBeLessThan(500)

    // "Exactly one outcome. Never both." -- at most one may report a successful booking.
    const booked = codes.filter((c) => c === 'CONFIRMED' || c === 'SLOT_REQUESTED' || c === 'PENDING_CONFIRMATION')
    expect(
      booked.length,
      `at most one confirm may produce a booking; got ${JSON.stringify(codes)}`,
    ).toBeLessThanOrEqual(1)
    expect(
      new Set(codes).size,
      `both confirms returned the same outcome ${JSON.stringify(codes)} -- one of them should ` +
        `have been refused (HOLD_ALREADY_ACTIONED / HOLD_EXPIRED)`,
    ).toBe(2)

    // --- UI half: the driver surface must show ONE promise state, never a lapse AND a booking ----
    const ctx = await contextForRole(browser, SANDBOX_DRIVER)
    try {
      const page = await ctx.newPage()
      await page.goto('/driver')
      await page.waitForLoadState('networkidle')
      const body = await page.locator('body').innerText()
      const saysLapsed = /lapsed|expired|no longer held/i.test(body)
      const saysBooked = /pending confirmation|confirmed|booked/i.test(body)
      console.log(`[race 1] driver surface — lapsed:${saysLapsed} booked:${saysBooked}`)
      expect(
        saysLapsed && saysBooked,
        'the driver surface showed BOTH a lapse notice and a booking — the exact "never both" ' +
          'failure edge-cases.md #2 forbids',
      ).toBe(false)
    } finally {
      await ctx.close()
    }
  })

  test('confirm AFTER the 90s hold lapses is refused, not double-applied', async () => {
    test.skip(
      process.env.E2E_SLOW !== '1',
      'SKIPPED (named reason): the true expiry-vs-confirm timing needs either a ~95s wall-clock ' +
        'wait or an injectable clock. TESTING_STRATEGY.md §9 item 3 flags this as an open item ' +
        '("likely needs an injectable clock ... rather than timing luck") and no such seam exists ' +
        'in backend/app/scheduling/holds.py. Run with E2E_SLOW=1 to execute the wall-clock version.',
    )
    test.setTimeout(180_000)

    const ships = await sandboxShipments()
    const target = ships.find((s) => s === 'SHP-RS-OPEN') ?? ships[0]
    test.skip(!target, 'SKIPPED: sandbox driver has no shipments.')
    usedShipment = target

    const { holdId, code } = await createHold(target)
    test.skip(!holdId, `SKIPPED: no hold issued (${code}).`)

    // D2 holds live 90s. Wait past that, then confirm.
    await new Promise((r) => setTimeout(r, 95_000))
    const res = await apiAs<{ code?: string }>(
      SANDBOX_DRIVER,
      'POST',
      `/api/v1/holds/${holdId}/confirm`,
      {},
      { 'Idempotency-Key': `e2e-r1-late-${Date.now()}` },
    )
    const outcome = res.body?.data?.code ?? res.body?.errors?.[0]?.code
    console.log('[race 1 slow] late confirm outcome:', outcome, 'HTTP', res.status)
    expect(res.status, 'a lapsed hold must refuse cleanly, not 5xx').toBeLessThan(500)
    expect(
      outcome,
      'confirming a lapsed hold must be refused with a typed code, not silently applied',
    ).toBe('HOLD_EXPIRED')
  })
})
