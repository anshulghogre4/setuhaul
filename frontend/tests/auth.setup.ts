import { mkdirSync, writeFileSync } from 'node:fs'
import { test as setup, expect } from 'playwright/test'

import { ACCOUNTS, ROLE_KEYS } from './support/accounts'
import { API_BASE_URL, assertLocalTarget } from './support/env'
import { mintSession, toStorageState } from './support/session'
import { AUTH_DIR, storageStatePath } from './support/paths'

/**
 * The `setup` project. Produces one storageState file per role BEFORE any race runs.
 *
 * **The pitfall this file exists to avoid** (`TESTING_STRATEGY.md` §4):
 *
 *   > sharing `storageState` across roles causes the files to overwrite each other, creating a
 *   > race **inside the test suite itself**. Use distinct storage paths per role. A concurrency
 *   > suite with its own race condition proves nothing.
 *
 * Every path here comes from `storageStatePath(role)`, which is `tests/.auth/<role>.json` -- one
 * file per role key, never a shared default. `playwright.config.ts` sets no `use.storageState` at
 * all, so a spec that forgets to pass one gets an ANONYMOUS context whose API calls 401 loudly,
 * rather than silently inheriting whichever role wrote last. That is the important property: the
 * failure mode of forgetting is a visible 401, not a false negative.
 *
 * `storage-state-isolation.spec.ts` then proves the files really do carry different identities,
 * because "I wrote different paths" is not the same claim as "two contexts are two people".
 */

setup('mint one storageState per role', async () => {
  assertLocalTarget()

  // A missing backend must fail here with a sentence, not 60s into a race suite as a timeout.
  const health = await fetch(`${API_BASE_URL}/health/live`).catch(() => null)
  expect(
    health?.ok,
    `Local backend is not answering at ${API_BASE_URL}. Start it first:\n` +
      `  cd backend && uv run uvicorn app.main:app --port 8000\n` +
      `(E6.2 targets the LOCAL stack; issue #43 forbids driving production with race writes.)`,
  ).toBe(true)

  /**
   * Best-effort M8 sweep before minting anything.
   *
   * A previous run's *winning* D2 hold keeps occupying its dock interval past the 90-second TTL,
   * because a lapsed hold is only released when the M8 expiry sweeper collects it -- and that
   * sweeper is a scheduled job, not something a plain local `uvicorn` runs. Observed directly:
   * races 1, 2, 4 and 5 all go inconclusive on back-to-back runs, every candidate slot answering
   * `SLOT_CONFLICT_REFRESH_REQUIRED`. Running one sweep cycle here makes the suite self-healing.
   *
   * Deliberately best-effort and never fatal: the endpoint is `JOB_AUTH_TOKEN`-gated
   * (`internal.py:56`, header `X-SetuHaul-Job-Token`) and answers 503 when unconfigured, which is
   * a perfectly normal local setup. The races each carry their own honest skip message for the
   * case where capacity is still blocked.
   */
  const jobToken = process.env.JOB_AUTH_TOKEN ?? process.env.SETUHAUL_JOB_AUTH_TOKEN
  if (jobToken) {
    // Mounted at the ROOT, not under /api/v1 -- `main.py:97` includes `internal.router` with no
    // extra prefix, and the router's own prefix is `/internal` (`internal.py:54`). Confirmed
    // against the live OpenAPI document, which lists exactly `/internal/jobs/expiry-sweep`.
    const sweep = await fetch(`${API_BASE_URL}/internal/jobs/expiry-sweep`, {
      method: 'POST',
      headers: { 'X-SetuHaul-Job-Token': jobToken },
    }).catch(() => null)
    console.log(`[setup] expiry sweep -> HTTP ${sweep?.status ?? 'unreachable'}`)
  } else {
    console.log(
      '[setup] expiry sweep skipped: no JOB_AUTH_TOKEN in the environment. Lapsed D2 holds may ' +
        'still occupy slots, which can make the driver-side races report INCONCLUSIVE.',
    )
  }

  mkdirSync(AUTH_DIR, { recursive: true })

  const appOrigin = process.env.E2E_BASE_URL ?? 'http://localhost:5173'
  const seenPaths = new Set<string>()

  for (const key of ROLE_KEYS) {
    const account = ACCOUNTS[key]
    // Each role gets its OWN minted session, including gate-booth/gate-yard which share an
    // account -- Supabase issues independent sessions per grant, so the two kiosk contexts do not
    // share a refresh token and cannot invalidate each other mid-race.
    const session = await mintSession(account)
    const path = storageStatePath(key)

    expect(seenPaths.has(path), `storageState path collision for role "${key}": ${path}`).toBe(false)
    seenPaths.add(path)

    writeFileSync(path, JSON.stringify(toStorageState(session, appOrigin), null, 2), 'utf8')
  }

  expect(seenPaths.size, 'every role must have written its own distinct storageState file').toBe(
    ROLE_KEYS.length,
  )
})
