/**
 * Facility id -> display name, for the shift bar's "Facility: Jaipur (fixed)" line
 * (`screens.md` section 1, `components.md` section 1).
 *
 * Same minimal table `features/ops/lib/facility-names.ts` carries, duplicated locally rather
 * than imported cross-feature (each surface owns its own small lib copy, matching this
 * product's per-surface separation). Only **two** of the seeded facilities have a documented
 * name anywhere in scope (`features/gallery/fixtures.ts`'s own comment) -- an unknown id
 * renders as itself, never a guessed name.
 */
const KNOWN_FACILITY_NAMES: Record<string, string> = {
  'FAC-JAI-01': 'Jaipur',
  'FAC-GGN-01': 'Gurugram',
}

export function facilityDisplayName(facilityId: string): string {
  return KNOWN_FACILITY_NAMES[facilityId] ?? facilityId
}
