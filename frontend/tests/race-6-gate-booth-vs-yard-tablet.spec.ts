import { test, expect } from 'playwright/test'

import { apiAs, simultaneously, twoContexts } from './support/race'

/**
 * ## Race 6 -- `04-gate-yard-kiosk` #5: gate booth and yard tablet act on the same truck
 *
 * `TESTING_STRATEGY.md` §4, row 6. The loser must see:
 *   `INVALID_TRANSITION` -> **re-fetch and re-render the now-correct one valid action** -- never a
 *   blind retry of the rejected one.
 *
 * ### Two contexts, one device account -- deliberately
 *
 * The two racers here are two *devices*, not two humans: `auth-and-scoping.md` makes the gate
 * session device-bound, and `gate.py`'s header comment spells out that the principal is a device
 * account while `officer_name` (U111, issue #68) is an unverified human label carried on the write.
 * So `gate-booth` and `gate-yard` intentionally resolve to the same `public.users` row -- and
 * `storage-state-isolation.spec.ts` level 3 asserts that sameness explicitly, so it cannot drift
 * into an accident. They still get **separately minted sessions in separate storageState files**,
 * so neither can invalidate the other mid-race.
 *
 * ### Why the mutating half is opt-in
 *
 * Gate transitions have **no inverse**. `gate_yard_service.py` implements a forward-only state
 * machine (`gate-in` -> `queue-state` -> `dock-in` -> `unload` -> `gate-out`); nothing un-gates a
 * truck. The only write-safe shipments are the reschedule sandbox's, whose yard state the
 * documented reschedule demo depends on (`supabase/demo/README.md`, runbook Phase H). Burning one
 * through the yard machine to observe a refusal would leave the sandbox in a state only a re-seed
 * restores -- a worse trade than an honest skip.
 *
 * So the real two-context write race is gated behind `E2E_ALLOW_GATE_WRITES=1` and skipped with
 * that reason by default. The **UI half runs unconditionally**, because it needs no write.
 */

