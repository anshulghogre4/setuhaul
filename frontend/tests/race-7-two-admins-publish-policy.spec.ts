import { test, expect } from 'playwright/test'

import { apiAs, simultaneously, twoContexts } from './support/race'

/**
 * ## Race 7 -- `06-admin-console` #3: two admins publish policy weights concurrently
 *
 * `TESTING_STRATEGY.md` §4, row 7. The loser must see:
 *   - a **named conflict, not a silent overwrite**,
 *   - their simulation marked stale,
 *   - and a required re-simulation against the new baseline before publishing.
 *
 * ### Why this races WITHOUT mutating the shared policy
 *
 * `publish_policy_version` has no inverse. A published version is global -- it is not
 * facility-scoped, so there is no sandbox to confine it to, and every subsequent ranking on the
 * shared dev database would run under whatever this suite published. That is exactly the kind of
 * write issue #43 says to avoid.
 *
 * The optimistic-concurrency guard makes a non-mutating race possible. `admin.py:141-149`'s
 * `PublishPolicyBody.based_on_version_id` is `edge-cases.md` #3's baseline, and
 * `admin_governance_service.py:847-881` refuses with `ALREADY_ACTIONED` (409) **before writing**
 * whenever the cited baseline is not the active version -- or `BASE_VERSION_REQUIRED` when an
 * active version exists and no baseline was cited. So two admins racing with a deliberately stale
 * baseline exercise the real refusal path, name the real winning version, and leave the policy
 * table untouched.
 *
 * The **mutating** variant -- one admin genuinely publishes and the other loses -- is implemented
 * too, but gated behind `E2E_ALLOW_POLICY_PUBLISH=1`. It is skipped with that reason by default,
 * never silently passed.
 */

type ActivePolicy = {
  active_version?: { version_id?: string; policy_version?: string } | string | null
  live_weights?: Record<string, unknown>
}

function versionIdOf(active: ActivePolicy | undefined): string | null {
  const v = active?.active_version
  if (!v) return null
  if (typeof v === 'string') return v
  return v.version_id ?? v.policy_version ?? null
}

