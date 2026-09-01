import type { Identity } from '@/core/auth/identity'

/**
 * The viewer's ACTIVE facility: which of the facilities the server already granted them the
 * desk surfaces should currently be reading.
 *
 * Issue #99.1. Before this existed, `App.tsx`'s `ShellRoute` passed `onFacilityChange={() => {}}`
 * and the switcher was a fully-built popover whose selection went nowhere.
 *
 * ## The rule this file exists to enforce (M15 / NFR-019)
 *
 * **A facility id is never something the client decides.** `identity.facilities` is the
 * server's answer (`/auth/me`'s `facility_id` plus `/account-profile`'s `scoped_facility_ids`,
 * see `identity-mapping.ts`), and `selectableFacilityIds` below is the ONLY set an id may come
 * from -- including an id restored from localStorage, which is attacker-writable and is
 * therefore validated on read exactly like a fresh click. Choosing a facility is a *narrowing
 * request* the server re-derives on every call
 * (`backend/app/repositories/scope.py::resolve_facility_scope`); it is never an assertion of
 * scope, and nothing here grants reach.
 *
 * ## Where the narrowing is actually honoured, and where it is not
 *
 * `resolve_facility_scope` only lets a **global-read persona** (`ctx.has_global_read_scope` --
 * ADMIN / TRANSPORT_MANAGER / REGIONAL_OPERATIONS_HEAD, `execution_context.py:106-117`) narrow
 * with `facility_id`. For every other persona it answers `ctx.facility_id` and raises
 * `FORBIDDEN` if a *different* facility was asked for. So a `WAREHOUSE_PLANNER` who somehow
 * holds two `user_scopes` rows can select the second one here and the server will refuse the
 * read -- correctly, and visibly, rather than silently serving the wrong facility's data. That
 * refusal is the boundary, and it is the server's to draw; the client does not pre-empt it by
 * hiding an option the identity genuinely lists.
 */

/** Sentinel for "no facility filter" -- the switcher's "All facilities" row. Never sent on the
 *  wire: `facilityIdForReads` maps it to `null`, and §7.5.5's `facility_id` is optional precisely
 *  so that omitting it means "every facility in scope". */
export const ALL_FACILITIES = '__all__'

/**
 * Every id the switcher may legitimately produce for this identity.
 *
 * `canSelectAllFacilities` is itself server-derived (`identity-mapping.ts` reads
 * `/auth/me`'s `scope.type === 'global_read_only'`), so the sentinel is only in the set for a
 * persona whose narrowing the backend will actually honour.
 */
export function selectableFacilityIds(identity: Identity): Set<string> {
  const ids = new Set(identity.facilities.map((f) => f.id))
  if (identity.canSelectAllFacilities) ids.add(ALL_FACILITIES)
  return ids
}

/** The value a read's optional `facility_id` query parameter should carry. `null` means "send no
 *  facility_id at all", which is what "All facilities" means on the wire. */
export function facilityIdForReads(activeFacilityId: string | null): string | null {
  if (activeFacilityId === null || activeFacilityId === ALL_FACILITIES) return null
  return activeFacilityId
}

/**
 * Persistence, per viewer.
 *
 * Keyed by `user_id` so a shared desk machine never hands the next person the previous person's
 * facility -- and because the value is only ever *applied* after `selectableFacilityIds` accepts
 * it, a stale key belonging to someone else is inert rather than dangerous.
 *
 * Every access is wrapped: `localStorage` throws in a Safari private window and on a browser with
 * storage blocked, and a facility preference is not worth a blank screen. A failure here means the
 * choice lasts the session instead of surviving a reload, which is the correct degradation.
 */
const STORAGE_PREFIX = 'setuhaul.activeFacility.'

export function readStoredFacilityChoice(userId: string): string | null {
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + userId)
  } catch {
    return null
  }
}

export function writeStoredFacilityChoice(userId: string, facilityId: string): void {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + userId, facilityId)
  } catch {
    /* storage unavailable -- the choice still applies for this session; see above */
  }
}
