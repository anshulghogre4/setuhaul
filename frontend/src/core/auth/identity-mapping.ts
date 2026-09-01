import type { Facility, Identity, RoleGrant, RoleName } from '@/core/auth/identity'
import { facilityDisplayName } from '@/features/ops/lib/facility-names'
import { roleDisplayName } from '@/features/admin/lib/roles'
import type { MeProfile } from '@/core/http/api'

/**
 * **THE identity-mapping site.** Server truth (`GET /api/v1/auth/me`) -> the UI's `Identity`.
 *
 * This is the file that replaced the `PLANNER_MULTI_ROLE` / `OPS_MANAGER` / `ADMIN_IDENTITY`
 * fixture seam (TODO #52). Everything the shell renders about *who is signed in* now originates
 * here, from a verified token the backend resolved server-side.
 *
 * The governing rule from `core/auth/identity.ts` still holds and is why this file computes no
 * permission at all: **the interface never decides what a user may see** (M15). What it produces
 * is presentation -- a label, a rail destination, a density -- over facts the server already
 * authorised.
 *
 * ## Two imports that point the "wrong" way, on purpose
 *
 * `core/` importing from `features/` is a layering inversion, and it is taken deliberately over
 * the alternative:
 *
 *  - `features/admin/lib/roles.ts` already holds the role vocabulary **mirrored from
 *    `backend/app/core/execution_context.py`'s `RoleName` enum**, with a `roleDisplayName` that
 *    renders an unknown role as its own raw value rather than a guessed label.
 *  - `features/ops/lib/facility-names.ts` already holds the id->name lookup, with the rule that
 *    *"an unknown id renders as itself, never a guessed name"* -- because only two of the six
 *    seeded facilities have a documented name anywhere in scope.
 *
 * Both are pure data modules with no imports of their own, so nothing is dragged into the entry
 * chunk. Copying either into `core/` to satisfy the layering rule would create a second table that
 * silently drifts from the backend, which is a worse failure than an import that points sideways.
 * Moving them both to `core/auth/` is the real fix and is a separate change.
 */

/**
 * Backend `role_name` -> the UI's `RoleName`.
 *
 * These two enums are **not the same set**, which is a real, pre-existing drift (issue #79's
 * family) rather than something this mapping introduced. Verified by reading both:
 *
 * | Backend (`execution_context.py:6-25`) | UI (`identity.ts:13-21`) | Resolution here |
 * |---|---|---|
 * | `DRIVER`, `OPERATIONS_EXECUTIVE`, `OPERATIONS_MANAGER`, `WAREHOUSE_PLANNER`, `GATE_OFFICER`, `TRANSPORT_MANAGER`, `ADMIN` | same | 1:1 |
 * | `CARRIER` | *(absent)* | -> `TRANSPORT_MANAGER`, see below |
 * | `FACILITY_MANAGER`, `REGIONAL_OPERATIONS_HEAD` | *(absent)* | no UI role -> honest refusal |
 *
 * **`CARRIER` -> `TRANSPORT_MANAGER`.** `backend/app/api/v1/routers/carrier.py:33` gates the whole
 * carrier portal on `require_roles(RoleName.CARRIER)`, while `identity.ts:98` maps the UI's
 * `TRANSPORT_MANAGER` to the carrier surface and E5.5 built that surface against it
 * (`features/gallery/fixtures.ts`'s `CARRIER` identity has `activeRole: 'TRANSPORT_MANAGER'`).
 * So the UI's `TRANSPORT_MANAGER` *is* the backend's `CARRIER` under a different name, and a real
 * carrier user would otherwise have no surface at all.
 *
 * ⚠ **FORK for the owner, not silently decided.** The backend also has a *separate*
 * `TRANSPORT_MANAGER` role, and it is in `OPS_PORTAL_ROLES` (`deps.py:84-92`) but **not** accepted
 * by any `/carrier/*` route. So a user whose server role is literally `TRANSPORT_MANAGER` lands on
 * `/carrier` per `identity.ts` and would get 403 on every read there. No such account exists in
 * the POC roster (`frontend/tests/support/accounts.ts`), so this is latent rather than live. The
 * two candidate fixes are (a) add `CARRIER` to the UI `RoleName` union and give
 * `TRANSPORT_MANAGER` the ops rail, or (b) retire the backend's `TRANSPORT_MANAGER`. Both change
 * shared infrastructure and belong to whoever owns #79.
 */
