import { appendFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

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
