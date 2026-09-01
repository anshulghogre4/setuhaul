import { GateKiosk } from './gate-kiosk'

/**
 * The mountable `/gate` route (E5.4, issue #39).
 *
 * Exists as its own file so `App.tsx` needs **one import and one self-contained JSX element** --
 * three surfaces were being wired into that file concurrently when this was built, and a route that
 * needs its own identity constant, its own fixture import and its own wrapper decision is three
 * more chances for a merge to silently do the wrong thing.
 *
 * ## Two things the coordinator must not "fix"
 *
 * **1. This is deliberately NOT wrapped in `ShellRoute`.** Every other desk surface is; this one
 * must not be. `stitch-prompts.md` and the rendered `mockup.html` both state there is no icon rail,
 * no top bar, no status bar and no facility switcher on this surface, and `GateKiosk` sets its own
 * `data-density="spacious"` root. Wrapping it would put a rail and a facility switcher on a mounted
 * gate booth and would override the density with the viewer's role default. `/driver` is already
 * outside the shell for the analogous reason.
 *
 * **2. It takes no `Identity` prop.** There is no facility switcher here to drive: the device's
 * facility is fixed to its physical installation (`screens.md` section 1), not chosen by the person
 * holding it, so issue #52's missing multi-role `grants[]` contract does not gate this surface at
 * all -- unlike ops and planner, there is no cross-facility scope union to resolve.
 *
 * ## Which identity model this surface assumes (issue #79)
 *
 * **The facility-role model, not `GATE_OFFICER`** -- stated explicitly because the two resolutions
 * of #79 imply different wiring, and this surface has deliberately picked one.
 *
 * `backend/app/core/execution_context.py`'s `RoleName` enum has no `GATE_OFFICER` member, while
 * `frontend/src/core/auth/identity.ts` does; #79 is open on which side is the drift. This feature
 * folder is unaffected either way: verified by grep, **nothing under `features/gate/**` imports
 * `core/auth/identity`, references `RoleName`, or mentions `GATE_OFFICER`.** The surface renders no
 * rail, no switcher and no role-derived chrome, so there is no role to resolve on the client at
 * all -- authorisation happens entirely server-side at `gate.py`'s own role gate
 * (`WAREHOUSE_PLANNER` / `FACILITY_MANAGER` / `ADMIN`, the owner-confirmed 2026-08-24 mapping), and
 * every write here already goes through it.
 *
 * So if #79 resolves in the backend's favour, nothing in this folder changes. If it resolves the
 * other way and a real `GATE_OFFICER` role is added, still nothing in this folder changes -- only
 * `gate.py`'s role tuple does. That independence is a property of the surface having no shell, not
 * a coincidence.
 */
export function GateRoute() {
  return <GateKiosk facilityId={GATE_DEVICE_FACILITY_ID} />
}

/**
 * DEVICE SEAM -- **not** the identity seam, and re-marked as such on 2026-09-01 when the identity
 * half of TODO(#52) was closed. This value is a property of the *installation*, not of whoever is
 * signed in, so it is deliberately NOT replaced by `identity.activeFacilityId`: a planner covering
 * a shift at another site must still see the booth's own facility, per `screens.md` section 1's
 * "the device's facility, not the user's". What it still needs is a device-provisioning mechanism
 * (a kiosk registration, an install-time config), which is a separate piece of work.
 *
 * The facility a kiosk is physically installed at. Server-derived in the real system: `gate.py`'s
 * writes already resolve scope from the caller's verified identity
 * (`repositories/scope.py::resolve_facility_scope`), so this value is **display only** -- it feeds
 * the shift bar's "Facility: Jaipur (fixed)" line and nothing else. It is never sent as an argument
 * to any tool, which is M15's rule and is why a wrong value here cannot widen anyone's scope.
 *
 * Deliberately a local constant rather than an import from `features/gallery/fixtures`, which is
 * now a gallery-only module.
 *
 * `FAC-JAI-01` matches the facility every artboard in `mockup.html` renders.
 */
const GATE_DEVICE_FACILITY_ID = 'FAC-JAI-01'
