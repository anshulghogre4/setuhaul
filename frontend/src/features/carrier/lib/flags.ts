/**
 * Feature flags for E5.5, named for the backend gap each one waits on.
 *
 * Same convention E5.2 and E5.3 established: default off, issue number in the comment, and the
 * flag gates a *designed* screen rather than hiding a half-built one.
 */

/**
 * **SPLIT 2026-08-31. This flag was two dependencies wearing one name, and only one of them was
 * ever going to be met.** The history below is kept because it is what the split was decided
 * against; read `carrierHeldEnabled` at the bottom for what actually ships.
 *
 * `HELD` and `SHOWN` were flagged together because on 2026-08-29 both 400ed identically. They are
 * not the same problem and issue #87 separated them at the server:
 *
 *  - **`HELD` is answerable and now answered.** #85 taught both fleet reads to derive it from
 *    `dock_occupancy` via a scoped LATERAL, and #87 moved the filter onto that derived
 *    `promise_state`. It is live.
 *  - **`SHOWN` is not answerable in any flag state, by argued decision rather than by omission.**
 *    §0.8/§4 define it as what `find_feasible_slots` returned to one caller, and that read reserves
 *    nothing and writes no row anywhere in the product. `carrier_reads._SHOWN_UNSUPPORTED_REASON`
 *    states it in the refusal itself. The tempting mapping -- "no appointment and no hold" -- would
 *    return every shipment that was never offered anything, which is the opposite of what a carrier
 *    filtering on `SHOWN` is asking for.
 *
 * So `SHOWN` is **removed from this surface entirely** rather than left behind a flag: a flag
 * implies a pending engineering task, and what `SHOWN` actually needs is a **design decision** about
 * whether a presentation-only state belongs in a carrier's status vocabulary at all. Until that
 * decision exists, `promise.ts`'s null-promise-state row ("No appointment yet.") remains the honest
 * stand-in, and the filter popover ships five options rather than six.
 *
 * **Owner decision required (not engineering):** does `SHOWN` belong on the carrier portal? If yes,
 * it needs a persisted representation somewhere -- which is a `SOLUTION_DESIGN.md` §4 change, not a
 * query change. If no, `05-carrier-portal/stitch-prompts.md` §3 state (b)'s six-option list and
 * `mockup.html` state 4a's `SHOWN` chip both want correcting to five.
 *
 * ---
 *
 * ## Original comment, retained (issue #53 — `HELD` had no backend, and neither did `SHOWN`)
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
 *
 * ## Re-audited 2026-08-29 (M5 flag-flip audit) — this file's analysis held up; nothing changed
 *
 * Unlike the driver, ops, planner and admin flag files, this one needed no correction: it was
 * written **while** #53's migration was landing and already predicted exactly what would happen.
 * Re-verified against current source rather than re-trusted:
 *   - `carrier_reads._SCHEMA_UNSUPPORTED_FILTERS` is still `frozenset({"SHOWN", "HELD"})` and
 *     still raises 400 `FILTER_UNSUPPORTED` (line 127). Requirement 2 above is unmet.
 *   - `repositories/carrier.py` still selects `appt.appointment_status AS promise_state` on both
 *     reads (lines 225, 283) — no `dock_occupancy` join. Requirement 1 above is unmet.
 *   - The three-condition list was subsequently filed as **issue #85**, which is OPEN with **no
 *     implementation** as of 2026-08-29.
 *   - The migration itself is **not applied to any database**, and the server-side
 *     `TWO_PHASE_HOLD_ENABLED` defaults off.
 *
 * **Exit criterion (superseded by the split above):** issue #85 closed, the migration applied, and
 * `SHOWN` given a representation. The first two are met; the third is a design question, which is
 * exactly why it no longer gates the first two.
 */

/**
 * Gates the `HELD` chip variant and the `Held` status-filter option. **ON since 2026-08-31.**
 *
 * Every gate this flag's predecessor named for `HELD` is met, and each was re-verified against live
 * source rather than taken from an issue's text:
 *
 *  - `repositories/carrier.py::_PROMISE_STATE_SQL` derives `promise_state` from an active
 *    appointment first and a live hold second, with the **identical precedence** to
 *    `services/driver_reads.resolve_promise_state` -- a carrier and the driver on the same shipment
 *    cannot be shown different promises. It also projects `hold_id` and `hold_expires_at`, which is
 *    what the chip's countdown needs and what nothing had a field for before #85.
 *  - The hold is joined **LATERAL inside the already-carrier-scoped statement**, not fetched by a
 *    query of its own, so a hold can never become a way to read outside a carrier's fleet
 *    (guarded by `test_every_carrier_query_is_carrier_scoped`).
 *  - The LATERAL carries `expires_at > now()` -- SQL `now()`, the database's own clock, the same
 *    authority the sweeper works against -- so a lapsed-but-unswept hold does not render as "Held"
 *    to a carrier. §0.8's mandatory lazy expiry check.
 *  - `carrier_reads._validate_status_filter` answers `HELD` when the server flag is on and refuses
 *    it with a *stated reason* when it is off (`_HOLD_FILTER_DISABLED_REASON`), rather than
 *    returning an empty list that reads as "you have none".
 *
 * **What this flag does NOT cover:** `SHOWN`, which is removed rather than gated -- see the block
 * above for why that is a design decision and not an engineering one.
 *
 * **To revert:** set this to `false`. The `Held` filter option disappears and a HELD row falls back
 * to the null-promise-state rendering. The server keeps deriving the state either way, so nothing
 * is written differently; only what this surface displays changes.
 */
export const carrierHeldEnabled = true
