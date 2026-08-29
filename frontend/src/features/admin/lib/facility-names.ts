/**
 * Facility id -> display name for the Users and Facility Rules tables.
 *
 * Deliberately a **local copy** of the same two-entry map `features/ops/lib/facility-names.ts`
 * holds, not an import from it: cross-feature imports couple two surfaces that are owned and
 * built separately, and this build runs concurrently with two others in the same tree. If a real
 * facilities read ever lands (see below), both copies collapse into it rather than into each
 * other.
 *
 * Only **two** facility names are documented anywhere in scope, per
 * `frontend/src/features/gallery/fixtures.ts`'s own comment ("Jaipur DC, Gurugram Cross-Dock …
 * the names are not stated anywhere and are deliberately not invented here"). An unknown id
 * renders as itself, never a guessed name.
 *
 * ⚠ **There is no facilities-list endpoint anywhere in the API** — checked 2026-08-29: no route
 * in `backend/app/api/v1/routers/` returns `facilities`. That is why the Users and Facility Rules
 * filters derive their option list from the `facility_id` values actually present in the rows
 * they already fetched (`facilityOptionsFrom` below) rather than from a proper read, and why the
 * invite form's facility picker can only offer facilities that already have a user or a rule.
 * Reported as a new finding, not silently absorbed.
 */

const KNOWN_FACILITY_NAMES: Record<string, string> = {
  'FAC-JAI-01': 'Jaipur',
  'FAC-GGN-01': 'Gurugram',
}

export function facilityDisplayName(facilityId: string): string {
  return KNOWN_FACILITY_NAMES[facilityId] ?? facilityId
}

/**
 * Distinct facility ids observed across whatever rows are already loaded, sorted by display name.
 *
 * An honest, stated approximation of a facilities read, not a substitute presented as one — see
 * this file's header. Null/empty ids (global-role users, for instance) are dropped rather than
 * rendered as an "unscoped" option, because that would be a filter value the server does not
 * accept.
 */
export function facilityOptionsFrom(
  ...rowSets: Array<Array<{ facility_id: string | null }>>
): Array<{ id: string; name: string }> {
  const ids = new Set<string>()
  for (const rows of rowSets) {
    for (const row of rows) {
      if (row.facility_id) ids.add(row.facility_id)
    }
  }
  return [...ids]
    .map((id) => ({ id, name: facilityDisplayName(id) }))
    .sort((a, b) => a.name.localeCompare(b.name))
}
