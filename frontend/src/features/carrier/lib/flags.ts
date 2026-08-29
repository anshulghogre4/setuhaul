/**
 * Feature flags for E5.5, named for the backend gap each one waits on.
 *
 * Same convention E5.2 and E5.3 established: default off, issue number in the comment, and the
 * flag gates a *designed* screen rather than hiding a half-built one.
 */

/**
 * **Issue #53 — the `HELD` promise-state has no backend, and neither does `SHOWN`.**
 *
 * Re-verified against live source during this build rather than taken from the issue's text:
 *
 *  - `appointments_appointment_status_check` (baseline migration, line 173) admits
 *    `PENDING_CONFIRMATION / CONFIRMED / IN_PROGRESS / COMPLETED / CANCELLED / NO_SHOW /
 *    REJECTED` (+ `EXPIRED`, added later). No `SHOWN`, no `HELD`.
 *  - `carrier_reads._SCHEMA_UNSUPPORTED_FILTERS = {'SHOWN', 'HELD'}` — the endpoint answers
 *    **400 `FILTER_UNSUPPORTED`** for either value, deliberately, because an empty list would
 *    tell a carrier "you have no held shipments", which is not what the system knows.
 *  - `scheduling/expiry.py:94-101` records the same gap for D2's HELD TTL sweep.
 *
 * What this flag gates, and nothing else:
 *  - the `Shown` and `Held` options in the status-filter popover
 *    (`stitch-prompts.md` §3 state (b) lists six options; five ship, `Shown`/`Held` are the
 *    two that would 400)
 *  - the `SHOWN` and `HELD` chip variants in the shipments table and on shipment detail
 *    (`mockup.html` states 12a / 12b)
 *
 * `05-carrier-portal/implementation-spec.md` §6 Fork A option (a), as recommended: gate them
 * behind a named flag rather than shipping a control that errors, or blocking the surface.
 *
 * ## Flipping this to `true` will NOT be sufficient even after #53's schema lands
 *
 * Checked against the migration that appeared in the working tree during this very build
 * (`supabase/migrations/20260829134929_d2_held_state_dock_occupancy.sql`, another agent's
 * concurrent #53 work) rather than assumed from the issue's text. That migration adds
 * `dock_occupancy.state` and `dock_occupancy.expires_at` — and **deliberately does not add
 * `'HELD'` to `appointments_appointment_status_check`**, stating the reason in its own header:
 * a hold is a `dock_occupancy` row and nothing else, so adding the value to `appointments` would
 * "create a value no code path can produce".
 *
 * `promise_state` on both carrier reads is `appointments.appointment_status`
 * (`repositories/carrier.py`). So after #53 lands, this surface **still** cannot receive `SHOWN`
 * or `HELD` — the value lives in a different table this endpoint does not join. Three things have
 * to be true before the flag means anything here:
 *
 *   1. `list_fleet_shipments` / `get_fleet_shipment` join `dock_occupancy` and derive a HELD
 *      promise state (with its `expires_at`, which is also what the `HELD` chip's countdown and
 *      its `Held for the driver until …` line need — neither has a field today);
 *   2. `carrier_reads._SCHEMA_UNSUPPORTED_FILTERS` is emptied, or the two filter options 400
 *      exactly as they do now;
 *   3. `SHOWN` gets a representation at all — nothing in #53 or its migration gives it one, and
 *      the null-promise-state row (`promise.ts`) is the honest stand-in until it does.
 */
export const carrierShownHeldEnabled = false
