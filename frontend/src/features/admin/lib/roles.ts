/**
 * The role vocabulary the invite/edit form may offer, and the scope shape each role takes.
 *
 * **Mirrored from `backend/app/services/admin_user_service.py`, not from the mockup's role
 * dropdown**, because `invite_user` rejects anything outside `RoleName`
 * (`app/core/execution_context.py:6-18`) with a 422 before it ever reaches the Auth API. Offering
 * a role the backend cannot accept would produce a form that fails only on submit.
 *
 * **`GATE_OFFICER` was absent here until 2026-08-31, and is now offered — issue #79 landed.** The
 * previous comment recorded a real cross-surface finding: `mockup.html` §3.1's role list offers
 * "Gate–Yard officer", `core/auth/identity.ts` has `GATE_OFFICER`, and E5.4 built a whole gate/yard
 * surface for it, but the backend `RoleName` enum had no such member, so
 * `invite_user(role='GATE_OFFICER')` raised `INVALID_ROLE` before scope validation ran.
 *
 * **Both halves are now verified present, by reading the source rather than the issue** — and they
 * genuinely are two halves, either of which alone would still fail an invite:
 *  1. `RoleName.GATE_OFFICER` exists (`app/core/execution_context.py`), so the role passes
 *     `invite_user`'s enum check.
 *  2. `GATE_OFFICER` is in `admin_user_service.FACILITY_SCOPED_ROLES`, so `_validate_scope` maps
 *     it to a `FACILITY` scope and `users.facility_id` is actually written — which is what
 *     `get_execution_context` later resolves the kiosk's scope from. Without this entry the invite
 *     is refused outright.
 * That is why its `scope` below is `'facility'` and not `'none'`: it mirrors the set the backend
 * validates against, not a guess about what a kiosk role "feels like".
 *
 * A second, narrower version of the same class: `RoleName.CARRIER` and
 * `RoleName.REGIONAL_OPERATIONS_HEAD` / `RoleName.FACILITY_MANAGER` are all real backend roles
 * with no entry in the mockup's dropdown. They are offered here because the backend accepts them;
 * the mockup's five-item list is illustrative, not a closed set.
 */

/** What kind of scope id a role takes — mirrors `_validate_scope` (`admin_user_service.py:121`). */
export type ScopeKind =
  /** `GLOBAL_ROLES` (line 46): no scope id accepted or required. */
  | 'none'
  /** `FACILITY_SCOPED_ROLES` (lines 40-45): exactly one `facility_id`, validated to exist. */
  | 'facility'
  /** `RoleName.CARRIER` (lines 143-146): a `carrier_id`, required but NOT existence-checked. */
  | 'carrier'
  /** `RoleName.DRIVER` (lines 126-133): a `driver_id`, validated to exist. */
  | 'driver'

export type RoleOption = {
  /** The literal string sent as `role` — must match a `RoleName` member exactly. */
  value: string
  /** Display label. Where the mockup names one, its wording is used verbatim. */
  label: string
  scope: ScopeKind
}

export const ROLE_OPTIONS: RoleOption[] = [
  // "Ops coordinator" in mockup.html §3.2 — the facility-scoped ops role.
  { value: 'OPERATIONS_EXECUTIVE', label: 'Ops coordinator', scope: 'facility' },
  { value: 'OPERATIONS_MANAGER', label: 'Operations manager', scope: 'facility' },
  // "Planner" in mockup.html §3.1.
  { value: 'WAREHOUSE_PLANNER', label: 'Planner', scope: 'facility' },
  { value: 'FACILITY_MANAGER', label: 'Facility manager', scope: 'facility' },
  // "Gate–Yard officer" in mockup.html §3.1. Facility-scoped per
  // `admin_user_service.FACILITY_SCOPED_ROLES`; deliberately NOT in `OPS_PORTAL_ROLES` or any
  // wider tier, since the kiosk is a device-bound shared session with its own write guard.
  { value: 'GATE_OFFICER', label: 'Gate–Yard officer', scope: 'facility' },
  // "Carrier manager" in mockup.html §3.3 — scoped by carrier_id, not by facility.
  { value: 'CARRIER', label: 'Carrier manager', scope: 'carrier' },
  { value: 'TRANSPORT_MANAGER', label: 'Transport manager', scope: 'none' },
  { value: 'REGIONAL_OPERATIONS_HEAD', label: 'Regional operations head', scope: 'none' },
  // "Administrator" in mockup.html §3.5 — renders NO scope field at all, per screens.md §2:
  // "admin roles need no scope at all … doesn't apply to the role that assigns scope to
  // everyone else."
  { value: 'ADMIN', label: 'Administrator', scope: 'none' },
  { value: 'DRIVER', label: 'Driver', scope: 'driver' },
]

const BY_VALUE = new Map(ROLE_OPTIONS.map((r) => [r.value, r]))

export function roleOption(value: string): RoleOption | undefined {
  return BY_VALUE.get(value)
}

/**
 * Display label for a `role_name` coming back from `list_users`.
 *
 * An unrecognised role renders as its own raw value rather than a guessed label — the same rule
 * `facility-names.ts` applies to unknown facility ids. A role this frontend does not know about is
 * a fact worth showing, not one to smooth over.
 */
export function roleDisplayName(roleName: string): string {
  return BY_VALUE.get(roleName)?.label ?? roleName
}

export function scopeKindFor(roleName: string): ScopeKind {
  return BY_VALUE.get(roleName)?.scope ?? 'none'
}
