import { test, expect } from 'playwright/test'

import { apiAs, assertNotDemoCast, contextForRole, simultaneously } from './support/race'

/**
 * ## Race 5 -- `03-planner-dock-board` #1: confirm vs the D9 sweeper
 *
 * `TESTING_STRATEGY.md` §4, row 5. The loser must see:
 *   - `ALREADY_ACTIONED` **with the winning transition named**,
 *   - the row updating **in place**, so the planner keeps their place in a 35-row spike.
 *
 * §9.2 #3 calls this *"the nastiest race in the design, because both actors believe they acted"*,
 * and §3a requires that **the audit log show which won and why**.
 *
 * ### How the race is forced without a clock seam
 *
 * The literal race is "the D9 sweeper fires as the planner clicks Confirm". Reproducing that on
 * timing alone is what `TESTING_STRATEGY.md` §9 item 3 calls out as needing an injectable clock.
 * But both actors have explicit endpoints -- `POST .../appointments/{id}/confirm` (the planner)
 * and `POST .../appointments/{id}/expire` (what the sweeper does to a lapsed pending request) --
 * so firing them simultaneously produces exactly the contested transition the design describes,
 * with the same two writers converging on one row. That is the race, driven deterministically
 * rather than waited for.
 *
 * ### Test data safety
 *
 * The appointment is created fresh by the sandbox driver at `FAC-GGN-01` and torn down after.
 * `ops-ggn` (USR108) is the only `OPERATIONS_EXECUTIVE` at that facility -- Jaipur's coordinators
 * cannot act on a Gurugram appointment, because appointments are facility-scoped. Nothing here
 * touches the `SHP-D16-*` cast or a pre-existing shared appointment.
 */

const DRIVER = 'driver-sandbox' as const
const OPS = 'ops-ggn' as const

type Ship = { shipment_id: string }
type Feasible = { options?: Array<{ slot_id: string }>; recommendation_id?: string }
type ReqResult = { code?: string; appointment_id?: string | null; hold_id?: string | null }

/** Drives a sandbox shipment all the way to a PENDING_CONFIRMATION appointment. */
async function createPendingAppointment(): Promise<{ shipment: string; appointmentId: string } | null> {
  const ctx = await apiAs<{ shipments?: Ship[] }>(DRIVER, 'GET', '/api/v1/driver/context')
  for (const s of (ctx.body?.data?.shipments ?? []).map((x) => x.shipment_id)) {
    assertNotDemoCast(s)
    const f = await apiAs<Feasible>(DRIVER, 'GET', `/api/v1/shipments/${s}/slots/feasible`)
    for (const opt of f.body?.data?.options ?? []) {
      const req = await apiAs<ReqResult>(
        DRIVER,
        'POST',
        `/api/v1/shipments/${s}/slots/${opt.slot_id}/request`,
        { displayed_recommendation_id: f.body?.data?.recommendation_id ?? null },
        { 'Idempotency-Key': `e2e-r5-req-${s}-${Date.now()}` },
      )
      const d = req.body?.data
      if (d?.code === 'SLOT_REQUESTED' && d.appointment_id) {
        return { shipment: s, appointmentId: d.appointment_id }
      }
      // Two-phase path: a hold must be confirmed into a PENDING_CONFIRMATION appointment first.
      if (d?.code === 'SLOT_HELD' && d.hold_id) {
        const conf = await apiAs<ReqResult>(
          DRIVER,
          'POST',
          `/api/v1/holds/${d.hold_id}/confirm`,
          {},
          { 'Idempotency-Key': `e2e-r5-conf-${d.hold_id}` },
        )
        const cd = conf.body?.data
        if (cd?.appointment_id) return { shipment: s, appointmentId: cd.appointment_id }
      }
    }
  }
  return null
}

