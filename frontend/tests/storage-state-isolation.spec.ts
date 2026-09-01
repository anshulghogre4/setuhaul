import { test, expect } from 'playwright/test'

import { ACCOUNTS, DISTINCT_IDENTITY_KEYS, ROLE_KEYS } from './support/accounts'
import { SUPABASE_STORAGE_KEY } from './support/env'
import { storageStatePath } from './support/paths'
import { authMe, jwtClaims } from './support/session'
import { accessTokenFor, contextForRole, readStorageState } from './support/race'

/**
 * Issue #43, sub-issue 2 -- **verify storageState isolation before trusting any result**.
 *
 * `TESTING_STRATEGY.md` §4 documents the pitfall this guards:
 *
 *   > sharing `storageState` across roles causes the files to overwrite each other, creating a
 *   > race **inside the test suite itself**. Use distinct storage paths per role. A concurrency
 *   > suite with its own race condition proves nothing.
 *
 * The failure it describes is SILENT: if two role contexts end up carrying the same identity, a
 * "two coordinators race" becomes one coordinator racing themselves, both actions succeed, and the
 * suite goes green having tested nothing. So this file asserts isolation at four increasing levels
 * of strength, because the cheap checks cannot catch the expensive failure:
 *
 *   1. **Distinct paths** -- no two roles write the same file.
 *   2. **Distinct tokens** -- the files do not contain the same access token.
 *   3. **Distinct subjects** -- the JWTs name different `sub` claims (different auth users).
 *   4. **The SERVER agrees** -- `GET /api/v1/auth/me` returns a different `user_id` per token.
 *
 * Level 4 is the one that actually matters. Levels 1-3 are all statements about files this suite
 * wrote itself; only level 4 asks the system under test who it thinks is calling. A suite that
 * checked only level 1 would still pass if every file held the same session.
 *
 * Level 5 (the last test) closes the loop in the browser: two live contexts, and the app's own
 * HTTP layer sends two different bearer tokens.
 */

test.describe('storageState isolation (issue #43 sub-issue 2)', () => {
  test('level 1: every role writes a distinct storageState path', async () => {
    const paths = ROLE_KEYS.map((r) => storageStatePath(r))
    expect(new Set(paths).size).toBe(ROLE_KEYS.length)
  })

  test('level 1b: each file holds the session under the key the APP actually reads', async () => {
    // If this key were wrong the injection would be inert: getSession() would return null and every
    // surface would 401 -- which looks like "the backend is down", not "the fixture is wrong".
    for (const role of ROLE_KEYS) {
      const state = readStorageState(role)
      const origin = state.origins[0]
      expect(origin, `no origin entry for ${role}`).toBeTruthy()
      const names = origin.localStorage.map((e) => e.name)
      expect(names, `${role} is missing ${SUPABASE_STORAGE_KEY}`).toContain(SUPABASE_STORAGE_KEY)
    }
  })

  test('level 2: no two roles share an access token', async () => {
    const tokens = ROLE_KEYS.map((r) => accessTokenFor(r))
    // Includes gate-booth/gate-yard, which are the SAME human but separately-minted sessions --
    // so even the deliberate account reuse must not produce a shared token.
    expect(new Set(tokens).size).toBe(ROLE_KEYS.length)
  })

  test('level 3: distinct-identity roles carry distinct JWT subjects', async () => {
    const subs = DISTINCT_IDENTITY_KEYS.map((r) => jwtClaims(accessTokenFor(r)).sub as string)
    for (const [i, sub] of subs.entries()) {
      expect(sub, `${DISTINCT_IDENTITY_KEYS[i]} has no sub claim`).toBeTruthy()
    }
    expect(new Set(subs).size, `expected ${DISTINCT_IDENTITY_KEYS.length} distinct auth subjects`).toBe(
      DISTINCT_IDENTITY_KEYS.length,
    )

    // ...and the two gate contexts must be the SAME subject, since they are one device account.
    // Asserted explicitly so that a future change making them different accounts is a visible
    // failure rather than a silent semantic drift.
    expect(jwtClaims(accessTokenFor('gate-booth')).sub).toBe(
      jwtClaims(accessTokenFor('gate-yard')).sub,
    )
  })

  test('level 4: the SERVER resolves each token to the expected distinct user', async () => {
    const seen: string[] = []
    for (const role of DISTINCT_IDENTITY_KEYS) {
      const me = await authMe(accessTokenFor(role))
      expect(me.status, `auth/me failed for ${role}`).toBe(200)
      expect(me.userId, `${role} resolved to the wrong user`).toBe(ACCOUNTS[role].userId)
      expect(me.roleName, `${role} resolved to the wrong role`).toBe(ACCOUNTS[role].roleName)
      expect(me.facilityId, `${role} resolved to the wrong facility`).toBe(ACCOUNTS[role].facilityId)
      seen.push(me.userId!)
    }
    expect(new Set(seen).size, 'the server must see these as different people').toBe(
      DISTINCT_IDENTITY_KEYS.length,
    )
  })

  test('level 5: two live browser contexts send two different bearer tokens', async ({ browser }) => {
    // The end-to-end version of the claim: not "the files differ" but "the app, running in two
    // contexts, authenticates as two different people". Asserted on the real Authorization header
    // the app's own fetch layer builds (core/http/api.ts:46-50).
    const ctxA = await contextForRole(browser, 'ops-a')
    const ctxB = await contextForRole(browser, 'ops-b')
    try {
      const pageA = await ctxA.newPage()
      const pageB = await ctxB.newPage()

      const seenA: string[] = []
      const seenB: string[] = []
      const capture = (sink: string[]) => (request: { headers: () => Record<string, string>; url: () => string }) => {
        const auth = request.headers()['authorization']
        if (auth?.startsWith('Bearer ')) sink.push(auth.slice(7))
      }
      pageA.on('request', capture(seenA))
      pageB.on('request', capture(seenB))

      await Promise.all([pageA.goto('/ops'), pageB.goto('/ops')])
      // The ops console fetches its queue on mount; wait for the network to settle rather than for
      // a specific selector, so this check does not depend on that surface's markup.
      await Promise.all([
        pageA.waitForLoadState('networkidle'),
        pageB.waitForLoadState('networkidle'),
      ])

      expect(seenA.length, 'context A never sent an authenticated request').toBeGreaterThan(0)
      expect(seenB.length, 'context B never sent an authenticated request').toBeGreaterThan(0)

      const subA = jwtClaims(seenA[0]).sub
      const subB = jwtClaims(seenB[0]).sub
      expect(subA).toBeTruthy()
      expect(subA, 'the two contexts authenticated as the SAME user -- isolation is broken').not.toBe(
        subB,
      )
    } finally {
      await ctxA.close()
      await ctxB.close()
    }
  })

  test('negative control: a context with NO storageState is anonymous, not a leaked role', async ({
    browser,
  }) => {
    // Proves the absence of a config-level default `storageState`. If one existed, this context
    // would silently inherit it and every "two role" test would risk being one role twice.
    const ctx = await browser.newContext()
    try {
      const page = await ctx.newPage()
      await page.goto('/ops')
      const token = await page.evaluate(
        (key) => window.localStorage.getItem(key),
        SUPABASE_STORAGE_KEY,
      )
      expect(token, 'a fresh context must carry no session').toBeNull()
    } finally {
      await ctx.close()
    }
  })
})
