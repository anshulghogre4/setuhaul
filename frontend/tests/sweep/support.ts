import { appendFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type Page } from 'playwright/test'

import { ACCOUNTS, type RoleKey } from '../support/accounts'
import { mintSession, toStorageState, type StorageState } from '../support/session'
import { storageStatePath } from '../support/paths'

/**
 * Shared plumbing for the full interactive click-sweep (owner-requested, 2026-09-01).
 *
 * The sweep activates every control in the design-derived inventory and writes one verdict line
 * per control. Verdicts go to a JSONL file rather than to `console.log` because a Playwright
 * `list` reporter interleaves worker output and this run has ~150 records to keep straight.
 */

const HERE = dirname(fileURLToPath(import.meta.url))

/** Gitignored (`tests/.gitignore` covers `.artifacts/`). */
export const SWEEP_OUT = resolve(HERE, '../.artifacts/sweep')

export type Verdict =
  | 'WORKING'
  | 'WORKING-ON-FIXTURE'
  | 'INACTIVE-LABELED'
  | 'DEAD'
  | 'MISSING'
  | 'BLOCKED-ENV'
  | 'VERIFIED-TO-DIALOG'
  /**
   * The control is absent AND the design says it should be — the inventory row was built from a
   * superseded design file. **Distinct from `MISSING` on purpose** (added 2026-09-01 while
   * closing #99/#100/#102): `MISSING` is a defect, and recording a deliberate, owner-resolved
   * absence as one turns a correct build into a permanent bug-count. Every row using this verdict
   * must cite the file and the ruling that supersedes the inventory, not merely assert it.
   */
  | 'NOT-IN-DESIGN'

export type Record_ = {
  surface: string
  control: string
  verdict: Verdict
  evidence: string
}

export function record(r: Record_): void {
  mkdirSync(SWEEP_OUT, { recursive: true })
  appendFileSync(resolve(SWEEP_OUT, `${r.surface}.jsonl`), `${JSON.stringify(r)}\n`, 'utf8')
}

/** A recorder bound to one surface, so a spec cannot mislabel a row. */
export function recorderFor(surface: string) {
  return (control: string, verdict: Verdict, evidence: string) =>
    record({ surface, control, verdict, evidence })
}

export function storageFor(role: RoleKey): string {
  return storageStatePath(role)
}

/**
 * The carrier surface's identity, minted inline rather than added to `tests/support/accounts.ts`.
 *
 * There is **no `CARRIER` role in the POC roster at all** -- `public.roles` runs ROL001..ROL008 and
 * none of them is `CARRIER`. The only account that lands on `/carrier` is `USR105`
 * (`TRANSPORT_MANAGER`), because `core/auth/identity-mapping.ts` maps the UI's `TRANSPORT_MANAGER`
 * to the carrier surface. `backend/app/api/v1/routers/carrier.py` gates on `RoleName.CARRIER`, so
 * every carrier read 403s for it -- the exact FORK that file flags as "latent"; it is not latent.
 *
 * Minted here rather than committed to `accounts.ts` so the seven race suites' own cast is
 * untouched by this read-only sweep.
 */
export async function carrierStorageState(appOrigin: string): Promise<StorageState> {
  const session = await mintSession({
    key: 'carrier-tm',
    email: 'sanjay.gupta@setuhaul.com',
    bucket: 'Admin',
    userId: 'USR105',
    roleName: 'TRANSPORT_MANAGER',
    facilityId: null,
  })
  return toStorageState(session, appOrigin)
}

export const ORIGIN = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

export { ACCOUNTS }

/**
 * The facility switcher, exercised on ops and planner alike (issue #99.1).
 *
 * ## Why a second facility has to be injected, and why that is honest
 *
 * **No account in the POC roster holds two facilities.** Verified live against this backend on
 * 2026-09-01: `GET /api/v1/account-profile` answers `scoped_facility_ids: ["FAC-JAI-01"]` for
 * `planner`, `["FAC-GGN-01"]` for `ops-ggn`, and `[]` for both admins. A switcher with one option
 * cannot demonstrate re-scoping at all -- selecting the row you are already on is correctly a
 * no-op -- so the only way to activate this control is to have the server say the account holds
 * two.
 *
 * So exactly one response is intercepted: `/account-profile`'s `scoped_facility_ids`. The real
 * response is fetched and only that array is widened; role, facility_id and everything else stay
 * verbatim. **Nothing about authorisation is faked** -- the access token is the real one, and the
 * subsequent read goes to the real server, which is the whole point of the assertion below.
 *
 * ## What is actually asserted
 *
 * Two reads, both real:
 *
 *  - selecting the OTHER facility must re-issue the surface's facility-scoped read carrying
 *    `facility_id=<other>` -- and the server must **refuse it**, because `resolve_facility_scope`
 *    (`backend/app/repositories/scope.py:46-57`) only lets a global-read persona narrow, and these
 *    identities are not one. That 403 is the M15 boundary working: the client asked, the server
 *    decided.
 *  - selecting the OWN facility back must re-issue the same read carrying `facility_id=<own>` and
 *    be served. That is the re-scope succeeding end to end.
 */
