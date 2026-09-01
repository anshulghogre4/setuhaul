import { expect, test } from 'playwright/test'

import { ACCOUNTS } from './support/accounts'
import { passwordFor } from './support/credentials'
import { assertLocalTarget, SUPABASE_STORAGE_KEY } from './support/env'
import { contextForRole } from './support/race'

/**
 * Route guards + real sign-in (2026-09-01).
 *
 * ## What was broken, and why this file exists
 *
 * `App.tsx` used to render `<SignIn onSubmit={() => navigate('/planner')} />`: **any** string in
 * either box "logged you in", every surface route was reachable with no session at all, and the
 * shell rendered a fixture identity (`PLANNER_MULTI_ROLE`) for whoever showed up.
 * `tests/support/session.ts` records that defect in its own docstring as the reason those suites
 * inject sessions rather than driving the form. This file is the regression suite for the fix, and
 * case (c) is the one that could not have been written before it.
 *
 * ## Why the guards do not break session injection
 *
 * They read the session through supabase-js (`getSession()` inside `core/auth/auth-provider.tsx`),
 * which is a plain localStorage read of `SUPABASE_STORAGE_KEY` -- the exact seam `auth.setup.ts`
 * writes. A guard that had instead kept its own token copy, or trusted a React-only login flag,
 * would have made every injected context anonymous. Case (b) is what proves that end to end.
 *
 * ## Secrets
 *
 * Case (c) resolves the sandbox driver's password through `support/credentials.ts` (environment
 * first, gitignored roster second). Nothing here logs, writes or asserts on a password value; the
 * only credential string that appears is the committed, non-secret email from the cast.
 */

const SANDBOX_DRIVER = ACCOUNTS['driver-sandbox']

test.describe('auth guards (unauthenticated)', () => {
  test('a: /planner and /driver both redirect an anonymous visitor to /signin', async ({
    browser,
  }) => {
    // A fresh context, deliberately with NO storageState -- the same negative-control shape
    // `storage-state-isolation.spec.ts` uses, so a config-level default could not mask the result.
    const ctx = await browser.newContext()
    try {
      const page = await ctx.newPage()

      for (const attempted of ['/planner', '/driver']) {
        await page.goto(attempted)
        await expect(page).toHaveURL(/\/signin$/)
        // The sign-in form is genuinely rendered, not just the URL rewritten.
        await expect(page.locator('input[name="identifier"]')).toBeVisible()
        // ...and nothing wrote a session on the way.
        const token = await page.evaluate(
          (key) => window.localStorage.getItem(key),
          SUPABASE_STORAGE_KEY,
        )
        expect(token, `visiting ${attempted} must not create a session`).toBeNull()
      }
    } finally {
      await ctx.close()
    }
  })

  test('a2: /admin redirects too -- the manual-sanity case, asserted', async ({ browser }) => {
    const ctx = await browser.newContext()
    try {
      const page = await ctx.newPage()
      await page.goto('/admin')
      await expect(page).toHaveURL(/\/signin$/)
    } finally {
      await ctx.close()
    }
  })

  test('a3: the _states galleries stay reachable without a session, by design', async ({
    browser,
  }) => {
    // Asserted rather than assumed: these render fixture artboards, make no authenticated call,
    // and are the only way to inspect a surface's states without holding that surface's role.
    // If someone later guards them, this fails loudly instead of the galleries quietly 404ing for
    // reviewers. Race suite 6 already depends on `/gate/_states` being open.
    const ctx = await browser.newContext()
    try {
      const page = await ctx.newPage()
      await page.goto('/gate/_states')
      await expect(page).toHaveURL(/\/gate\/_states$/)
    } finally {
      await ctx.close()
    }
  })
})

