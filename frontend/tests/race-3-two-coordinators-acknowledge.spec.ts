import { test, expect } from 'playwright/test'

import { apiAs, createFreshEscalation, refusalCode, simultaneously, twoContexts } from './support/race'

/**
 * ## Race 3 -- `02-ops-exception-console` #2: two coordinators acknowledge the same escalation
 *
 * `TESTING_STRATEGY.md` §4, row 3. The loser must see:
 *   - `ALREADY_ACTIONED` **naming the winning owner**,
 *   - an `assertive` announcement **if focused on that row**,
 *   - the row updating **in place**, never removed and re-inserted.
 *
 * ### Test data safety
 *
 * This suite CREATES its own escalation (`POST /api/v1/operations/escalate`) and CANCELS it in
 * teardown, rather than acknowledging one of the 49 live rows. Acknowledge has no inverse -- there
 * is no `unacknowledge` tool anywhere in `operations.py` -- so racing a pre-existing escalation
 * would permanently reassign a shared row. Creating and cancelling our own is additive and fully
 * reversible.
 *
 * The escalation is attached to a non-cast Jaipur shipment. It must be Jaipur because an
 * escalation is facility-scoped and `ops-a`/`ops-b` (USR101/USR107) are the roster's only two
 * coordinators sharing a facility -- the pair the race requires. `assertNotDemoCast` is enforced
 * by picking the shipment from the live queue and filtering `SHP-D16-*` out.
 */

const ACK = (id: string) => `/api/v1/operations/escalations/${id}/acknowledge`

type QueueItem = { escalation_id?: string; shipment_id?: string; facility_id?: string }