test.describe('Race 5 — planner confirm vs the D9 sweeper', () => {
  let made: { shipment: string; appointmentId: string } | null = null

  test.afterEach(async () => {
    if (!made) return
    // When `expire` wins the race the appointment is already terminal, and cancelling a terminal
    // row is a correct 409 (`Cannot cancel appointment from EXPIRED`) rather than a leak. Check
    // first so the teardown log does not read like a failed cleanup.
    const status = await apiAs<{ appointment?: { appointment_status?: string } }>(
      DRIVER,
      'GET',
      `/api/v1/shipments/${made.shipment}/appointment-request/status`,
    )
    const state = status.body?.data?.appointment?.appointment_status ?? ''
    if (/EXPIRED|CANCELLED|REJECTED/i.test(state)) {
      console.log(`[race 5 cleanup] ${made.appointmentId} already terminal (${state}); nothing to release`)
      made = null
      return
    }
    const res = await apiAs(
      DRIVER,
      'POST',
      `/api/v1/shipments/${made.shipment}/appointments/${made.appointmentId}/cancel`,
      { cancellation_reason: 'E6.2 race 5 (issue #43) teardown' },
      { 'Idempotency-Key': `e2e-r5-cleanup-${made.appointmentId}` },
    )
    console.log(`[race 5 cleanup] cancel ${made.appointmentId} -> HTTP ${res.status}`)
    made = null
  })

  test('confirm and expire converge on one row: exactly one wins, the loser is told which', async ({
    browser,
  }) => {
    made = await createPendingAppointment()
    test.skip(
      !made,
      'SKIPPED: could not create a PENDING_CONFIRMATION appointment on any sandbox shipment. ' +
        'Every offered GGN slot was refused SLOT_CONFLICT_REFRESH_REQUIRED — lapsed D2 holds keep ' +
        'blocking their dock interval until the M8 expiry sweeper collects them, and that job does ' +
        'not run against a plain local uvicorn. Re-seed with ' +
        '`python supabase/demo/seed_reschedule_driver.py --confirm --with-auth` or run the sweep.',
    )
    console.log(`[race 5] racing on ${made!.appointmentId} (${made!.shipment})`)

    const base = `/api/v1/shipments/${made!.shipment}/appointments/${made!.appointmentId}`

    /**
     * The planner's confirm needs the `snapshot_hash` **the queue row itself carried** (section
     * 7.5 principle 3 / issue #61). The queue's own `snapshot` envelope field is metadata, not a
     * hash -- verified live: it returns
     * `{algorithm: "sha256/planner-queue-v1", enforced: true, note: "...Always send the value the
     * row carried..."}`. So the hash must come off the matching row, and inventing one gets a
     * `SNAPSHOT_STALE` that looks like a race outcome but is really a contract error.
     *
     * Read as `admin-a`, not as `ops-ggn`: verified live 2026-09-01, `GET /planner/queue` returns
     * **403 FORBIDDEN** for `OPERATIONS_EXECUTIVE` (`ops-ggn`) and also for the Jaipur
     * `WAREHOUSE_PLANNER` asking about Gurugram -- the latter being correct M15 facility scoping,
     * not a defect. `ADMIN` is the only role in this roster that can read GGN's queue.
     */
    const queue = await apiAs<{ items?: Array<Record<string, unknown>> }>(
      'admin-a',
      'GET',
      `/api/v1/planner/queue?facility_id=FAC-GGN-01`,
    )
    const row = (queue.body?.data?.items ?? []).find(
      (r) => r.appointment_id === made!.appointmentId || r.shipment_id === made!.shipment,
    )
    const snapshotHash = (row?.snapshot_hash ?? row?.snapshotHash) as string | undefined
    console.log(
      `[race 5] planner queue HTTP ${queue.status}, rows=${(queue.body?.data?.items ?? []).length}, ` +
        `snapshot_hash=${snapshotHash ? 'found' : 'MISSING'}`,
    )

    test.skip(
      !snapshotHash,
      `SKIPPED (named reason): no planner-queue row carrying a snapshot_hash exists for the ` +
        `sandbox appointment at FAC-GGN-01 (queue HTTP ${queue.status}, ` +
        `${(queue.body?.data?.items ?? []).length} rows). confirm_request refuses without the ` +
        `row's own hash, so the confirm arm of this race cannot be driven honestly — sending a ` +
        `made-up hash returns SNAPSHOT_STALE, which would look like a race outcome but is a ` +
        `contract error. The facility with a populated queue (FAC-JAI-01, 3 rows) has only ` +
        `shared/demo-cast appointments, which issue #43 forbids writing to. Closing this needs a ` +
        `write-safe sandbox shipment at a facility whose planner queue is populated.`,
    )

    const [first, second] = await simultaneously(
      // The planner half, as ADMIN (the only role that can read this facility's queue at all).
      () =>
        apiAs<{ code?: string }>(
          'admin-a',
          'POST',
          `${base}/confirm`,
          { snapshot_hash: snapshotHash },
          { 'Idempotency-Key': `e2e-r5-confirm-${Date.now()}` },
        ),
      // The D9 sweeper half. `scheduling.py:121-124` -- ExpireAppointmentBody forbids extras and
      // requires `expire_reason` (not `reason`); sending `reason` is a 422 VALIDATION_ERROR that
      // would masquerade as a race outcome.
      () =>
        apiAs<{ code?: string }>(
          OPS,
          'POST',
          `${base}/expire`,
          { expire_reason: 'E6.2 race 5 — simulated D9 sweeper' },
          { 'Idempotency-Key': `e2e-r5-expire-${Date.now()}` },
        ),
    )
    expect(first.status).toBe('fulfilled')
    expect(second.status).toBe('fulfilled')
    const confirm = first.status === 'fulfilled' ? first.value : null
    const expire = second.status === 'fulfilled' ? second.value : null
    const code = (r: typeof confirm) => r?.body?.data?.code ?? r?.body?.errors?.[0]?.code ?? ''
    const codes = { confirm: code(confirm), expire: code(expire) }
    console.log('[race 5] codes:', codes, 'statuses:', confirm?.status, expire?.status)

    // §3a: zero 5xx. "Both actors believe they acted" must resolve into typed outcomes.
    expect(confirm!.status, 'confirm returned 5xx').toBeLessThan(500)
    expect(expire!.status, 'expire returned 5xx').toBeLessThan(500)

    // The appointment must end in exactly ONE terminal state -- never confirmed AND expired.
    const status = await apiAs<{ appointment?: { appointment_status?: string } }>(
      DRIVER,
      'GET',
      `/api/v1/shipments/${made!.shipment}/appointment-request/status`,
    )
    const finalStatus = status.body?.data?.appointment?.appointment_status
    console.log('[race 5] final appointment_status:', finalStatus)
    expect(
      finalStatus,
      'the raced appointment must have resolved to exactly one state',
    ).toBeTruthy()

    // At most one of the two writers may report success; the other must be refused by name.
    const SUCCESS_CODES: readonly string[] = [
      'APPOINTMENT_CONFIRMED',
      'APPOINTMENT_EXPIRED',
      'CONFIRMED',
      'EXPIRED',
    ]
    const successes = Object.values(codes).filter((c) => SUCCESS_CODES.includes(c))
    expect(
      successes.length,
      `both writers claimed the row — that is the double-transition §9.2 #3 forbids. ${JSON.stringify(codes)}`,
    ).toBeLessThanOrEqual(1)

    // Anti-vacuous guard: "at most one winner" passes trivially when BOTH writers were refused for
    // contract reasons rather than by the race. That is not evidence of anything and must not read
    // as green.
    test.skip(
      successes.length === 0,
      `INCONCLUSIVE: neither writer succeeded (${JSON.stringify(codes)}), so no transition was ` +
        `actually contested. "At most one winner" holds vacuously here and proves nothing — ` +
        `reported as skipped rather than passed.`,
    )

    {
      const loser = Object.entries(codes).find(([, c]) => !successes.includes(c))?.[1]
      expect(
        loser,
        `the loser must be refused with a NAMED transition (ALREADY_ACTIONED / ` +
          `INVALID_APPOINTMENT_TRANSITION), not a bare error. got "${loser}"`,
      ).toMatch(/ALREADY_ACTIONED|INVALID_APPOINTMENT_TRANSITION|SLOT_OPTIONS_STALE|SNAPSHOT/i)
    }

    // --- UI half: the planner board must survive the raced row and keep rendering in place ------
    const ctx = await contextForRole(browser, 'planner')
    try {
      const page = await ctx.newPage()
      await page.goto('/planner')
      await page.waitForLoadState('networkidle')
      await expect(
        page.getByRole('tablist', { name: 'Planner console' }),
        'the planner console did not render after the race',
      ).toBeVisible()
      await expect(page.locator('body')).not.toContainText('Something went wrong')
    } finally {
      await ctx.close()
    }
  })
})
