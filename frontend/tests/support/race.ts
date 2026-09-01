import { readFileSync } from 'node:fs'
import type { Browser, BrowserContext, Page } from 'playwright/test'

import { ACCOUNTS, type RoleKey } from './accounts'
import { API_BASE_URL } from './env'
import { storageStatePath } from './paths'
import type { StorageState } from './session'

/**
 * Helpers shared by the seven race suites.
 *
 * The governing idea (`TESTING_STRATEGY.md` §2): Playwright's job in this product is **"the loser
 * is told correctly"**, not "the invariant holds" -- that second one is Locust's, and issue #42
 * owns it. So these helpers are about getting two genuinely-separate authenticated users onto the
 * same screen, and reading what the losing one is shown.
 */

export function readStorageState(role: RoleKey): StorageState {
  return JSON.parse(readFileSync(storageStatePath(role), 'utf8')) as StorageState
}

export function accessTokenFor(role: RoleKey): string {
  const state = readStorageState(role)
  const entry = state.origins[0]?.localStorage.find((e) => e.name.startsWith('sb-'))
  if (!entry) throw new Error(`no supabase session in storageState for "${role}"`)
  return (JSON.parse(entry.value) as { access_token: string }).access_token
}

/**
 * A browser context carrying exactly one role's session.
 *
 * Each `browser.newContext()` is a fully isolated user -- its own cookies, localStorage,
 * sessionStorage, IndexedDB and service workers -- which is why two of them are two planners
 * (`TESTING_STRATEGY.md` §2). `storageState` is passed per-context from `storageStatePath(role)`;
 * there is no config-level default to fall back to.
 */
export async function contextForRole(browser: Browser, role: RoleKey): Promise<BrowserContext> {
  return browser.newContext({ storageState: storageStatePath(role) })
}

/** Two isolated contexts, one per role, plus a page each. Returns a disposer. */
export async function twoContexts(
  browser: Browser,
  roleA: RoleKey,
  roleB: RoleKey,
): Promise<{
  a: Page
  b: Page
  contexts: [BrowserContext, BrowserContext]
  dispose: () => Promise<void>
}> {
  const ctxA = await contextForRole(browser, roleA)
  const ctxB = await contextForRole(browser, roleB)
  const a = await ctxA.newPage()
  const b = await ctxB.newPage()
  return {
    a,
    b,
    contexts: [ctxA, ctxB],
    dispose: async () => {
      await ctxA.close()
      await ctxB.close()
    },
  }
}

/** Direct REST call as a role, for preconditions and cleanup -- never for the assertion itself. */
export async function apiAs<T = unknown>(
  role: RoleKey,
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
  headers?: Record<string, string>,
): Promise<{ status: number; body: { success?: boolean; data?: T; message?: string; errors?: Array<{ code?: string }> } | null }> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${accessTokenFor(role)}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  let parsed = null
  try {
    parsed = await res.json()
  } catch {
    /* the status is the useful part */
  }
  return { status: res.status, body: parsed }
}

/** The refusal code the backend put in the envelope, or '' if the call succeeded. */
export function refusalCode(r: { body: { errors?: Array<{ code?: string }> } | null }): string {
  return r.body?.errors?.[0]?.code ?? ''
}

export function facilityOf(role: RoleKey): string {
  const f = ACCOUNTS[role].facilityId
  if (!f) throw new Error(`role "${role}" has no facility scope`)
  return f
}

/**
 * Fires two actions as close to simultaneously as the runtime allows.
 *
 * `Promise.all` over two already-primed callbacks is the practical ceiling in-process --
 * `TESTING_STRATEGY.md` §9 item 2 makes the same honesty point about Locust ("ramping 50 VUs is not
 * the same as 50 requests landing together"). It is genuine concurrency at the server, which is
 * what these races need, but it is not a hardware barrier and is not claimed to be.
 */
export async function simultaneously<A, B>(
  first: () => Promise<A>,
  second: () => Promise<B>,
): Promise<[PromiseSettledResult<A>, PromiseSettledResult<B>]> {
  const results = await Promise.allSettled([first(), second()])
  return results as [PromiseSettledResult<A>, PromiseSettledResult<B>]
}

/**
 * The nine types `escalation_service.ESCALATION_TYPES` accepts. Rotating over them is how
 * `createFreshEscalation` gets a genuinely new row -- see below.
 */
export const ESCALATION_TYPES = [
  'NO_FEASIBLE_SLOT',
  'PENDING_EXPIRED_UNACTIONED',
  'AMBIGUOUS_SHIPMENT',
  'LOW_CONFIDENCE_ETA',
  'WAREHOUSE_REPLY_CONFLICT',
  'NOTIFICATION_FAILED',
  'NOTIFICATION_UNROUTABLE',
  'SAFETY_OR_REGULATED',
  'CAPACITY_EVENT_CASCADE',
] as const

/**
 * Creates an escalation that is genuinely **OPEN and unowned**, or returns null.
 *
 * `POST /operations/escalate` is not a plain insert. `escalation_service.py:135-160`:
 *
 *     dedupe_key = f"{shipment_id}:{day}:{escalation_type}"
 *     ... ON CONFLICT (dedupe_key) DO UPDATE SET payload_json = ..., severity_code = ...
 *
 * The `DO UPDATE` refreshes the payload but **never resets `escalation_status`**. So re-escalating
 * the same shipment and type on the same calendar day hands back the EXISTING row in whatever
 * state it is already in -- ACKNOWLEDGED, or even CANCELLED by a previous test's teardown.
 *
 * Found the hard way: races 3 and 4 each passed alone and then failed when run in sequence,
 * because the second run silently reused the first run's already-actioned escalation and both
 * coordinators were told `ALREADY_ACTIONED`. A suite that races an already-decided row is testing
 * nothing, so this helper verifies the row is actually OPEN and unowned before handing it back,
 * rotating the escalation type until it finds a free dedupe key.
 */
export async function createFreshEscalation(
  role: RoleKey,
  shipmentId: string,
): Promise<{ escalationId: string; escalationType: string } | null> {
  for (const escalationType of ESCALATION_TYPES) {
    const created = await apiAs<{ escalation_id?: string }>(role, 'POST', '/api/v1/operations/escalate', {
      shipment_id: shipmentId,
      escalation_type: escalationType,
      severity_code: 'HIGH',
      payload: { source: 'E6.2 race suite (issue #43)' },
      confirmed: true,
    })
    const escalationId = created.body?.data?.escalation_id
    if (created.status !== 200 || !escalationId) continue

    const queue = await apiAs<{
      items?: Array<{ escalation_id?: string; escalation_status?: string; owner_user_id?: string | null }>
    }>(role, 'GET', '/api/v1/operations/escalation-queue')
    const row = (queue.body?.data?.items ?? []).find((i) => i.escalation_id === escalationId)
    if (row?.escalation_status === 'OPEN' && !row.owner_user_id) {
      return { escalationId, escalationType }
    }
    // Reused a stale row for this (shipment, day, type). Try the next type.
  }
  return null
}

/** Demo-cast guard. `SHP-D16-*` is the shared presentation cast and must never be written to. */
export function assertNotDemoCast(shipmentId: string): void {
  if (shipmentId.startsWith('SHP-D16-')) {
    throw new Error(
      `Refusing to write to ${shipmentId}: SHP-D16-* is the shared demo cast ` +
        `(POC_TEAM_ACCOUNTS.local.md, supabase/demo/README.md). Use a sandbox entity.`,
    )
  }
}
