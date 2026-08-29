/**
 * Facility id -> display name, for the queue row's plain-text facility line (U91,
 * `components.md` section 6 of this folder: "Jaipur · Reefer dock", no accent colour).
 *
 * Only **two** of the seeded facilities have a name documented anywhere in scope --
 * `frontend/src/features/gallery/fixtures.ts`'s own comment: "Only TWO facility names exist in
 * any document in scope (Jaipur DC, Gurugram Cross-Dock) against section 2's six facilities...
 * the names are not stated anywhere and are deliberately not invented here." Same rule applies
 * here: an unknown id renders as itself, never a guessed name.
 */
const KNOWN_FACILITY_NAMES: Record<string, string> = {
  'FAC-JAI-01': 'Jaipur',
  'FAC-GGN-01': 'Gurugram',
}

export function facilityDisplayName(facilityId: string): string {
  return KNOWN_FACILITY_NAMES[facilityId] ?? facilityId
}
