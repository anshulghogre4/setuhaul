/**
 * Identity, scope and role-derived shell configuration.
 *
 * The governing rule (auth-and-scoping.md): **the interface never decides what a user may
 * see.** Scope arrives from the server, derived from the authenticated identity (M15).  The
 * types here describe what the server hands us; nothing in this file computes permission.
 *
 * The one thing derived on the client is *presentation* -- which rail destination, which
 * density, whether a facility switcher exists at all.  That derivation is a rendering
 * decision over data the server already authorised, never an authorisation decision.
 */

export type RoleName =
  | 'DRIVER'
  | 'OPERATIONS_EXECUTIVE'
  | 'OPERATIONS_MANAGER'
  | 'WAREHOUSE_PLANNER'
  | 'GATE_OFFICER'
  | 'TRANSPORT_MANAGER'
  | 'ADMIN'

/** One of the six surfaces.  A rail destination is a SURFACE, and this product has one
 *  surface per role (components.md section 7, the criterion added 2026-08-26). */
export type SurfaceId = 'driver' | 'ops' | 'planner' | 'gate' | 'carrier' | 'admin'

export type Density = 'compact' | 'comfortable' | 'spacious' | 'auth'

export type Facility = {
  id: string
  name: string
  /** 1-6.  Assigned by creation order; only ever rendered as the rail stripe or the
   *  switcher swatch (U59).  Never anywhere else. */
  accent: 1 | 2 | 3 | 4 | 5 | 6
}

/** A single role+scope pair the account holds.  An account with more than one of these
 *  sees the role picker at sign-in; an account with exactly one never does. */
export type RoleGrant = {
  role: RoleName
  /** Display label for the picker and the user menu's identity header. */
  roleLabel: string
  /** "Jaipur DC", "All facilities", or a carrier name.  What changes what a click means. */
  scopeLabel: string
}

export type Identity = {
  userId: string
  fullName: string
  initials: string
  email: string
  grants: RoleGrant[]
  activeRole: RoleName
  activeRoleLabel: string
  /** Facilities the user actually has, from the server.  Empty for carrier and driver. */
  facilities: Facility[]
  activeFacilityId: string | null
  /** True only for the cross-facility ops roles -- section 7.5.5 takes an optional
   *  facility_id, and omitting it means every facility in scope. */
  canSelectAllFacilities: boolean
  carrierId: string | null
}

export type RailDestination = {
  surface: SurfaceId
  path: string
  /** Spoken and shown when the rail is expanded. */
  label: string
}

/**
 * Rail destinations per role.
 *
 * Derived job-by-job from SOLUTION_DESIGN.md section 2's persona table cross-checked against
 * each role's own section 7.5.* catalog (U101) -- a job with no tool does not get a
 * destination.  Enumerated in iconography.md section "Rail destinations".
 *
 * **All five internal roles have exactly ONE destination.  This is owner-confirmed, not an
 * oversight, and it must not be "fixed" by adding icons to make the rail look busier --
 * that is precisely what U101 forbids.**  The rail earns its 56px by carrying the facility
 * accent stripe (U40), the active/scope indicator, and headroom for section 2's two
 * deferred personas (facility manager, regional ops head).
 *
 * Everything inside a surface is internal navigation and never a rail item:
 *   - Planner: Queue and Board are TABS.
 *   - Admin: Users / Rules / Policy / Audit are four TABS.
 *   - Gate: two device contexts on a SEGMENTED CONTROL.
 *   - Carrier: shipments, exceptions and the on-time tile are SECTIONS of one dashboard.
 *   - Settings is reached from the user menu, not the rail.
 */
const RAIL_BY_ROLE: Record<RoleName, RailDestination | null> = {
  // The PWA runs 320-768px.  A 56px rail expanding to a 240px overlay is not viable on a
  // 390px phone, and prompt 8 scopes the shell to "the five internal roles".
  DRIVER: null,
  OPERATIONS_EXECUTIVE: { surface: 'ops', path: '/ops', label: 'Exceptions' },
  OPERATIONS_MANAGER: { surface: 'ops', path: '/ops', label: 'Exceptions' },
  WAREHOUSE_PLANNER: { surface: 'planner', path: '/planner', label: 'Dock Command' },
  GATE_OFFICER: { surface: 'gate', path: '/gate', label: 'Yard' },
  TRANSPORT_MANAGER: { surface: 'carrier', path: '/carrier', label: 'Fleet' },
  ADMIN: { surface: 'admin', path: '/admin', label: 'Admin' },
}