const UI_ROLE_BY_SERVER_ROLE: Record<string, RoleName> = {
  DRIVER: 'DRIVER',
  OPERATIONS_EXECUTIVE: 'OPERATIONS_EXECUTIVE',
  OPERATIONS_MANAGER: 'OPERATIONS_MANAGER',
  WAREHOUSE_PLANNER: 'WAREHOUSE_PLANNER',
  GATE_OFFICER: 'GATE_OFFICER',
  TRANSPORT_MANAGER: 'TRANSPORT_MANAGER',
  CARRIER: 'TRANSPORT_MANAGER',
  ADMIN: 'ADMIN',
  // FACILITY_MANAGER and REGIONAL_OPERATIONS_HEAD are absent on purpose. `identity.ts:80-81`
  // names them as SOLUTION_DESIGN section 2's "two deferred personas" -- they have no rail
  // destination, no surface and no screens. Mapping either onto a borrowed surface would hand
  // someone a console built for a different job. `toIdentity` refuses instead, naming the role.
}

export function uiRoleFor(serverRoleName: string): RoleName | null {
  return UI_ROLE_BY_SERVER_ROLE[serverRoleName] ?? null
}

/**
 * Initials for the avatar. First + last word of the full name, uppercased.
 *
 * Falls back to the email's first character rather than rendering an empty circle -- `/auth/me`
 * guarantees `email` but `full_name` is a nullable-ish free-text column in `public.users`.
 */
function initialsFrom(fullName: string, email: string): string {
  const words = fullName.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return (email[0] ?? '?').toUpperCase()
  const first = words[0][0] ?? ''
  const last = words.length > 1 ? (words[words.length - 1][0] ?? '') : ''
  return (first + last).toUpperCase()
}

/**
 * Facility accent 1-6.
 *
 * `identity.ts:31-33` says the accent is "assigned by creation order", and **no server read
 * exposes creation order** -- `/auth/me` returns one `facility_id` and
 * `GET /api/v1/account-profile` returns `scoped_facility_ids` as an unordered list of ids
 * (`backend/app/services/account_service.py:76-87`). So the accent is derived from the id's
 * position in a *sorted* list, which is stable across reloads and across the two reads, and is
 * the closest honest approximation available. It is only ever rendered as the rail stripe or the
 * switcher swatch, so a wrong hue is cosmetic, never a fact about a shipment.
 */
function accentFor(index: number): Facility['accent'] {
  return ((index % 6) + 1) as Facility['accent']
}

/**
 * The extra fields `GET /api/v1/account-profile` adds over `/auth/me`.
 *
 * Only `scoped_facility_ids` is used here, and it is the one field that matters: `/auth/me`
 * returns the single `users.facility_id` column, while `user_scopes` is the only source that can
 * express **more than one facility per user** (`account_service.get_account_profile`'s own
 * docstring). Without it a multi-facility planner would render a facility switcher with exactly
 * one entry.
 */
export type AccountProfile = {
  user_id: string
  full_name: string | null
  email: string | null
  phone_number: string | null
  employee_code: string | null
  role_name: string
  facility_id: string | null
  driver_id: string | null
  is_active: number | boolean
  last_login_ts: string | null
  scoped_facility_ids: string[]
}

/**
 * One `(role x scope)` pair, exactly as `GET /api/v1/auth/me` now returns it (issue #52,
 * `backend/app/services/auth_grants_service.py`).
 *
 * **`role_name` is the same on every entry, and that is the schema's answer, not a simplification.**
 * `public.users.role_id` is a single `NOT NULL` FK to `roles` -- one account cannot hold two roles
 * -- while `public.user_scopes` is a child table with `UNIQUE (user_id, scope_type, scope_value)`
 * and no per-user cap. So issue #52's "multi-role identity" resolves to **one role, multiple
 * facility/carrier scopes**, and this array is the scope list, not a role list.
 *
 * `scope_type` is the server naming its own branch rather than the client inferring one from which
 * id happens to be non-null -- the same discipline `canSelectAllFacilities` already follows for
 * `scope.type` below. `GLOBAL` and `NONE` are not `user_scopes.scope_type` values (that column's
 * CHECK allows only FACILITY/CARRIER/DRIVER); they name the two cases where reach is the *absence*
 * of a scope row.
 *
 * Declared here rather than in `core/http/api.ts`'s `MeProfile` **only because this task's file
 * scope did not include that file**; folding it in there is the tidier home and a one-line
 * follow-up. `toIdentity` accepts `MeProfile & { grants?: ServerGrant[] }`, which a plain
 * `MeProfile` satisfies, so no caller changes and a backend that predates #52 still works.
 */
export type ServerGrant = {
  role_name: string
  scope_type: 'FACILITY' | 'CARRIER' | 'DRIVER' | 'GLOBAL' | 'NONE' | (string & {})
  facility_id: string | null
  facility_name?: string | null
  carrier_id: string | null
}