test.describe('auth guards (authenticated, wrong surface)', () => {
  test('b: a DRIVER session hitting /planner is redirected to /driver, not shown the console', async ({
    browser,
  }) => {
    // Uses the injected storageState the whole E6.2 suite runs on. If the guards had stopped
    // reading the session through supabase-js, this context would be anonymous and the assertion
    // would land on /signin instead -- which is exactly the failure mode worth catching.
    const ctx = await contextForRole(browser, 'driver-sandbox')
    try {
      const page = await ctx.newPage()
      await page.goto('/planner')
      await expect(page).toHaveURL(/\/driver$/)
      // Their own surface really rendered; they were not bounced to sign-in.
      await expect(page.getByRole('heading', { level: 1, name: 'SetuHaul' })).toBeVisible()
    } finally {
      await ctx.close()
    }
  })
})

test.describe('real sign-in against the local stack', () => {
  test('c: the sandbox driver signs in for real and lands on /driver', async ({ browser }) => {
    assertLocalTarget()

    // No storageState: this test must establish its own session through the form, which is the
    // whole point. It is also why it cannot reuse `contextForRole`.
    const ctx = await browser.newContext()
    try {
      const page = await ctx.newPage()
      await page.goto('/signin')

      await page.locator('input[name="identifier"]').fill(SANDBOX_DRIVER.email)
      // Never logged, never asserted on -- resolved from env or the gitignored roster.
      await page.locator('input[name="password"]').fill(passwordFor(SANDBOX_DRIVER.bucket))
      await page.getByRole('button', { name: 'Sign in' }).click()

      // The landing surface comes from the SERVER's role, not from the form: `/auth/me` says
      // DRIVER, `landingPathFor('DRIVER')` says `/driver`.
      await expect(page).toHaveURL(/\/driver$/, { timeout: 20_000 })
      await expect(page.getByRole('heading', { level: 1, name: 'SetuHaul' })).toBeVisible()
      // Scoped to the thread-list header: `DriverShell`'s bottom nav carries a second link to the
      // same href, so an unscoped by-role lookup is a strict-mode violation rather than a signal.
      await expect(page.locator('header a[href="/driver/profile"]')).toBeVisible()

      // The thread-list region resolved to a real state -- a list of threads, or one of the two
      // honest empty states, or the load-failure state. Any of the three means the surface
      // rendered with a real session; a skeleton that never resolves would mean it did not.
      await expect(
        page
          .locator('main')
          .getByRole('list')
          .or(page.getByText(/No active loads|No loads assigned yet|Couldn’t load/)),
      ).toBeVisible({ timeout: 20_000 })

      // And the session is genuinely persisted where the app reads it from.
      const token = await page.evaluate(
        (key) => window.localStorage.getItem(key),
        SUPABASE_STORAGE_KEY,
      )
      expect(token, 'a successful sign-in must persist a Supabase session').not.toBeNull()
    } finally {
      await ctx.close()
    }
  })

  test('d: a wrong password shows the error state and does NOT navigate', async ({ browser }) => {
    assertLocalTarget()

    const ctx = await browser.newContext()
    try {
      const page = await ctx.newPage()
      await page.goto('/signin')

      await page.locator('input[name="identifier"]').fill(SANDBOX_DRIVER.email)
      // A deliberately wrong value. Not a real password, so nothing secret is written here.
      await page.locator('input[name="password"]').fill('definitely-not-the-password')
      await page.getByRole('button', { name: 'Sign in' }).click()

      // The screen's own anti-enumeration copy: identical whichever half was wrong, neither field
      // marked (`auth-and-scoping.md`, "Errors never disclose whether an account exists").
      const error = page.getByTestId('signin-error')
      await expect(error).toBeVisible({ timeout: 20_000 })
      await expect(error).toContainText('Those details don’t match.')

      // Still on /signin, and -- the part that actually matters -- still no session.
      await expect(page).toHaveURL(/\/signin$/)
      const token = await page.evaluate(
        (key) => window.localStorage.getItem(key),
        SUPABASE_STORAGE_KEY,
      )
      expect(token, 'a failed sign-in must not create a session').toBeNull()
    } finally {
      await ctx.close()
    }
  })
})