export function railDestinationFor(role: RoleName): RailDestination | null {
  return RAIL_BY_ROLE[role]
}

/** Landing surface per role -- auth-and-scoping.md section "Role landing".
 *  GATE_OFFICER was added to that table on 2026-08-26; note the facility is the DEVICE's,
 *  not the user's, because the gate session is device-bound. */
export function landingPathFor(role: RoleName): string {
  return RAIL_BY_ROLE[role]?.path ?? '/driver'
}

/** Surface density, verbatim from spacing-and-layout.md's density table.
 *  Set ONCE per route at the shell root; never per component, never a user preference. */
const DENSITY_BY_SURFACE: Record<SurfaceId, Density> = {
  planner: 'compact',
  ops: 'compact',
  gate: 'spacious',
  carrier: 'comfortable',
  admin: 'comfortable',
  driver: 'comfortable',
}

export function densityFor(surface: SurfaceId): Density {
  return DENSITY_BY_SURFACE[surface]
}

/**
 * Facility switcher presence.
 *
 * Carriers are scoped by `carrier_id`, not by facility (section 7.5.6), so there is no
 * facility to switch between and no facility to colour.  The control is **absent from the
 * DOM**, not disabled -- scope-denied is Hidden (U83).  A greyed-out switcher would tell a
 * carrier that facilities exist as a thing this product can scope by, which is exactly the
 * structural leak auth-and-scoping.md's inference rule forbids.
 */
export function hasFacilityScope(role: RoleName): boolean {
  return role !== 'TRANSPORT_MANAGER' && role !== 'DRIVER'
}

/**
 * Status-bar field presence per role.  **Owner decision, 2026-08-27 — no longer open.**
 *
 * `spacing-and-layout.md` specifies the five fields once, for all roles, but two cannot
 * apply universally, and `mockup-shared-shell.html`'s artboard 31 flagged that rather than
 * resolving it inside a mockup.  Resolved as:
 *
 *   > **Only roles that have a facility show the policy version.**
 *
 * Which makes both fields the same predicate, deliberately:
 *
 *   - `facility` is omitted where the role has no facility scope at all.  Never a judgement
 *     -- rendering "Facility —" for a carrier would be inventing a fact they do not have.
 *   - `policyVersion` follows facility presence.  **Gate officers DO get it** (their session
 *     is facility-scoped, just device-bound rather than user-chosen), and **carriers do not**
 *     (scoped by `carrier_id`, §7.5.6 — structurally no `facility_id` to attach a policy
 *     version to).  This supersedes the earlier reading of the spec's "only where a decision
 *     receipt is rendered (planner, ops, admin)", which had excluded gate.
 *
 * They are kept as two named fields rather than collapsed into one boolean because they mean
 * different things at the call site; if the rule ever diverges again, this is where it does.
 */
export function statusBarFields(role: RoleName): { facility: boolean; policyVersion: boolean } {
  const facilityScoped = hasFacilityScope(role)
  return {
    facility: facilityScoped,
    policyVersion: facilityScoped,
  }
}

/** Idle timeout per surface -- auth-and-scoping.md section "Session expiry".
 *  `null` means no idle timeout at all.  Drivers must never be signed out mid-exception,
 *  and a gate officer cannot re-authenticate with gloves on every few minutes. */
export function idlePolicyFor(role: RoleName): { warnAtMin: number; signOutAtMin: number } | null {
  switch (role) {
    case 'DRIVER':
      return null
    case 'GATE_OFFICER':
      return null
    case 'WAREHOUSE_PLANNER':
    case 'OPERATIONS_EXECUTIVE':
    case 'OPERATIONS_MANAGER':
      return { warnAtMin: 55, signOutAtMin: 60 }
    case 'TRANSPORT_MANAGER':
    case 'ADMIN':
      return { warnAtMin: 25, signOutAtMin: 30 }
  }
}
