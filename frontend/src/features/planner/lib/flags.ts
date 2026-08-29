/**
 * Planner-surface feature flags.
 *
 * Named for the DEPENDENCY, not the feature, per E5.1/E5.2's precedent
 * (`features/driver/lib/flags.ts`, `features/ops/lib/flags.ts`) -- so it is obvious what removes
 * a flag rather than obvious what it hides. Names copied verbatim from
 * `03-planner-dock-board/implementation-spec.md` section 7's own naming scheme. All seven default
 * OFF, each with the issue number(s) that gate it named in its own comment.
 *
 * **Why every one of these is off, in one sentence**: `get_planner_queue` (P-G1, issue #60) does
 * not exist, and every write action on this surface -- confirm, counter-offer, hold, bulk confirm,
 * even reject's live entry point -- starts from a queue row this backend cannot produce. Only the
 * block-dock group (states 16-18, `block_dock`/`end_dock_block`/`get_dock_block_impact`) has a
 * complete backend and ships unconditionally, with no flag of its own.
 */

/**
 * Gates the live Queue tab (states 1, 6, 8, 9, 10, 11) and its "N new . press R" live-arrivals
 * affordance.
 *
 * **Default OFF, and it must stay off until issues #60 and #59 both land.**
 *
 * Why (P-G1, issue #60): `get_planner_queue` does not exist in section 7.5.1's shape. The nearest
 * read, `operations_reads.get_appointment_schedule`, joins `appointments` to `appointment_slots`
 * -- not `dock_occupancy`, which D1 declares the authority -- and returns none of section 7.3's
 * seven required fields (condensed receipt, displacement check, ETA confidence,
 * `latest_acceptable_ts`, TTL remaining, `snapshot_hash`), nor the composite-urgency ordering.
 *
 * Why also #59 (P-G10, the same live-update-transport gap E5.2 filed as its own G6): the only
 * streaming endpoint anywhere in the product is the driver `/chat` SSE turn stream. Without it,
 * "3 new . press R to re-sort" and the assertive same-row-race announcement
 * (`edge-cases.md` section 1) have no live signal to render.
 *
 * States 27 (queue skeleton), 29 (load failed / out of scope / maintenance) and 30 (below 1024px)
 * are NOT behind this flag -- they are structural/negative states independent of what
 * `get_planner_queue` would return, and ship unconditionally (`implementation-spec.md`'s own 🟢
 * marks for these three).
 *
 * **Exit criterion:** issues #60 and #59 both closed, then flip to `true`.
 */
export const plannerQueueLiveEnabled = false

/**
 * Gates Confirm and its refusal taxonomy (states 1, 6, 8) once a queue row exists to confirm.
 *
 * **Default OFF, and it must stay off until issues #61 and #62 both land.**
 *
 * Why (P-G2, issue #61): `snapshot_hash` does not exist anywhere in `backend/app/` -- zero
 * occurrences, grepped. It is the mechanism behind `SNAPSHOT_STALE`, and without it there is no
 * optimistic-concurrency story for the confirm path at all.
 *
 * Why also #62 (P-G3): `confirm_request`'s refusal taxonomy is one-third built --
 * `ALREADY_ACTIONED` is real (`allocation.py:263`), but `SNAPSHOT_STALE` and
 * `DISPLACEMENT_DETECTED` are absent. Separately, the shipped `ConfirmAppointmentCommand`
 * requires `warehouse_confirmation_ref` (`allocation.py:110`), a mandatory field with no UI
 * anywhere in the 30 planner artboards and no design-doc source.
 *
 * **Exit criterion:** issues #61 and #62 both closed, then flip to `true`.
 */
export const plannerConfirmEnabled = false

/**
 * Gates the counter-offer board-picker (U103, states 3, 24, 25) -- the one affordance that leaves
 * the Queue tab and the reason the Board tab has an interactive mode at all.
 *
 * **Default OFF, and it must stay off until issue #63 lands.**
 *
 * Why (P-G4): `counter_offer` does not exist anywhere in `backend/app/` -- zero occurrences.
 *
 * **Exit criterion:** issue #63 closed, then flip to `true`.
 */
export const plannerCounterOfferEnabled = false

/**
 * Gates Hold for information (states 7, 14, 15) -- the D9 clock pause.
 *
 * **Default OFF, and it must stay off until issue #64 lands, which needs a migration, not just a
 * tool.**
 *
 * Why (P-G5): `expiry.py:77-81` says so in its own comment -- `public.appointments` has no
 * deadline/expires_at column, so there is nowhere to record the extension. Faking it by touching
 * `booked_at` would corrupt the request's own history, which is why this was flagged rather than
 * worked around.
 *
 * **Exit criterion:** issue #64 closed (the migration lands), then flip to `true`.
 */
export const plannerHoldEnabled = false

/**
 * Gates Bulk confirm (states 9, 10) -- "Select all eligible (N)" and the server-side re-check of
 * the five safe-batch predicates at press time.
 *
 * **Default OFF, and it must stay off until issue #65 lands. Do not ship a client-side
 * approximation as a stopgap when it does** -- the server-side re-check at press time is the
 * whole point (`implementation-spec.md` section 7, item 9).
 *
 * Why (P-G6): `bulk_confirm` does not exist anywhere in `backend/app/` -- zero occurrences.
 *
 * **Exit criterion:** issue #65 closed, then flip to `true`.
 */
export const plannerBulkConfirmEnabled = false

/**
 * Gates the Board tab's "at rest" occupancy view (states 2, 22) and the counter-offer picker's
 * eligible/ineligible dock rendering, which both depend on `dock_occupancy.state`.
 *
 * **Default OFF, and it must stay off until issue #53 lands, which needs a migration.**
 *
 * Why (P-G8): `dock_occupancy` has no `state` column in the shipped schema
 * (`20260823060000_d1_correctness_bedrock.sql:175-182`, independently confirmed in
 * `expiry.py:88-95`) -- `components.md` section 3's nine-value state-to-chip mapping table, the
 * single most-cited table in this surface's design, is grounded in a column that does not exist.
 * The same gap also blocks D2's HELD promise-state, tracked as issue #53 -- reused here rather
 * than filing a duplicate, since fixing one migration unblocks both.
 *
 * States 23 (board load failed) and 28 (board loading skeleton) are NOT behind this flag -- they
 * are structural/negative states independent of `dock_occupancy.state`, and ship unconditionally.
 * The block-dock group (states 16-18, `[ Block a dock ]`) is also NOT behind this flag -- it reads
 * `dock_status_events` and `dock_occupancy.window`/`appointment_id`, never `.state`, so it has a
 * complete backend regardless of this gap.
 *
 * **Exit criterion:** issue #53 closed (the migration lands), then flip to `true`.
 */
export const dockBoardEnabled = false

/**
 * Gates the sequencer proposal diff overlay (states 19, 20, 21) and turns
 * "[ Review proposal (N) ]" from permanently Inactive into a real entry point.
 *
 * **Default OFF, and it must stay off until issue #49 lands** (the epic that also gates E5.2's
 * prompt 14 -- the two surfaces are the two halves of U93's handoff, and neither can be built
 * before the other).
 *
 * Why (P-G9): section 7.5.3 (the Sequencer) is entirely unbuilt -- `propose_facility_schedule`,
 * `apply_schedule_proposal` and `get_scheduling_run` are all absent.
 *
 * **Exit criterion:** issue #49 closed, then flip to `true`.
 */
export const sequencerProposalEnabled = false
