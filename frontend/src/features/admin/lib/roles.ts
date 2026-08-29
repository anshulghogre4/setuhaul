/**
 * The role vocabulary the invite/edit form may offer, and the scope shape each role takes.
 *
 * **Mirrored from `backend/app/services/admin_user_service.py`, not from the mockup's role
 * dropdown**, because `invite_user` rejects anything outside `RoleName`
 * (`app/core/execution_context.py:6-18`) with a 422 before it ever reaches the Auth API. Offering
 * a role the backend cannot accept would produce a form that fails only on submit.
 *
 * ⚠ **`GATE_OFFICER` is deliberately absent, and this is a real cross-surface finding, not an
 * omission.** `mockup.html` §3.1's role list offers "Gate–Yard officer", `frontend/src/core/auth/
 * identity.ts:18` has `GATE_OFFICER` as a `RoleName`, and E5.4 is building a whole gate/yard
 * surface for it — but the **backend `RoleName` enum has no `GATE_OFFICER` member at all**
 * (checked directly, 2026-08-29). `invite_user(role='GATE_OFFICER')` raises `INVALID_ROLE` at
 * `admin_user_service.py:200-202` before any scope validation runs. Reported to the owner rather
 * than worked around here.
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
