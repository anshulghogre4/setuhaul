/**
 * Gate/yard kiosk feature flags.
 *
 * Named for the DEPENDENCY, not the feature, per E5.1-E5.3's precedent
 * (`features/driver/lib/flags.ts`, `features/ops/lib/flags.ts`, `features/planner/lib/flags.ts`).
 *
 * **One flag, not several.** Unlike planner's seven, `implementation-spec.md` section 3's screen
 * table finds exactly one gap and states plainly that "this surface unblocks in one motion": the
 * moment a search tool exists, screens 3-22 all become buildable at once. There is no per-tool flag
 * because the five write tools are all shipped and correct -- re-verified line-by-line this pass
 * against `gate_yard_service.py`, not taken from the spec -- so there is nothing about any
 * individual write to gate.
 *
 * ## Why this flag exists at all: what was true when the surface was built
 *
 * `gate.py` had **zero `GET` routes** (confirmed by grepping `@router.get` across
 * `app/api/v1/routers/`: gate was the only router with none). The surface's entire logic is
 * `screens.md` section 3's state -> action table, whose input is the truck's current state, and no
 * endpoint anywhere returned it to an operator-role caller:
 *
 *   - `driver_reads.get_gate_and_queue_status` returned the right shape but opened with
 *     `get_driver_operational_context`, which raises `DRIVER_UNMAPPED` (403) unless `ctx.is_driver`
 *     -- and it was wired to no router and no agent tool, so unreachable at any URL regardless.
 *   - `GET /operations/queue-status` sounds like it would (and is reachable -- `WAREHOUSE_PLANNER`
 *     and `FACILITY_MANAGER` are both in `OPS_PORTAL_ROLES`) but returns two facility-wide
 *     integers, `pending_appointments` and `open_escalations`. No per-truck row, no queue state.
 *     Checked because `implementation-spec.md` section 2 never mentions it; it does not close the gap.
 *   - `GET /api/v1/search` never matched `vehicles.registration_number`, so the plate half of
 *     U109's "shipment ID **or** plate number" had no matching column at all.
 *
 * Without that read the kiosk could not know which of the five writes was the one valid action, and
 * `screens.md` section 3's table has no default row. Rendering a button anyway would have meant
 * guessing -- and on this surface a wrong guess records a real gate event against a real truck.
 *
 * ## Why no write was exposed "blind", even though one of them safely could have been
 *
 * `record_gate_in` is genuinely callable from a shipment id alone: self-describing
 * (`GATE_IN_RECORDED` / `ALREADY_CHECKED_IN` / `NO_ACTIVE_APPOINTMENT`), the one tool the catalog
 * gives a real `Idempotency-Key` replay to, and with no destructive precondition to skip. An earlier
 * interrupted attempt on this issue shipped exactly that as a live control.
 *
 * **Reversed this pass, deliberately.** `screens.md` section 3's Rules are explicit that "the current
 * state renders above the button, not just implied by the button's own label -- an officer glancing
 * at the screen mid-task needs to confirm 'yes, this is where this truck actually is' before pressing
 * anything." With no state to render, a blind Gate-in button inverts the one safety property this
 * surface is built around, on the surface where a mis-tap writes an unreversible fact about the wrong
 * truck (`components.md` section 4 has no confirmation step *because* the identity card is the
 * confirmation). The other four are worse: `record_dock_in` needs a `dock_id` only the appointment
 * supplies, and `record_gate_out` has **no server-side guard that the unload ever finished**
 * (`gate_yard_service.py:805-834` checks only "never gated in" and "already gated out"), so a blind
 * call there can record a genuinely premature gate-out.
 *
 * ## Current state: the endpoint landed while this surface was being built, and the flag is now ON
 *
 * `GET /api/v1/gate/trucks` (`gate.py::search_trucks` -> `services/gate_yard_reads.py`) shipped
 * concurrently with this build. It was found here by reading `git status` and then the router
 * itself, before the flip -- not taken on trust -- and this client is aligned to the real contract
 * rather than to the shape an earlier draft had guessed:
 *
 *   - `lib/api.ts::searchTrucks` calls that exact route with `?query=`. The earlier draft targeted
 *     `/api/v1/gate/search?q=` with a `{ matches }` body and was wrong on the path, the parameter
 *     name **and** the response shape.
 *   - `lib/types.ts` mirrors `GateTruckMatch` / `GateTruckSearchResult` field-for-field, flat
 *     appointment fields included.
 *   - `lib/queue-states.ts` consumes the server's own `next_action` and does **not** re-derive it.
 *     `derive_next_action`'s docstring requires this, and the earlier client-side derivation had a
 *     real defect the server version does not: it would have offered "Call to dock" to a truck in a
 *     `WAITING_*` state with a null `gate_in_ts`, which every write except `record_gate_in` refuses
 *     outright with `NOT_CHECKED_IN`.
 *   - `SearchPanel` branches on the server's `code`, not on array length: `NO_MATCH` is a 200 with
 *     an empty list, not a 404, and is handled as Flow 1.3 (stay on the screen, keep the value,
 *     refocus the field) rather than as a transport failure.
 *
 * **What is verified, and what is not.** Verified: the client compiles against the shipped Pydantic
 * models, every screen behind this flag renders correctly in headless Chromium, and the backend's
 * own 69 gate unit tests pass. **Not verified by this build: a live round trip.** No authenticated,
 * facility-scoped session was available here, so `searchTrucks` has never actually reached the
 * route. The degradation if something is wrong is safe and honest rather than silent -- a throw
 * lands in `SearchPanel`'s `lookup-failed` state ("Couldn't look that truck up"), never in a wrong
 * write -- but it is a real residual gap and is named in the build report rather than glossed.
 *
 * ## Re-confirmed 2026-08-29 (M5 flag-flip audit) -- this flip is correct and was not re-done
 *
 * Checked, rather than assumed from E5.4's own report:
 *   - `GET /api/v1/gate/trucks` is registered at `routers/gate.py:90` with `query` as its one
 *     parameter and **no `facility_id`** -- scope comes from the verified token via
 *     `resolve_facility_scope(ctx, None)`, so M15/NFR-019 holds and the search cannot surface a
 *     truck the caller could not then act on. (`implementation-spec.md` section 6 Fork E's proposed
 *     `search_gate_yard_truck(query, facility_id)` signature was deliberately **not** built; that
 *     design doc still needs amending before anyone builds to it.)
 *   - `lib/types.ts`'s `GateTruckMatch` / `GateTruckSearchResult` match the shipped Pydantic models
 *     field-for-field, flat appointment fields included, and `lib/api.ts::searchTrucks` calls the
 *     exact path with the exact `?query=` parameter name.
 *   - The route carries `GateCtx` = `require_roles(*GATE_KIOSK_ROLES)`, the same set the five write
 *     tools use -- so read reach and write reach agree by construction. **Issue #79 landed during
 *     this audit** (a concurrent agent added `RoleName.GATE_OFFICER` plus
 *     `supabase/migrations/20260829180000_gate_officer_role.sql`), so `GATE_KIOSK_ROLES` is now
 *     `(GATE_OFFICER, WAREHOUSE_PLANNER, FACILITY_MANAGER, ADMIN)` -- **widened, not narrowed**, so
 *     every session that could reach this kiosk before still can. That migration's applied state
 *     was not verified here; it does not matter for this flag, because the three pre-existing roles
 *     need no new database row.
 *   - `MIN_QUERY_LENGTH = 2` mirrored here still matches `gate_yard_reads.py:66`.
 *
 * **Still not verified: a live authenticated round trip.** Unchanged from E5.4 -- no scoped session
 * was available in this pass either.
 */
export const gateSearchEnabled = true

/**
 * Issue #68 (GY-G2) -- officer attribution. **Closed 2026-08-31, and still deliberately NOT a flag.**
 *
 * It was recorded here as an absence rather than an off switch, because there was no hidden
 * capability to switch on: none of the five write tools had an argument the name could be sent in.
 * That is now fixed -- all five `gate.py` body models carry `officer_name` and `_audit` records it
 * on every event -- and it stays flagless for the mirror-image reason. Sending a label the server
 * already treats as optional has no failure mode worth gating: an older backend ignores the extra
 * field or rejects it outright at `extra="forbid"`, and the kiosk is deployed against one backend,
 * not a fleet of versions. There is no half-on state to model.
 *
 * The user-visible behaviour is unchanged either way -- the officer sees the same shift bar. What
 * changed is only what the audit trail can answer afterwards. See `lib/session.ts` and
 * `gate_yard_service.OFFICER_ATTRIBUTION_KEY`.
 */