test.describe('Race 6 — gate booth vs yard tablet', () => {
  test('both kiosk contexts start a shift independently and neither leaks the other', async ({
    browser,
  }) => {
    const { a: booth, b: yard, dispose } = await twoContexts(browser, 'gate-booth', 'gate-yard')
    try {
      await Promise.all([booth.goto('/gate'), yard.goto('/gate')])

      // The kiosk opens on the shift-start screen (`components/shift-start.tsx`), which is a real
      // gate on the surface: no search, and therefore no transition, until a shift is started.
      for (const [name, page] of [
        ['booth', booth],
        ['yard', yard],
      ] as const) {
        await expect(
          page.getByRole('heading', { name: 'Start shift' }),
          `${name} did not render the shift-start screen`,
        ).toBeVisible()
      }

      // Two devices, two different officers on shift at once -- U111's shared-shift model. Each
      // context must keep its own officer; if storageState or app state leaked between contexts,
      // one name would overwrite the other.
      await booth.getByLabel(/officer name/i).fill('E2E Booth Officer')
      await yard.getByLabel(/officer name/i).fill('E2E Yard Officer')
      await Promise.all([
        booth.getByRole('button', { name: 'Start shift' }).click(),
        yard.getByRole('button', { name: 'Start shift' }).click(),
      ])
      await Promise.all([
        booth.waitForLoadState('networkidle'),
        yard.waitForLoadState('networkidle'),
      ])

      const boothText = await booth.locator('body').innerText()
      const yardText = await yard.locator('body').innerText()
      expect(boothText, 'the booth context is showing the yard context\'s officer').not.toContain(
        'E2E Yard Officer',
      )
      expect(yardText, 'the yard context is showing the booth context\'s officer').not.toContain(
        'E2E Booth Officer',
      )
      for (const [name, text] of [
        ['booth', boothText],
        ['yard', yardText],
      ] as const) {
        expect(text, `${name} rendered a crash screen`).not.toContain('Something went wrong')
      }
    } finally {
      await dispose()
    }
  })

  test('the INVALID_TRANSITION treatment renders with no retry affordance', async ({ browser }) => {
    // The loser's UI contract, asserted against the REAL components rather than a write: the gate
    // states gallery (`/gate/_states`) renders artboard 22a --
    // "INVALID_TRANSITION — no button; the screen resolves on its own" -- from
    // `components/outcome-screen.tsx` with the real `RESULT_INVALID_TRANSITION` result shape.
    // `outcome-screen.tsx:39` states the rule this asserts: the outcome is `null`-buttoned for
    // INVALID_TRANSITION precisely so nobody can blind-retry the rejected action.
    const ctx = await twoContexts(browser, 'gate-booth', 'gate-yard')
    try {
      await ctx.a.goto('/gate/_states')
      await ctx.a.waitForLoadState('networkidle')
      const body = await ctx.a.locator('body').innerText()
      expect(
        body,
        'the gate states gallery does not render the INVALID_TRANSITION artboard, so the loser ' +
          'treatment this race depends on is not present in the built surface',
      ).toContain('INVALID_TRANSITION')
      expect(body).not.toContain('Something went wrong')
    } finally {
      await ctx.dispose()
    }
  })

  test('two devices act on one truck: exactly one transition applies', async () => {
    test.skip(
      process.env.E2E_ALLOW_GATE_WRITES !== '1',
      'SKIPPED (named reason): gate transitions have NO inverse — gate_yard_service.py implements ' +
        'a forward-only state machine (gate-in → queue-state → dock-in → unload → gate-out) and ' +
        'nothing un-gates a truck. The only write-safe shipments are the reschedule sandbox\'s, ' +
        'whose yard state the documented reschedule demo (supabase/demo/README.md, runbook Phase ' +
        'H) depends on, so burning one to observe a refusal would need a re-seed to undo. Set ' +
        'E2E_ALLOW_GATE_WRITES=1 to run the real two-device write race.',
    )

    // GATE_KIOSK_ROLES = (GATE_OFFICER, WAREHOUSE_PLANNER, FACILITY_MANAGER, ADMIN)
    // -- backend/app/core/deps.py:99-104. The roster has no GATE_OFFICER credential (issue #79
    // added the enum member and the role gate, but no kiosk account was provisioned), so the
    // planner account stands in.
    const facility = 'FAC-JAI-01'
    const trucks = await apiAs<{ trucks?: Array<{ shipment_id?: string }> }>(
      'gate-booth',
      'GET',
      `/api/v1/gate/trucks?facility_id=${facility}&query=SHP`,
    )
    test.skip(
      trucks.status !== 200,
      `SKIPPED: GET /api/v1/gate/trucks returned ${trucks.status} for the kiosk role.`,
    )
    const target = (trucks.body?.data?.trucks ?? []).find(
      (t) => t.shipment_id && !t.shipment_id.startsWith('SHP-D16-'),
    )?.shipment_id
    test.skip(!target, 'SKIPPED: no non-demo-cast truck available at the gate.')

    const gateIn = (role: 'gate-booth' | 'gate-yard') =>
      apiAs<{ code?: string }>(
        role,
        'POST',
        `/api/v1/gate/shipments/${target}/gate-in`,
        { officer_name: role === 'gate-booth' ? 'E2E Booth' : 'E2E Yard' },
        { 'Idempotency-Key': `e2e-r6-${role}-${Date.now()}` },
      )

    const [first, second] = await simultaneously(() => gateIn('gate-booth'), () => gateIn('gate-yard'))
    const a = first.status === 'fulfilled' ? first.value : null
    const b = second.status === 'fulfilled' ? second.value : null
    const code = (r: typeof a) => r?.body?.data?.code ?? r?.body?.errors?.[0]?.code ?? ''
    const codes = [code(a), code(b)]
    console.log('[race 6] codes:', codes, 'statuses:', a?.status, b?.status)

    expect(a!.status, 'booth got a 5xx').toBeLessThan(500)
    expect(b!.status, 'yard got a 5xx').toBeLessThan(500)
    expect(
      codes.filter((c) => /INVALID_TRANSITION/.test(c)).length,
      `one device must be refused INVALID_TRANSITION; got ${JSON.stringify(codes)}`,
    ).toBe(1)
  })
})
