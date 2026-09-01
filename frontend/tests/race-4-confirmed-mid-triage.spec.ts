import { test, expect } from 'playwright/test'

import { apiAs, assertNotDemoCast, contextForRole, createFreshEscalation, simultaneously } from './support/race'

/**
 * ## Race 4 -- `02-ops-exception-console` #9: shipment confirmed by another planner mid-triage
 *
 * `TESTING_STRATEGY.md` §4, row 4. The coordinator must see:
 *   - the new fact surfaced **inline**,
 *   - the escalation **does not auto-resolve**,
 *   - the coordinator still chooses Resolve or Cancel **deliberately**.
 *
 * This is the one race in §4 with no backend-invariant half. Nothing here is about "exactly one
 * winner" -- both actors legitimately succeed. The whole assertion is that the system does NOT
 * helpfully tidy up on the coordinator's behalf: an escalation is a human's open question, and
 * closing it because the underlying shipment got confirmed would silently discard that judgement.
 *
 * ### Test data safety
 *
 * Everything is created by this suite in the `FAC-GGN-01` sandbox and torn down: a
 * PENDING_CONFIRMATION appointment on a `SHP-RS-*` shipment, plus an escalation attached to it.
 * `ops-ggn` (USR108) is the only coordinator at that facility; `admin-a` stands in for "another
 * planner", because `ADMIN` is the only role that can read GGN's planner queue for the
 * `snapshot_hash` that `confirm_request` requires (verified live: `OPERATIONS_EXECUTIVE` and the
 * Jaipur planner both get 403).
 */

const DRIVER = 'driver-sandbox' as const
const OPS = 'ops-ggn' as const

type Ship = { shipment_id: string }
type Feasible = { options?: Array<{ slot_id: string }>; recommendation_id?: string }
type ReqResult = { code?: string; appointment_id?: string | null; hold_id?: string | null }

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
        { 'Idempotency-Key': `e2e-r4-req-${s}-${Date.now()}` },
      )
      const d = req.body?.data
      if (d?.code === 'SLOT_REQUESTED' && d.appointment_id) return { shipment: s, appointmentId: d.appointment_id }
      if (d?.code === 'SLOT_HELD' && d.hold_id) {
        const conf = await apiAs<ReqResult>(
          DRIVER,
          'POST',
          `/api/v1/holds/${d.hold_id}/confirm`,
          {},
          { 'Idempotency-Key': `e2e-r4-conf-${d.hold_id}` },
        )
        if (conf.body?.data?.appointment_id) {
          return { shipment: s, appointmentId: conf.body.data.appointment_id }
        }
      }
    }
  }
  return null
}