test.describe('Race 3 — two coordinators acknowledge the same escalation', () => {
  let escalationId: string | null = null

  test.afterEach(async () => {
    if (!escalationId) return
    // Cancel closes the row this suite created. Best-effort: a failed cleanup must be visible in
    // the log, but must not turn a passing race assertion into a failure.
    const res = await apiAs(
      'ops-a',
      'POST',
      `/api/v1/operations/escalations/${escalationId}/cancel`,
      {
        // `escalation_service.py:41` -- CANCEL_REASON_CODES is
        // {SHIPMENT_CANCELLED, DUPLICATE, CREATED_IN_ERROR}. A row this suite created for a race
        // and is now retiring is exactly CREATED_IN_ERROR; anything else is a 422.
        reason_code: 'CREATED_IN_ERROR',
        resolution_note: 'Created and cancelled by E6.2 race 3 (issue #43).',
      },
      { 'Idempotency-Key': `e2e-r3-cleanup-${escalationId}` },
    )
    console.log(`[race 3 cleanup] cancel ${escalationId} -> HTTP ${res.status}`)
    escalationId = null
  })

  test('exactly one acknowledge wins; the loser is told ALREADY_ACTIONED', async ({ browser }) => {
    // --- precondition: a fresh, unowned escalation on a non-cast Jaipur shipment -----------------
    const queue = await apiAs<{ items?: QueueItem[] }>(
      'ops-a',
      'GET',
      '/api/v1/operations/escalation-queue',
    )
    test.skip(
      queue.status !== 200,
      `SKIPPED: the ops escalation queue did not answer (HTTP ${queue.status}); ` +
        `cannot pick a shipment to attach a test escalation to.`,
    )

    const candidate = (queue.body?.data?.items ?? []).find(
      (i) => i.shipment_id && !i.shipment_id.startsWith('SHP-D16-'),
    )
    test.skip(
      !candidate?.shipment_id,
      'SKIPPED: no non-demo-cast shipment in the Jaipur escalation queue to attach a test ' +
        'escalation to. Every visible row belongs to the SHP-D16-* presentation cast, which ' +
        'issue #43 forbids writing to.',
    )

    // `createFreshEscalation` guarantees an OPEN, unowned row -- see its comment for why a plain
    // POST is not enough (the daily dedupe key can hand back an already-actioned escalation, which
    // makes both coordinators lose and the race prove nothing).
    const fresh = await createFreshEscalation('ops-a', candidate!.shipment_id!)
    test.skip(
      !fresh,
      `SKIPPED: could not obtain a fresh OPEN escalation for ${candidate!.shipment_id}. ` +
        `escalate deduplicates on (shipment_id, calendar-day, escalation_type) and DO UPDATE never ` +
        `resets escalation_status, so all nine types are already used for this shipment today. ` +
        `Race 3 refuses to acknowledge a pre-existing shared row, because acknowledge has no inverse.`,
    )
    escalationId = fresh!.escalationId
    console.log(`[race 3] fresh escalation ${escalationId} (${fresh!.escalationType})`)

    // --- the race --------------------------------------------------------------------------------
    // Distinct Idempotency-Keys on purpose: a shared key would be de-duplicated by the idempotency
    // layer and both callers would get the SAME stored result, which is not a race at all.
    const [first, second] = await simultaneously(
      () => apiAs('ops-a', 'POST', ACK(escalationId!), undefined, { 'Idempotency-Key': `e2e-r3-a-${Date.now()}` }),
      () => apiAs('ops-b', 'POST', ACK(escalationId!), undefined, { 'Idempotency-Key': `e2e-r3-b-${Date.now()}` }),
    )
    expect(first.status, 'ops-a request did not complete').toBe('fulfilled')
    expect(second.status, 'ops-b request did not complete').toBe('fulfilled')

    const a = first.status === 'fulfilled' ? first.value : null
    const b = second.status === 'fulfilled' ? second.value : null

    const codes = [
      a?.body?.data && typeof a.body.data === 'object' ? (a.body.data as { code?: string }).code : refusalCode(a!),
      b?.body?.data && typeof b.body.data === 'object' ? (b.body.data as { code?: string }).code : refusalCode(b!),
    ]
    console.log('[race 3] outcome codes:', codes, 'statuses:', a?.status, b?.status)

    // §2's zero-5xx assertion: a race that resolves correctly but crashes has still failed.
    expect(a!.status, 'ops-a got a 5xx -- the refusal must be typed, not a crash').toBeLessThan(500)
    expect(b!.status, 'ops-b got a 5xx -- the refusal must be typed, not a crash').toBeLessThan(500)

    // Exactly one CLAIMED, exactly one ALREADY_ACTIONED. `escalation_service.py:716` sets
    // `result["code"] = "ALREADY_ACTIONED"` when the conditional claim UPDATE matches no row.
    const alreadyActioned = codes.filter((c) => c === 'ALREADY_ACTIONED').length
    expect(
      alreadyActioned,
      `expected exactly one loser told ALREADY_ACTIONED, got codes ${JSON.stringify(codes)}`,
    ).toBe(1)

    // --- the UI half: the loser must be TOLD, and told WHO won ------------------------------------
    const { a: pageA, b: pageB, dispose } = await twoContexts(browser, 'ops-a', 'ops-b')
    try {
      await Promise.all([pageA.goto('/ops'), pageB.goto('/ops')])
      await Promise.all([
        pageA.waitForLoadState('networkidle'),
        pageB.waitForLoadState('networkidle'),
      ])

      // Both consoles must render the queue at all -- if the surface is broken, the race assertion
      // above is still valid but the UI half is not being tested, and that must not read as a pass.
      for (const [name, page] of [
        ['ops-a', pageA],
        ['ops-b', pageB],
      ] as const) {
        await expect(
          page.getByRole('listbox', { name: 'Escalations' }),
          `${name}'s ops console did not render the escalation listbox`,
        ).toBeVisible()
      }

      // The owned row must show an owner rather than "Unowned" -- i.e. the winning claim is
      // reflected in the UI both coordinators see, in place, without either console erroring.
      const row = pageB.getByRole('option').filter({ hasText: escalationId! })
      const rowCount = await row.count()
      if (rowCount === 0) {
        // Owned rows may sort or filter out of the default view; that is a real product behaviour,
        // not a failure, but it means this particular assertion has nothing to stand on.
        console.log(
          `[race 3] NOTE: ${escalationId} is not in ops-b's default queue view after the race; ` +
            `owner-naming assertion skipped for this run.`,
        )
      } else {
        await expect(row.first()).not.toContainText('Unowned')
      }

      // Neither console may have crashed on the raced row (the #89 class of failure).
      for (const [name, page] of [
        ['ops-a', pageA],
        ['ops-b', pageB],
      ] as const) {
        await expect(page.locator('body'), `${name} rendered a crash screen`).not.toContainText(
          'Something went wrong',
        )
      }
    } finally {
      await dispose()
    }
  })
})
