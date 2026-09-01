import { landingPathFor, type RoleName } from '@/core/auth/identity'

/**
 * Which roles may *open* which surface.
 *
 * ## This is presentation, not authorisation. Read this before changing it.
 *
 * The server is and remains the authority (M15, `auth-and-scoping.md`'s governing rule). Every
 * table below is a **mirror** of a `require_roles(...)` gate that already exists in the backend,
 * copied from source and cited per row. Its only job is to stop the client rendering a console
 * whose every request the server will refuse -- a planner who lands on `/admin` should be taken to
 * their own surface, not shown an admin console that 403s on load. Deleting this file would leak
 * no data and grant no permission; it would only make the app less honest about what it can do.
 *
 * The consequence of a mismatch is therefore a UX bug in one direction and *only* a UX bug in the
 * other: too narrow here hides a surface a user could legitimately use; too wide here shows a
 * surface whose reads 403. Neither can grant access, because no read here is trusted by anything.
 *
 * ## Rows, and the server gate each one mirrors (read 2026-09-01)
 *
 * | Route | Backend gate | File |
 * |---|---|---|
 * | `/driver` | `require_roles(RoleName.DRIVER)` | `api/v1/routers/driver.py`, `chat.py` |
 * | `/planner` | `require_roles(WAREHOUSE_PLANNER, ADMIN)` | `planner.py:38` |
 * | `/ops` | `require_roles(*OPS_PORTAL_ROLES)` | `operations.py:93+`, set at `deps.py:84-92` |
 * | `/gate` | `require_roles(*GATE_KIOSK_ROLES)` | `gate.py:75`, set at `deps.py:99-104` |
 * | `/carrier` | `require_roles(RoleName.CARRIER)` | `carrier.py:33` |
 * | `/admin` | `require_roles(RoleName.ADMIN)` | `admin.py:72` |
 * | `/settings` | any authenticated caller (`AnyCtx`) | `shared.py:105-136` |
 *
 * Two rows are narrower than the backend set purely because the UI `RoleName` union has no member
 * for the missing roles: `FACILITY_MANAGER` and `REGIONAL_OPERATIONS_HEAD` are in the backend's
 * `OPS_PORTAL_ROLES` / `GATE_KIOSK_ROLES` but do not exist in `core/auth/identity.ts` at all --
 * `identity-mapping.ts` refuses such a session outright with a named error, so it can never reach
 * a guard.
 *
 * ### `/gate` -- a deliberate deviation from the brief, flagged rather than taken silently
 *
 * The task brief suggested "gate = any authenticated facility-scoped role", on the grounds that
 * nothing under `features/gate/**` imports `RoleName`. That is true of the *feature folder* but
 * not of the *server*: `gate.py:75` gates every kiosk tool on `GATE_KIOSK_ROLES`
 * (`GATE_OFFICER`, `WAREHOUSE_PLANNER`, `FACILITY_MANAGER`, `ADMIN` -- `deps.py:99-104`), which
 * excludes `OPERATIONS_EXECUTIVE` and `OPERATIONS_MANAGER`. Sending an ops coordinator to a kiosk
 * where gate-in, call-to-dock and gate-out all 403 is exactly the dead surface this file exists to
 * prevent, so the server's own set is mirrored instead. Race suite 6 drives `/gate` as
 * `WAREHOUSE_PLANNER` (`tests/support/accounts.ts`), which is inside the set, so this is not a
 * behaviour change for any existing test.
 */
const ALLOWED_ROLES: Record<string, readonly RoleName[] | 'any'> = {
  '/driver': ['DRIVER'],
  '/planner': ['WAREHOUSE_PLANNER', 'ADMIN'],
  '/ops': [
    'OPERATIONS_EXECUTIVE',
    'OPERATIONS_MANAGER',
    'WAREHOUSE_PLANNER',
    'TRANSPORT_MANAGER',
    'ADMIN',
  ],
  '/gate': ['GATE_OFFICER', 'WAREHOUSE_PLANNER', 'ADMIN'],
  '/carrier': ['TRANSPORT_MANAGER'],
  '/admin': ['ADMIN'],
  // Settings is per-user preferences and read-only identity; every signed-in role has one.
  '/settings': 'any',
}

/** The surface prefixes, longest first, so `/driver/t/x` resolves to `/driver` and not to `/`. */
const PREFIXES = Object.keys(ALLOWED_ROLES).sort((a, b) => b.length - a.length)

/** The surface a path belongs to, or `null` for a path this table says nothing about. */
export function surfaceForPath(pathname: string): string | null {
  return (
    PREFIXES.find((p) => pathname === p || pathname.startsWith(`${p}/`)) ?? null
  )
}

/**
 * May this role open this path?
 *
 * A path outside the table (`/`, `/signin`, `*`, the `_states` galleries) returns `true` -- this
 * function answers "is this role wrong for this surface", not "does this route exist". Route
 * existence is `App.tsx`'s job and a 404 is its answer.
 */
export function canAccess(role: RoleName, pathname: string): boolean {
  const surface = surfaceForPath(pathname)
  if (surface === null) return true
  const allowed = ALLOWED_ROLES[surface]
  return allowed === 'any' || allowed.includes(role)
}

/**
 * Where this role belongs. Delegates to `identity.ts`'s `landingPathFor`, which derives from
 * `RAIL_BY_ROLE` -- itself derived from `auth-and-scoping.md`'s "Role landing" table. Deliberately
 * not a second table: one role->surface mapping, or they drift.
 */
export function homePathFor(role: RoleName): string {
  return landingPathFor(role)
}