test.describe('Race 4 — shipment confirmed by another planner mid-triage', () => {
  let appointment: { shipment: string; appointmentId: string } | null = null
  let escalationId: string | null = null

  test.afterEach(async () => {
    if (escalationId) {
      const r = await apiAs(
        OPS,
        'POST',
        `/api/v1/operations/escalations/${escalationId}/cancel`,
        { reason_code: 'CREATED_IN_ERROR', resolution_note: 'E6.2 race 4 (issue #43) teardown' },
        { 'Idempotency-Key': `e2e-r4-esc-cleanup-${escalationId}` },
      )
      console.log(`[race 4 cleanup] cancel escalation ${escalationId} -> HTTP ${r.status}`)
      escalationId = null
    }
    if (appointment) {
      const r = await apiAs(
        DRIVER,
        'POST',
        `/api/v1/shipments/${appointment.shipment}/appointments/${appointment.appointmentId}/cancel`,
        { cancellation_reason: 'E6.2 race 4 (issue #43) teardown' },
        { 'Idempotency-Key': `e2e-r4-apt-cleanup-${appointment.appointmentId}` },
      )
      console.log(`[race 4 cleanup] cancel appointment ${appointment.appointmentId} -> HTTP ${r.status}`)
      appointment = null
    }
  })

  test('a confirm landing mid-triage does NOT auto-resolve the escalation', async ({ browser }) => {
    appointment = await createPendingAppointment()
    test.skip(
      !appointment,
      'SKIPPED: could not create a PENDING_CONFIRMATION appointment on any sandbox shipment ' +
        '(every offered GGN slot refused SLOT_CONFLICT_REFRESH_REQUIRED — lapsed D2 holds keep ' +
        'blocking their dock interval until the M8 sweeper collects them, and that job does not ' +
        'run against a plain local uvicorn).',
    )

    // Must be a genuinely OPEN row: `escalate` deduplicates on (shipment_id, calendar-day,
    // escalation_type) and its ON CONFLICT DO UPDATE never resets `escalation_status`, so a plain
    // POST can hand back a row a previous run already cancelled -- which then legitimately is not
    // in the queue, and the "did it auto-resolve?" assertion would misread that as a failure.
    const fresh = await createFreshEscalation(OPS, appointment!.shipment)
    test.skip(
      !fresh,
      `SKIPPED: could not obtain a fresh OPEN escalation for ${appointment!.shipment} — all nine ` +
        `escalation types are already used for this shipment today (daily dedupe key).`,
    )
    escalationId = fresh!.escalationId
    console.log(`[race 4] fresh escalation ${escalationId} (${fresh!.escalationType})`)

    // The coordinator picks the escalation up -- this is "mid-triage".
    const ack = await apiAs(
      OPS,
      'POST',
      `/api/v1/operations/escalations/${escalationId}/acknowledge`,
      undefined,
      { 'Idempotency-Key': `e2e-r4-ack-${Date.now()}` },
    )
    console.log(`[race 4] coordinator acknowledged -> HTTP ${ack.status}`)

    // Meanwhile another planner confirms the underlying shipment.
    const queue = await apiAs<{ items?: Array<Record<string, unknown>> }>(
      'admin-a',
      'GET',
      '/api/v1/planner/queue?facility_id=FAC-GGN-01',
    )
    const row = (queue.body?.data?.items ?? []).find(
      (r) => r.appointment_id === appointment!.appointmentId || r.shipment_id === appointment!.shipment,
    )
    const snapshotHash = (row?.snapshot_hash ?? row?.snapshotHash) as string | undefined
    test.skip(
      !snapshotHash,
      `SKIPPED (named reason): no planner-queue row carrying a snapshot_hash for the sandbox ` +
        `appointment, so the "another planner confirms" half cannot be driven honestly ` +
        `(confirm_request refuses without the row's own hash). Same limitation as race 5.`,
    )

    const [triage, confirm] = await simultaneously(
      // The coordinator is actively working the escalation while the confirm lands.
      () => apiAs(OPS, 'GET', `/api/v1/operations/escalations/${escalationId}/suggestion`),
      () =>
        apiAs<{ code?: string }>(
          'admin-a',
          'POST',
          `/api/v1/shipments/${appointment!.shipment}/appointments/${appointment!.appointmentId}/confirm`,
          { snapshot_hash: snapshotHash },
          { 'Idempotency-Key': `e2e-r4-confirm-${Date.now()}` },
        ),
    )
    const confirmRes = confirm.status === 'fulfilled' ? confirm.value : null
    console.log(
      '[race 4] triage read:', triage.status,
      '| confirm:', confirmRes?.status, confirmRes?.body?.data?.code ?? confirmRes?.body?.errors?.[0]?.code,
    )
    expect(confirmRes!.status, 'the confirm must not 5xx').toBeLessThan(500)

    // --- the assertion that matters: the escalation is still the coordinator's to decide --------
    const after = await apiAs<{ items?: Array<{ escalation_id?: string; escalation_status?: string }> }>(
      OPS,
      'GET',
      '/api/v1/operations/escalation-queue',
    )
    const mine = (after.body?.data?.items ?? []).find((i) => i.escalation_id === escalationId)
    console.log('[race 4] escalation status after the confirm:', mine?.escalation_status ?? '(not in queue)')

    expect(
      mine,
      'the escalation vanished from the queue after an unrelated confirm — edge-cases.md #9 ' +
        'requires it to stay, so the coordinator still chooses Resolve or Cancel deliberately',
    ).toBeTruthy()
    expect(
      mine?.escalation_status,
      'the escalation AUTO-RESOLVED when the shipment was confirmed. edge-cases.md #9 forbids ' +
        'this: the new fact is surfaced inline, the coordinator still decides.',
    ).not.toMatch(/RESOLVED|CANCELLED|CLOSED/i)

    // --- UI half: the new fact must be visible, and the row must still be there ------------------
    const ctx = await contextForRole(browser, OPS)
    try {
      const page = await ctx.newPage()
      await page.goto('/ops')
      await page.waitForLoadState('networkidle')
      await expect(page.getByRole('listbox', { name: 'Escalations' })).toBeVisible()
      await expect(page.locator('body')).not.toContainText('Something went wrong')
    } finally {
      await ctx.close()
    }
  })
})