/** Raised when the server's role has no surface in this application. Carries the role name so the
 *  UI can say which one, rather than showing a blank screen or a broken redirect. */
export class UnmappedRoleError extends Error {
  readonly roleName: string
  constructor(roleName: string) {
    super(`No SetuHaul surface exists for the role "${roleName}".`)
    this.name = 'UnmappedRoleError'
    this.roleName = roleName
  }
}

/**
 * Server profile -> `Identity`. The single mapping function.
 *
 * `profile` is optional: `/auth/me` alone is enough to render the whole shell, and
 * `/account-profile` only widens the facility list. A failure to read the second one is
 * therefore not a reason to refuse a session (see `auth-context.tsx`, which fetches it
 * best-effort).
 *
 * @throws {UnmappedRoleError} when `role_name` has no UI surface.
 */
export function toIdentity(
  me: MeProfile & { grants?: ServerGrant[] },
  profile?: AccountProfile | null,
): Identity {
  const role = uiRoleFor(me.role_name)
  if (role === null) throw new UnmappedRoleError(me.role_name)

  const serverGrants = me.grants ?? []

  /**
   * `grants[]` is a third source of facility ids, and the most reliable of the three: it is
   * `user_scopes` unioned with the `users.facility_id` mirror, computed server-side
   * (`auth_grants_service._facility_ids_in_scope`). Folding it in means the facility switcher stays
   * complete even when the best-effort `/account-profile` read fails, which `auth-provider.tsx`
   * explicitly tolerates. Still server-derived, so M15 is untouched -- this widens the list only
   * with ids the server itself just authorised.
   */
  const facilityIds = [
    ...new Set(
      [
        ...(profile?.scoped_facility_ids ?? []),
        ...serverGrants.map((g) => g.facility_id),
        me.facility_id,
      ].filter((id): id is string => typeof id === 'string' && id.length > 0),
    ),
  ].sort()

  const facilities: Facility[] = facilityIds.map((id, i) => ({
    id,
    name: facilityDisplayName(id),
    accent: accentFor(i),
  }))

  /**
   * `identity.ts:57-59`: "True only for the cross-facility ops roles -- section 7.5.5 takes an
   * optional facility_id, and omitting it means every facility in scope."
   *
   * ## Read off the SERVER's own scope, not off a role guess (changed 2026-09-01, issue #99)
   *
   * This was `role === 'OPERATIONS_MANAGER'`, and that was wrong against the live backend --
   * latent only because the switcher's selection went nowhere. `GET /api/v1/auth/me` reports
   * `scope.type = "global_read_only" if ctx.has_global_read_scope else ...`
   * (`backend/app/api/v1/routers/health_auth.py:57-61`), and `has_global_read_scope` is
   * `{ADMIN, TRANSPORT_MANAGER, REGIONAL_OPERATIONS_HEAD}` (`execution_context.py:106-117`) --
   * **`OPERATIONS_MANAGER` is not in it.** `resolve_facility_scope` branches on exactly that
   * property (`repositories/scope.py:46-49`), so for an operations manager, omitting `facility_id`
   * does *not* mean "every facility": the server silently scopes the read to their own facility
   * and the UI would have labelled one facility's rows "All facilities". That is the inference
   * leak `auth-and-scoping.md` forbids, stated as a fact about scope rather than about data.
   *
   * `scope.type` is the honest predicate because it is the server reporting its own branch. The
   * `permissions` fallback covers a deployment whose `/auth/me` predates the `scope` object;
   * `*_read_global` is what `ROLE_PERMISSIONS` grants exactly those three personas
   * (`backend/app/core/deps.py`).
   */
  const canSelectAllFacilities =
    me.scope?.type === 'global_read_only' ||
    (me.permissions ?? []).some((p) => p.endsWith(':read_global'))

  const roleLabel = roleDisplayName(me.role_name)

  /**
   * **THE #52 grants[] SEAM -- server-fed since 2026-09-01.**
   *
   * Steps 1 and 2 of the recipe this comment used to carry are done: `/auth/me` now returns a real
   * `grants[]` (`backend/app/api/v1/routers/health_auth.py`, built by
   * `app/services/auth_grants_service.resolve_grants`) and the single-element literal below is a
   * `.map()` over it. A multi-facility ops account -- the only kind the schema can produce, since
   * `users.role_id` is a single FK -- now yields one entry per facility.
   *
   * **Step 3 is deliberately NOT done here**: rendering `<RolePicker>` after sign-in when
   * `grants.length > 1` needs `core/auth/auth-provider.tsx` (to hold the chosen grant) and
   * `App.tsx` (to route to it), neither of which is in this change's file scope. Until then a
   * multi-grant account signs straight into its role's landing surface, which is the pre-#52
   * behaviour -- correct, just not yet offering the choice. `RolePicker` already refuses to render
   * with fewer than two rows, so wiring it is additive.
   *
   * The fallback branch is not dead code: it covers a **deployed backend that predates #52**, the
   * same reason `canSelectAllFacilities` above keeps its `permissions` fallback. Vercel ships the
   * frontend on push while the backend deploys separately, so the two are routinely a version apart.
   *
   * No component changes: everything downstream already consumes `Identity.grants`, and nothing
   * else in `src/` constructs a `RoleGrant`.
   */
  const grants: RoleGrant[] =
    serverGrants.length > 0
      ? serverGrants.map((g) => ({
          // The server sends the same `role_name` on every entry (one role per account), so this
          // is `role` in practice. Resolved per entry anyway rather than reused: if a grant ever
          // did name a role this UI has no surface for, falling back to the caller's own resolved
          // role is a strictly better failure than an undefined rail destination -- and
          // `toIdentity` has already refused outright above if the *account's* role is unmapped.
          role: uiRoleFor(g.role_name) ?? role,
          roleLabel: roleDisplayName(g.role_name),
          scopeLabel: grantScopeLabel(g, role, canSelectAllFacilities),
        }))
      : [
          {
            role,
            roleLabel,
            scopeLabel: scopeLabelFor(role, me.facility_id, canSelectAllFacilities),
          },
        ]

  /**
   * The `carrierId` gap this file used to record as "real, not an oversight" is closed: the
   * `CARRIER` grant carries it, sourced from `user_scopes(scope_type='CARRIER')` exactly as
   * `ExecutionContext.carrier_id` is (`core/deps.py`). Still `null` for every non-carrier account,
   * and still not used for any authorisation decision -- every carrier read is scoped server-side
   * from the token, so this is a fact to display, never one to act on.
   */
  const carrierId = serverGrants.find((g) => g.carrier_id)?.carrier_id ?? null

  return {
    userId: me.user_id,
    fullName: me.full_name || me.email,
    initials: initialsFrom(me.full_name ?? '', me.email),
    email: me.email,
    grants,
    activeRole: role,
    activeRoleLabel: roleLabel,
    facilities,
    activeFacilityId: me.facility_id,
    canSelectAllFacilities,
    carrierId,
  }
}

