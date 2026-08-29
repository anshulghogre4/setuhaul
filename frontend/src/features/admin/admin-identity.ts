import type { Identity } from '@/core/auth/identity'

/**
 * FIXTURE SEAM — TODO(#52). The admin identity `/admin` renders under.
 *
 * Defined **here rather than in `features/gallery/fixtures.ts`** for one concrete reason: two other
 * surface builds (E5.4 gate, E5.5 carrier) are writing in this working tree at the same time as
 * this one, and `fixtures.ts` is shared. Adding a constant to it would be a write into a file a
 * concurrent agent may be reading. When #52 lands and the shell fetches a real identity, this
 * constant is deleted along with `OPS_IDENTITY` and `PLANNER_MULTI_ROLE`'s use in `App.tsx` — it
 * is the same seam, just parked in the folder that owns it.
 *
 * Why these particular values:
 *  - `activeRole: 'ADMIN'` so `railDestinationFor` resolves to `{ surface: 'admin', path:
 *    '/admin', label: 'Admin' }` and `densityFor('admin')` gives `comfortable`
 *    (`core/auth/identity.ts:99`, `:120`) — the density `spacing-and-layout.md` assigns this
 *    surface, and the one `screens.md` §1 assumes (44px rows, 40px controls, 24px padding).
 *  - **One rail destination.** `06-admin-console/implementation-spec.md` §0.2 records the
 *    cross-surface fix settled 2026-08-29: the rail's second "Profile" item duplicated the top-bar
 *    account control and was dropped from ops's and planner's mockups and from all 20 admin
 *    frames. `railDestinationFor` already returns exactly one destination per role, so the built
 *    shell inherits the corrected behaviour with no work — the duplication is not reintroduced.
 *  - `facilities` is empty and `activeFacilityId` is `null`. `screens.md` §1: "no facility
 *    switcher, since admin actions span facilities by nature (a user's scope, a rule's facility,
 *    are set per-action, not by a global view filter)". Note this differs from
 *    `hasFacilityScope('ADMIN')`, which returns `true` and would render a switcher — with an
 *    empty `facilities` array there is nothing for it to switch between, which is the honest
 *    encoding. Flagged for the owner rather than changed: `identity.ts` is shared infrastructure
 *    and `hasFacilityScope`'s admin branch is arguably a real mismatch with this surface's design.
 *  - `canSelectAllFacilities: false` — that flag exists for the cross-facility ops roles whose
 *    §7.5.5 tools take an optional `facility_id`; admin's tools take a required one per action.
 */
export const ADMIN_IDENTITY: Identity = {
  userId: 'USR-DEMO-ADMIN',
  // Copied from the mockup's own top-bar account control ("Account — Anshul B.", avatar "AB"),
  // which is the one identity string that appears in all 20 frames -- not invented here.
  fullName: 'Anshul B.',
  initials: 'AB',
  email: 'anshul.b@setuhaul.example',
  activeRole: 'ADMIN',
  activeRoleLabel: 'Administrator',
  grants: [{ role: 'ADMIN', roleLabel: 'Administrator', scopeLabel: 'All facilities' }],
  facilities: [],
  activeFacilityId: null,
  canSelectAllFacilities: false,
  carrierId: null,
}