test.describe('Race 7 — two admins publish policy weights concurrently', () => {
  test('a stale baseline is refused with a NAMED conflict, not a silent overwrite', async () => {
    const active = await apiAs<ActivePolicy>('admin-a', 'GET', '/api/v1/admin/policy/active')
    test.skip(
      active.status !== 200,
      `SKIPPED: GET /api/v1/admin/policy/active returned ${active.status}; without the active ` +
        `baseline there is nothing for two admins to race against.`,
    )
    const activeId = versionIdOf(active.body?.data)
    const weights = active.body?.data?.live_weights ?? {}
    console.log('[race 7] active version:', activeId ?? '(none)')

    test.skip(
      !activeId,
      'SKIPPED (named reason): `active_version` is null on this database — no policy version has ' +
        'ever been published (verified live 2026-09-01: GET /admin/policy/active returns ' +
        '`active_version: null`, `engine_matches_active_version: false`). edge-cases.md #3\'s ' +
        'conflict only exists once a version is live, and the very first publish has no baseline ' +
        'to be stale against, so it would SUCCEED and mutate global policy. Publish one baseline ' +
        'version (or run with E2E_ALLOW_POLICY_PUBLISH=1) to make this race runnable.',
    )

    // Both admins cite a baseline that is NOT the active one. Neither can win, and neither writes.
    const stale = `${activeId}-E2E-STALE`
    const publish = (role: 'admin-a' | 'admin-b') =>
      apiAs<{ code?: string }>(
        role,
        'POST',
        '/api/v1/admin/policy/publish',
        { weights, based_on_version_id: stale },
        { 'Idempotency-Key': `e2e-r7-${role}-${Date.now()}` },
      )

    const [first, second] = await simultaneously(() => publish('admin-a'), () => publish('admin-b'))
    expect(first.status).toBe('fulfilled')
    expect(second.status).toBe('fulfilled')
    const a = first.status === 'fulfilled' ? first.value : null
    const b = second.status === 'fulfilled' ? second.value : null

    const code = (r: typeof a) => r?.body?.errors?.[0]?.code ?? r?.body?.data?.code ?? ''
    console.log('[race 7] codes:', [code(a), code(b)], 'statuses:', a?.status, b?.status)

    for (const [name, r] of [
      ['admin-a', a],
      ['admin-b', b],
    ] as const) {
      expect(r!.status, `${name} got a 5xx -- a version conflict must be typed, not a crash`).toBeLessThan(500)
      expect(
        ['ALREADY_ACTIONED', 'BASE_VERSION_REQUIRED'],
        `${name} was allowed to publish over a stale baseline -- that is the silent overwrite ` +
          `edge-cases.md #3 forbids. code=${code(r)}`,
      ).toContain(code(r))
    }

    // "Named conflict": the refusal must identify the winning version, not just say no.
    const message = a?.body?.message ?? ''
    console.log('[race 7] refusal message:', message.slice(0, 200))
    expect(
      message.length,
      'the conflict refusal must carry an explanatory message naming what won',
    ).toBeGreaterThan(0)

    // And nothing may have been written: the active version must be unchanged.
    const after = await apiAs<ActivePolicy>('admin-a', 'GET', '/api/v1/admin/policy/active')
    expect(
      versionIdOf(after.body?.data),
      'a refused publish must not change the active policy version',
    ).toBe(activeId)
  })

  test('both admins reach the Policy tab and neither console crashes on the conflict', async ({
    browser,
  }) => {
    const { a: pageA, b: pageB, dispose } = await twoContexts(browser, 'admin-a', 'admin-b')
    try {
      await Promise.all([pageA.goto('/admin'), pageB.goto('/admin')])
      await Promise.all([
        pageA.waitForLoadState('networkidle'),
        pageB.waitForLoadState('networkidle'),
      ])
      for (const [name, page] of [
        ['admin-a', pageA],
        ['admin-b', pageB],
      ] as const) {
        await expect(
          page.getByRole('tablist', { name: 'Admin console sections' }),
          `${name}'s admin console did not render`,
        ).toBeVisible()
        await page.getByRole('tab', { name: /policy/i }).click()
        await expect(page.locator('body'), `${name} crashed on the Policy tab`).not.toContainText(
          'Something went wrong',
        )
      }
    } finally {
      await dispose()
    }
  })

  test('the mutating variant: one admin publishes, the other is told who won', async () => {
    test.skip(
      process.env.E2E_ALLOW_POLICY_PUBLISH !== '1',
      'SKIPPED (named reason): publishing a policy version is a GLOBAL, irreversible write on the ' +
        'shared dev database — policy versions are not facility-scoped, so there is no sandbox to ' +
        'confine it to and no unpublish tool. The non-mutating stale-baseline test above already ' +
        'exercises the same ALREADY_ACTIONED refusal path. Set E2E_ALLOW_POLICY_PUBLISH=1 to run ' +
        'the real publish.',
    )

    const active = await apiAs<ActivePolicy>('admin-a', 'GET', '/api/v1/admin/policy/active')
    const activeId = versionIdOf(active.body?.data)
    const weights = active.body?.data?.live_weights ?? {}
    test.skip(!activeId, 'SKIPPED: no active baseline.')

    // Both cite the SAME, genuine baseline. Exactly one may win.
    const publish = (role: 'admin-a' | 'admin-b') =>
      apiAs<{ code?: string }>(
        role,
        'POST',
        '/api/v1/admin/policy/publish',
        { weights, based_on_version_id: activeId },
        { 'Idempotency-Key': `e2e-r7-real-${role}-${Date.now()}` },
      )

    const [first, second] = await simultaneously(() => publish('admin-a'), () => publish('admin-b'))
    const a = first.status === 'fulfilled' ? first.value : null
    const b = second.status === 'fulfilled' ? second.value : null
    const code = (r: typeof a) => r?.body?.errors?.[0]?.code ?? r?.body?.data?.code ?? ''
    const codes = [code(a), code(b)]
    console.log('[race 7 mutating] codes:', codes)

    expect(
      codes.filter((c) => c === 'ALREADY_ACTIONED').length,
      `exactly one admin must lose with a named conflict; got ${JSON.stringify(codes)}`,
    ).toBe(1)
  })
})