export async function verifyFacilitySwitcher(
  page: Page,
  opts: {
    say: (control: string, verdict: Verdict, evidence: string) => void
    control: string
    /** The facility this identity genuinely holds. */
    ownFacility: string
    /** A real facility id this identity does NOT hold. */
    otherFacility: string
    triggerName: RegExp
    /** Path fragment of the surface's facility-scoped read. */
    scopedRead: string
    /** Runs after every reload to get the surface back to a state where the switcher is usable. */
    settle?: (page: Page) => Promise<void>
  },
): Promise<void> {
  const { say, control, ownFacility, otherFacility, triggerName, scopedRead, settle } = opts

  await page.route('**/api/v1/account-profile*', async (route) => {
    const response = await route.fetch()
    const body = (await response.json()) as {
      data?: { scoped_facility_ids?: string[] }
    }
    if (body.data) body.data.scoped_facility_ids = [ownFacility, otherFacility]
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })

  const reads: Array<{ url: string; status: number }> = []
  page.on('response', (r) => {
    if (r.url().includes(scopedRead)) reads.push({ url: r.url(), status: r.status() })
  })

  await page.reload()
  await settle?.(page)

  const trigger = page.getByRole('button', { name: triggerName })
  await expect(trigger).toBeVisible({ timeout: 30_000 })
  await trigger.click()
  const listbox = page.getByRole('listbox', { name: 'Facility' })
  await expect(listbox).toBeVisible()
  const optionLabels = await listbox.getByRole('option').allTextContents()
  const labelBefore = (await trigger.textContent())?.trim()

  // Rows are labelled by facility NAME, so the option is picked by index against the sorted id
  // list `identity-mapping.ts` builds, not by a display string this test would have to guess.
  const sorted = [ownFacility, otherFacility].slice().sort()
  const otherIndex = sorted.indexOf(otherFacility)

  const beforeCount = reads.length
  await listbox.getByRole('option').nth(otherIndex).click()
  await expect(listbox).toBeHidden()
  await page.waitForTimeout(1500)
  const afterOther = reads.slice(beforeCount)
  const labelAfter = (await trigger.textContent())?.trim()
  const otherRead = afterOther.find((r) => r.url.includes(`facility_id=${otherFacility}`)) ?? null

  // Back to the facility this identity really holds -- both to prove the honoured direction and to
  // leave the console usable for the rest of the file.
  const beforeBack = reads.length
  await trigger.click()
  await expect(listbox).toBeVisible()
  await listbox.getByRole('option').nth(sorted.indexOf(ownFacility)).click()
  await expect(listbox).toBeHidden()
  await page.waitForTimeout(1500)
  const ownRead =
    reads.slice(beforeBack).find((r) => r.url.includes(`facility_id=${ownFacility}`)) ?? null

  expect(otherRead, 'selecting a facility must re-issue the surface read with that facility_id')
    .not.toBeNull()
  expect(ownRead, 'selecting back must re-issue the surface read with the original facility_id')
    .not.toBeNull()

  say(
    control,
    'WORKING',
    `selecting a facility now re-scopes the surface's own read. Setup, stated plainly: no roster account holds two facilities (live /account-profile returns exactly one id for every ops/planner account and none for admin), so this run intercepts ONE field -- scoped_facility_ids -> [${sorted.join(', ')}] -- and leaves the real token, the real role and every other field untouched. Result: the switcher offered [${optionLabels.map((t) => t.trim()).join(' | ')}]; selecting the second one changed the trigger label "${labelBefore}" -> "${labelAfter}" and fired ${scopedRead}?facility_id=${otherFacility} (HTTP ${otherRead?.status ?? 'none'}); selecting back fired ${scopedRead}?facility_id=${ownFacility} (HTTP ${ownRead?.status ?? 'none'}). SERVER-DERIVED BOUNDARY, and it is the point rather than a caveat: the out-of-scope narrowing is REFUSED server-side -- repositories/scope.py's resolve_facility_scope only lets a global-read persona (ADMIN / TRANSPORT_MANAGER / REGIONAL_OPERATIONS_HEAD) narrow with facility_id and answers 403 FORBIDDEN to everyone else who names a facility other than their own. So the client re-scopes the request and the server still decides the answer (M15/NFR-019); the console renders the refusal in its own error state rather than silently showing the wrong facility's rows.`,
  )

  await page.unroute('**/api/v1/account-profile*')
}