/**
 * A server grant's scope label -- "Jaipur", "All facilities", a carrier, or the role's own name.
 *
 * The facility branch prefers this app's own SHORT name over the database's full one, and that
 * order is deliberate. `facilities.facility_name` is "SetuHaul Jaipur Distribution Centre"; the
 * rail, the queue row and the picker all want "Jaipur" (`facility-names.ts`, U91). But the local
 * table knows only two of the six facilities section 2 names, and its rule is *"an unknown id
 * renders as itself, never a guessed name"* -- so `facility_name` fills exactly that hole with a
 * real name from the database rather than a raw `FAC-...` id. Neither source is ever guessed.
 */
function grantScopeLabel(
  grant: ServerGrant,
  fallbackRole: RoleName,
  canSelectAllFacilities: boolean,
): string {
  if (grant.scope_type === 'CARRIER') return roleDisplayName('CARRIER')
  if (grant.scope_type === 'GLOBAL') return 'All facilities'
  if (grant.facility_id) {
    const short = facilityDisplayName(grant.facility_id)
    // `facilityDisplayName` returns the id unchanged when it has no entry -- that is the signal
    // there is no short name, not a coincidence worth hiding.
    if (short !== grant.facility_id) return short
    return grant.facility_name || grant.facility_id
  }
  return scopeLabelFor(fallbackRole, null, canSelectAllFacilities)
}

/**
 * "Jaipur", "All facilities", or a carrier's name -- `identity.ts:42-43`: *"What changes what a
 * click means."*
 *
 * The carrier case genuinely has nothing to render: there is no `carrier_id` in any read (see
 * above) and no carrier-name endpoint at all, so it falls back to the role label rather than
 * inventing a company name. `features/carrier/carrier-portal.tsx:95-97` reads this exact field
 * for its header, and would rather show "Carrier manager" than a fabricated customer.
 */
function scopeLabelFor(
  role: RoleName,
  facilityId: string | null,
  canSelectAllFacilities: boolean,
): string {
  if (role === 'TRANSPORT_MANAGER') return roleDisplayName('CARRIER')
  if (facilityId) return facilityDisplayName(facilityId)
  return canSelectAllFacilities ? 'All facilities' : roleDisplayName(role)
}
