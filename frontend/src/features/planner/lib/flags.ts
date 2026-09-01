/**
 * Planner-surface feature flags.
 *
 * Named for the DEPENDENCY, not the feature, per E5.1/E5.2's precedent
 * (`features/driver/lib/flags.ts`, `features/ops/lib/flags.ts`) -- so it is obvious what removes
 * a flag rather than obvious what it hides. Names copied verbatim from
 * `03-planner-dock-board/implementation-spec.md` section 7's own naming scheme. All seven default
 * OFF, each with the issue number(s) that gate it named in its own comment.
 *
 * ## Re-audited 2026-08-29 — the original reason for four of these has EXPIRED, the flags have not
 *
 * When this file was written, `get_planner_queue`, `snapshot_hash`, `counter_offer` and
 * `bulk_confirm` genuinely did not exist. **They do now** (#60/#61/#62/#63/#65/#66 all landed
 * 2026-08-29, verified by reading `app/api/v1/routers/planner.py::@router.get("/queue")`,
 * `app/scheduling/snapshot.py` and `planner_service.py` directly, not by trusting an issue
 * comment). Every one of those issues is still OPEN, because this repo closes on owner review
 * rather than on inference -- so OPEN did not mean unbuilt, and re-reading the code was the only
 * way to tell.
 *
 * **They all stay OFF anyway, for a reason that has moved from the backend to this folder.** The
 * planner surface has no queue UI at all: `lib/api.ts` wraps three endpoints (`dock-snapshot`,
 * `block-impact`, `block`/`end`) and none of the six new ones; there is no queue row, no confirm
 * control, no counter-offer picker and no bulk-select anywhere in `components/`. Flipping
 * `plannerQueueLiveEnabled` today does not reveal a queue -- it swaps one honest "not yet
 * available" panel for `QueueEmptyCaughtUp`, i.e. it would tell a planner they are **caught up**
 * while real pending rows sit unactioned in a database this surface never queried. That is a
 * strictly worse failure than the stub, and it is the specific trap this re-audit was run to
 * avoid.
 *
 * ## RESOLVED 2026-08-29 (later the same day) — the queue UI was built, and four flags flipped
 *
 * The audit above was acted on rather than filed. `lib/api.ts` now wraps all five queue
 * endpoints, `components/queue-tab.tsx` + `queue-row.tsx` render section 7.3's nine-column row
 * against real data, and confirm / reject / counter-offer / bulk-confirm each have a real call
 * site. So `plannerQueueLiveEnabled`, `plannerConfirmEnabled`, `plannerCounterOfferEnabled` and
 * `plannerBulkConfirmEnabled` are **on**, and the trap the audit named is gone: the `true` branch
 * of the Queue tab now queries the server before it can render an empty state at all.
 *
 * **`plannerQueueLiveEnabled` was split**, exactly as the audit recommended. It conflated two
 * dependencies with very different readiness: the queue read (#60, shipped) and the live-arrivals
 * transport (#59, not started). The second is now `plannerLiveArrivalsEnabled`, still off, so a
 * working queue no longer waits on an architecture decision about multi-viewer streaming.
 *
 * `plannerHoldEnabled`, `dockBoardEnabled` and `sequencerProposalEnabled` stay off, and each
 * comment below states which of its gates is still shut. Read those, not this summary, before
 * flipping anything further.
 *
 * The block-dock group (states 16-18, `block_dock`/`end_dock_block`/`get_dock_block_impact`)
 * still ships unconditionally with no flag of its own.
 *
 * ## Reject has no flag, and #66 changed its wire contract -- read this before wiring it
 *
 * `reject_request` was never flagged (its live entry point is a queue row, so it was gated by
 * `plannerQueueLiveEnabled` transitively). #66 landed 2026-08-29 and **renamed the wire field
 * `rejection_reason` -> `reason_code`** and constrained it to a frozen 5-value enum copied verbatim
 * from `escalation_service.RESOLVE_REASON_CODES`, with a 422 `INVALID_REASON_CODE` naming the
 * supported set. `components/reject-dialog.tsx` is built against the enum in `lib/reasons.ts`,
 * which is copied from `allocation.REJECTION_REASON_CODES` rather than from the artboards -- a
 * form built from the older prose would 422 on every submit, and the 422 is still handled rather
 * than assumed unreachable. Reject remains unflagged: it ships with the queue.
 */

/**
 * Gates the live Queue tab (states 1, 6, 8, 26, 27, 29) -- the read itself, and nothing else.
 *
 * **ON since 2026-08-29.** P-G1 / issue #60 is resolved in the backend *and* consumed here:
 * `GET /api/v1/planner/queue` (`routers/planner.py:56`) ships section 7.3's seven fields, a
 * composite-urgency score with every term returned per row, and a real `snapshot_hash` tagged
 * `sha256/planner-queue-v1`. It LEFT-joins `dock_occupancy` rather than INNER-joining it, which
 * is why it does **not** depend on #53 and can ship while the board cannot.
 *
 * **What was verified about the read path before flipping**, not merely that an endpoint exists:
 *
 *  - The route is reachable by this surface's identity -- `require_roles(WAREHOUSE_PLANNER,
 *    ADMIN)` (`planner.py:36`), and the `/planner` route mounts under the `WAREHOUSE_PLANNER`
 *    fixture.
 *  - Scope resolves without a client-supplied id: `resolve_facility_scope(..., require_facility=
 *    True)` returns the operator's own facility when none is passed and 403s on a mismatch
 *    (`repositories/scope.py:45-58`), so `facility_id` is a narrowing request, never an assertion.
 *  - Every field the row renders exists on `PlannerQueueRow` (`planner_service.py:239-278`), which
 *    is `extra="forbid"` -- so `lib/types.ts` is the complete shape, not a hopeful superset.
 *  - `ttl.deadline_ts` + the payload's `ttl_minutes` are what the countdown bands are a fraction
 *    of, and `as_of` feeds the shared clock's server-time offset. Both are consumed.
 *
 * `snapshot.enforced` on the payload still reports `false`. **That field is now stale**, not a
 * limit: it predates #62, and `_snapshot_guard` genuinely enforces the hash on confirm /
 * counter-offer / bulk-confirm. The client therefore does not branch on it -- it always sends the
 * hash the row gave it. Worth correcting server-side so the payload stops understating itself.
 *
 * States 27 (skeleton), 29 (load failed / out of scope / maintenance) and 30 (below 1024px) are
 * NOT behind this flag -- structural/negative states, independent of what the read returns.
 */
export const plannerQueueLiveEnabled = true

/**
 * Gates the "N new · press S to re-sort" pill and U19's arrivals-accumulate-behind-a-frozen-sort
 * behaviour (`stitch-prompts.md` section 4, State 9's pin line).
 *
 * **ON since 2026-08-31 (issue #59).** The owner decided the transport: **polling**, not SSE and
 * not WebSocket. The reasoning, recorded because it will otherwise be re-litigated -- this is a
 * *multi-viewer* problem (several coordinators on one queue) and the product's only existing
 * stream, the driver `/chat` SSE, is single-consumer, so extending it needs real rework of its race
 * semantics. At the stated 5-concurrent-user scale a poll is sufficient, deploys/monitors/secures
 * nothing new, and reverts by setting this constant back to `false`.
 *
 * **The concern that kept this flag off is answered rather than waived.** The previous comment
 * (and `components/queue-tab.tsx`'s own header) argued that a background poll would re-sort rows
 * under a planner mid-decision, which is exactly what U19 forbids -- composite urgency is a
 * function of the TTL, so the correct order genuinely drifts every second. That argument was
 * against a *naive* poll and it still stands. What ships is not naive: every response goes through
 * `lib/live-queue.ts::mergeQueue`, which
 *
 *  - adopts server order only when nothing is focused, nothing is selected, no dialog is open and
 *    no write is in flight;
 *  - otherwise PINS the order, refreshes each visible row's own fields in place (including
 *    `snapshot_hash` -- freezing that would turn `SNAPSHOT_STALE` from a rare race into the normal
 *    outcome), stages arrivals behind the pill, and marks a row the server has dropped **in place**
 *    rather than removing it, because removing it moves every row below it;
 *  - is skipped entirely (`paused`) while a confirm / reject / counter-offer / bulk-confirm is in
 *    flight, so a poll can never land underneath a write.
 *
 * The two announcement rows `accessibility-behaviour.md` wrote for this surface by name are both
 * implemented and are deliberately **not** unified: *"Planner queue — new row arrives"* is
 * `polite` and count-only (`role="status"`, the sentence is "3 new requests" and never a row's
 * content); *"the row a user IS focused on is acted on elsewhere"* is `assertive` (`role="alert"`
 * on that row only). A row that vanishes while the planner is focused **somewhere else** is
 * silent, per the same matrix.
 *
 * **Interval: 15s, visible tabs only, exponential backoff with jitter on failure.** No design file
 * names a number; see `shared/lib/live-poll.ts` for why 15s and why a hidden tab stops polling
 * altogether rather than slowing down.
 *
 * **Known limit, stated rather than hidden:** the "N new" count is at most one interval stale, so a
 * request that arrives 2 seconds after a poll is invisible for up to 13 more. That is inherent to
 * polling and is the cost the owner's decision accepted; the explicit Refresh remains, and it is
 * the escape hatch for a planner who wants certainty now.
 *
 * **To revert:** set this to `false`. The queue keeps working; the pill and the `S` key disappear
 * and the tab says plainly that new requests will not appear on their own.
 */
export const plannerLiveArrivalsEnabled = true

/**
 * Gates Confirm and its refusal taxonomy (states 1, 6, 8) once a queue row exists to confirm.
 *
 * **Default OFF. Both backend blockers are GONE; the UI is what is missing.**
 *
 * P-G2 / issue #61 **RESOLVED**: `backend/app/scheduling/snapshot.py` exists
 * (`planner_snapshot_hash`, `batch_snapshot_hash`, `displacement_conflicts`), a leaf module so it
 * does not close the `allocation -> planner_service -> expiry` import cycle. Its digest is
 * byte-identical to the queue producer's, guarded by both a function-level equality test and a
 * query-level integration test against live rows.
 *
 * P-G3 / issue #62 **RESOLVED**: `_snapshot_guard` runs inside `confirm_appointment`'s existing
 * `FOR UPDATE`, in the order `ALREADY_ACTIONED -> DISPLACEMENT_DETECTED -> SNAPSHOT_STALE` (that
 * order is load-bearing -- conflicts are inside the digest, so a staleness check first would make
 * `DISPLACEMENT_DETECTED` unreachable). `warehouse_confirmation_ref` was made **optional** with
 * `COALESCE(:ref, warehouse_confirmation_ref)`, so the missing-UI problem this comment used to
 * describe no longer exists.
 *
 * **ON since 2026-08-29.** `lib/api.ts::confirmRequest` calls the shipped route and
 * `components/queue-row.tsx` renders the control; the refusal taxonomy is implemented in
 * `lib/refusals.ts` with all three outcomes told apart **by code, never by message text**.
 *
 * **What was verified about this write path**, beyond "the endpoint exists":
 *
 *  - `snapshot_hash` round-trips verbatim from the row the planner read. It is a required
 *    argument at every layer of this client and is never recomputed locally -- a recomputed hash
 *    would either lie about what the planner saw or accidentally match and defeat the guard.
 *  - `warehouse_confirmation_ref` is deliberately NOT sent. #62 made it optional precisely
 *    because this console has no source for one; omitting it leaves the stored value untouched
 *    via `COALESCE`, where sending a synthesised one would stamp a fake warehouse acknowledgement.
 *  - `SNAPSHOT_STALE` carries `current_snapshot_hash` in its own body, so recovery needs no second
 *    call -- `lib/refusals.ts` parses the drift document rather than re-reading the queue.
 *  - `Idempotency-Key` is one UUID per *press*, reused across a retry of that press. Generating a
 *    fresh key inside the request helper would have looked correct and silently defeated U70.
 *
 * **The #62 asymmetry is CLOSED as of issue #88 (2026-09-02).** It used to read, correctly at the
 * time, that `DISPLACEMENT_DETECTED` was a superset of what the row displayed: the write path
 * counted `snapshot.py::displacement_conflicts` (`conflicts + dock_blocks`) while the row's column
 * came from `planner_service._conflicts_for`, the overlapping-claim half only -- so a planner could
 * be refused for a dock taken offline under them since render, a reason their screen never showed.
 *
 * #88 made the row carry **both** legs, each tagged with a `conflict_type`
 * (`INTERVAL_CONFLICT` | `DOCK_BLOCKED`), so the row and the refusal now count the same thing. The
 * client half of that landed here the same day: `lib/types.ts`'s `QueueConflict` is a discriminated
 * union and `lib/format.ts::describeDisplacement` renders the two legs as different sentences --
 * a blocked dock displaces nobody and carries no `shipment_id`, which is why reading one off it
 * previously rendered "Confirming this displaces undefined."
 *
 * What has not changed, and still matters: the refusal renders **whatever the server actually
 * returned**, never the row's idea of the conflict set. The two agreeing is now the expected case
 * rather than the guaranteed one -- a row rendered before a dock went offline is still stale by
 * definition, and that is a race, not an asymmetry.
 */
export const plannerConfirmEnabled = true

/**
 * Gates the counter-offer board-picker (U103, states 3, 24, 25) -- the one affordance that leaves
 * the Queue tab and the reason the Board tab has an interactive mode at all.
 *
 * **Default OFF. The backend landed; the picker did not.**
 *
 * P-G4 / issue #63 **RESOLVED**: `counter_offer` is built -- it resolves `(dock_id, start_ts)` to a
 * slot, runs full Stage-1 revalidation through `explain_slot_eligibility` (stricter than
 * `request_slot`'s reduced call), then release-then-reclaim inside one transaction, snapshot-guarded
 * under the row lock like `confirm_request`.
 *
 * **ON since 2026-08-29, via an interim form rather than the designed board picker. Read this
 * before assuming the design shipped.**
 *
 * `components/counter-offer-dialog.tsx` is a dialog, not U103's dock/time grid. The grid needs
 * `dock_occupancy.state` to colour lanes and dim ineligible docks -- issue #53, whose migration
 * is written but applied to no database -- so the spatial picker cannot be built today, while the
 * `counter_offer` backend is complete and tested. The choice was between an interim entry point
 * and leaving a finished tool unreachable behind an unapplied migration.
 *
 * **What the interim keeps, and it is the part that matters:** the offered intervals come from
 * `find_feasible_slots` (Stage 1) for *this shipment*, which is the same eligibility the dimmed
 * lanes were going to express spatially, and the server still revalidates the chosen interval
 * through `explain_slot_eligibility` before reserving it. A planner cannot hand out an infeasible
 * slot either way. **What it loses:** the spatial context -- seeing *why* a dock is unavailable by
 * looking at what occupies it. That returns with the board.
 *
 * The alternative considered and rejected: a raw dock + time-of-day form. `counter_offer` matches
 * `(dock_id, start_ts)` to an `appointment_slots` row **exactly**, so a typed timestamp would make
 * `INTERVAL_UNAVAILABLE` the normal outcome instead of a rare race.
 *
 * **Two owner decisions carried from #63, both still unresolved:** there is no "awaiting driver"
 * status to write (derivable only from `audit_logs.new_value_json.transition = 'COUNTER_OFFERED'`),
 * so Flow 2's distinct micro-state on the row cannot be rendered -- the row re-reads and shows its
 * new interval instead; and counter-offer deliberately does **not** reset the D9 clock, so the
 * driver replies against the original deadline. If it should buy fresh time, that belongs in
 * `appointments.expires_at` (#64).
 *
 * **Exit criterion for replacing the interim:** #53 applied, `dockBoardEnabled` on, then the
 * dialog gives way to the board picker.
 */
export const plannerCounterOfferEnabled = true

/**
 * Gates U103's **board picker** -- `screens.md` section 4, states 3/24/25: Counter-offer on a
 * queue row switches to the Board tab pinned to that request, a persistent banner names the
 * shipment and offers Cancel, and the planner clicks an open interval on an eligible dock.
 *
 * **ON since 2026-09-02.** `plannerCounterOfferEnabled`'s own comment set the exit criterion --
 * *"#53 applied, `dockBoardEnabled` on, then the dialog gives way to the board picker"* -- and
 * named the remaining third as "build work, not a gate". Both gates are met (`dockBoardEnabled`
 * has been on since 2026-08-31) and this is that build.
 *
 * ## What is genuinely spatial now, and what is honestly not
 *
 * **Built:** the pinned banner with Cancel; the board rendered underneath it with each *feasible*
 * interval drawn as a real focusable button at its true position in its own dock lane; lanes with
 * no feasible interval for this shipment dimmed and non-interactive (`components.md` section 18's
 * **Disabled**, not Inactive -- a heavy-only shipment's ineligibility for D1-D4 is a
 * prerequisite, not a permission); `INTERVAL_UNAVAILABLE` re-fetching so the board re-renders with
 * that interval gone rather than dead-clicking, which is section 4's own stated refusal behaviour.
 *
 * **Not built, and stated rather than implied:** eligibility here is *derived from Stage 1's
 * answer*, not computed per lane. `find_feasible_slots` returns the intervals that are feasible
 * for this shipment; a lane is drawn eligible exactly when at least one of them lands on it. That
 * is the same eligibility the design's dimming was going to express, but it cannot say **why** an
 * ineligible dock is ineligible (weight class? refrigeration? already occupied?) -- no read
 * returns per-dock-per-shipment constraint failures. The lane's tooltip says "no feasible interval
 * for this shipment", which is true and is all the server actually told us.
 *
 * **A second honest boundary:** the board's horizon is "four hours, or until closing time"
 * (server-computed), while Stage 1's feasible set can reach beyond it. Options that fall outside
 * the drawn horizon cannot be plotted, so the banner **counts them and says so**, and the interim
 * dialog stays reachable as the way to take one. A picker that silently dropped four of six
 * options would be worse than the dialog it replaced.
 *
 * ## The reason code is still required, and the design's sketch omits it
 *
 * `counter_offer` takes `reason_code` (section 7.5.1) and the server 422s without a supported one.
 * `screens.md` section 4 draws only the click. So the picker collects the reason in the banner
 * *after* an interval is chosen -- the spatial act stays a click, and the contract's required
 * argument is gathered in the one place the planner is already looking. Flagged rather than
 * silently resolved: the design's sketch and the tool's signature disagree, and this is the
 * reading that keeps both true.
 *
 * **To revert:** set this to `false`. Counter-offer returns to `counter-offer-dialog.tsx`, which
 * is kept for exactly that reason and is also still the route for an out-of-horizon option.
 */
export const plannerBoardPickerEnabled = true

/**
 * Gates Hold for information (states 7, 14, 15) -- section 7.5.1 / FR-PLN-004,
 * `flows-and-states.md` Flow 4, keyboard `H`.
 *
 * **ON since 2026-09-02 (issue #64).** Both gates this comment previously named are met, and each
 * was re-checked against the code rather than taken from the issue's title:
 *
 *  1. **The column is live.** `appointments.expires_at` exists and is swept
 *     (`repositories/operations.py:142` reads `(a.expires_at IS NOT NULL) AS hold_used`), retiring
 *     `expiry.py`'s original stated blocker.
 *  2. **The tool ships.** `POST /shipments/{id}/appointments/{id}/hold-for-information`
 *     (`routers/scheduling.py:414`) -> `allocation.hold_for_information`, returning a real
 *     `new_deadline` / `previous_deadline` / `extension_minutes`, `Idempotency-Key` required,
 *     `OPS_PORTAL_ROLES`, scope asserted server-side off the shipment (M15 -- no scope id is
 *     accepted from the caller).
 *  3. **The queue read feeds the UI.** `ttl.hold_used` is on every row
 *     (`planner_service.py:237-248`), which is what lets the one-shot cap be *prevented* rather
 *     than handled after a 409 (`edge-cases.md` #6).
 *
 * ## The one thing that is NOT what the design describes, stated here rather than discovered later
 *
 * U67 and `00-foundations/components.md` §3 specify a **pause**: the D9 clock stops, the numeric
 * value "freezes and hides", and it *resumes* with a visible transition when the driver answers.
 * **The shipped tool is a bounded extension, not a pause** -- it writes `expires_at = now + N`
 * once, time keeps elapsing against the new deadline, and nothing resumes because nothing stopped.
 *
 * So the row takes U67's visual language (pause icon, neutral colour off the urgency scale, held
 * label) but **keeps the number visible**, which U67 says to hide. Hiding it would invert U67's own
 * stated reason for hiding it -- it protects against the misread "time is still passing normally"
 * when it is not, and here time genuinely is. Full reasoning at the render site
 * (`components/queue-row.tsx`'s TTL cell). **Owner fork:** accept extension semantics and correct
 * U67's copy, or build real pause/resume server-side and then hide the number as written.
 *
 * Also note the tool is **REST-only and deliberately not an LLM tool** -- section 7.5.4's driver
 * allowlist does not contain it, and the route's own docstring records that check.
 *
 * **To revert:** set this to `false`. The Hold affordance returns to Inactive with its reason, the
 * `H` key stops opening the dialog (`openHold` is flag-guarded), and nothing else changes.
 */
export const plannerHoldEnabled = true

/**
 * Gates Bulk confirm (states 9, 10) -- "Select all eligible (N)" and the server-side re-check of
 * the five safe-batch predicates at press time.
 *
 * **Default OFF. The backend landed with the server-side re-check intact; the UI did not.**
 *
 * P-G6 / issue #65 **RESOLVED**: `bulk_confirm` ships with `evaluate_safe_batch_predicates` -- all
 * five section 7.3 safe-batch predicates re-evaluated **server-side at press time**, pure,
 * exported and individually tested. No client-side approximation was accepted, so the standing
 * instruction below still holds and is now enforced by the server rather than only by this
 * comment.
 *
 * **ON since 2026-08-29.** The selection model, "Select all eligible (N)" and the contextual
 * action bar are in `components/queue-tab.tsx`, and `lib/api.ts::bulkConfirm` calls the route.
 *
 * **What was verified about this write path:**
 *
 *  - The batch token is composed from the per-row `snapshot_hash` values the queue already handed
 *    us, by `lib/batch-hash.ts`, which replicates `snapshot.py::batch_snapshot_hash`
 *    byte-for-byte. That composition is the design (`bulk_confirm` takes one hash for N ids, and
 *    the server's own docstring says the client must derive it) -- it is **not** a client-side
 *    approximation of a server check. The five predicates are still evaluated server-side at
 *    press time and nothing here influences them.
 *  - The Python/JS canonicalisation was checked by running both on the same input rather than
 *    assumed compatible; `sort_keys=True` emits `"rows"` before `"v"`, which a naive port gets
 *    wrong. `crypto.subtle` is secure-context-only (MDN), so its availability is checked and bulk
 *    confirm hides rather than sending a token it could not compute.
 *  - The response is rendered as **per-id outcomes**, never collapsed into one verdict: confirmed
 *    rows leave, skipped rows stay visible with their failing predicate named on the row, and the
 *    summary toast names the skipped shipments (Flow 6 step 4, `edge-cases.md` #7).
 *
 * **Owner decision still open (#65's own fork):** a composite batch-hash mismatch is *reported*
 * (`snapshot_hash_matched: false`) and does **not** refuse the batch. This UI therefore renders it
 * as an explanatory notice -- "the server re-checked every one at press time, so these outcomes
 * are against current data" -- rather than as a failure. If the owner decides it should hard-refuse,
 * that copy changes with it.
 *
 * **Known honest limit:** "Select all eligible (N)" pre-ticks from the **three** safe-batch
 * predicates a queue row can express. The other two (operating window, open escalation) are not in
 * the read's payload, so they are not guessed at -- see `clientVisibleEligibility` in
 * `components/queue-tab.tsx` for why an ineligible row is still selectable rather than disabled.
 */
export const plannerBulkConfirmEnabled = true

/**
 * Gates the Board tab's "at rest" occupancy view (states 2, 22).
 *
 * **ON since 2026-08-31. All three gates are met, and the third was real build work rather than a
 * wait.**
 *
 *  1. **The D2 migration is applied to production.** `dock_occupancy.state` / `.expires_at` exist.
 *  2. **Issue #84 is fixed**, and it was the correctness gate rather than a cosmetic one. The
 *     occupancy query INNER-JOINed `appointments` while `create_hold` writes `appointment_id NULL`,
 *     so a HELD row was invisible to it -- proven empirically, the query returned 0 conflicts
 *     against a live HELD row the database's own exclusion constraint would refuse. It now LEFT-joins
 *     and admits `o.state = ANY(:hold_states)`
 *     (`repositories/operations.py::_LIVE_DOCK_OCCUPANCY_WITH_HOLDS_SQL`).
 *  3. **The board's occupancy fetch is wired** -- `GET /api/v1/planner/board`
 *     (`routers/planner.py::planner_board` -> `planner_service.get_dock_board`), consumed by
 *     `components/dock-board.tsx` via `lib/api.ts::fetchDockBoard`.
 *
 * **What was verified about this read path before flipping**, not merely that a route exists:
 *
 *  - It reuses the **same** `list_live_dock_occupancy` the queue's displacement check runs, rather
 *    than a second board-specific occupancy query. Issue #84 is exactly what a second one costs when
 *    it drifts, so there is one answer to "what is on this dock" on both paths.
 *  - Scope resolves without a client-supplied id: `resolve_facility_scope(..., require_facility=
 *    True)`, identical to `/queue`, so `facility_id` is a narrowing request and a mismatch is a
 *    server-side 403.
 *  - The horizon is computed server-side -- "four hours, or until closing time, whichever comes
 *    sooner" needs the facility's own timezone and `close_time`, and a browser deriving those from a
 *    local clock is the wrong-day hazard this product designs against. `horizon_end_reason` says
 *    which bound applied, so the caption states it rather than guessing.
 *  - The now-line runs off `CountdownProvider`'s measured server offset, fed from the board
 *    payload's own `as_of`. Never bare `Date.now()`.
 *  - `holds_enabled` is echoed from `TWO_PHASE_HOLD_ENABLED`, so the legend omits a HELD swatch on a
 *    deploy where no `dock_occupancy` row could be in that state, rather than showing a dead entry.
 *
 * **The nine-value mapping table lives in `lib/board.ts`, in one record**, per `components.md`
 * section 3's own rule that "a new `dock_occupancy` state added later gets a mapping-table row, not
 * a bespoke branch". The five terminal states map to `null` -- open lane space, never a ghost bar.
 *
 * **Fork F resolved as its own recommendation (c)**: the HELD bar's border measured 2.91:1 against
 * the board's `surface-hover` track, 0.09 short of 1.4.11's 3:1, because the promise-state border
 * palette was tuned against chip backgrounds. A **component-scoped** `--dock-bar-held-border`
 * (`tokens.md`'s component tier, U85) is declared on the board root at `amber-700` (4.58:1
 * measured) rather than raising the foundations token, which would change the chip on three other
 * surfaces to fix one. Dark is left on the foundations token, which already clears 3:1.
 *
 * **What this flag does NOT turn on, stated rather than implied:** the counter-offer picker's
 * interactive mode (states 3, 24, 25 -- eligible lanes highlighted, ineligible dimmed). That needs
 * per-shipment eligibility over these lanes, a different read from this one, so
 * `plannerCounterOfferEnabled`'s interim dialog remains the entry point. Its own comment's exit
 * criterion ("#53 applied, `dockBoardEnabled` on, then the dialog gives way to the board picker")
 * is now two-thirds met and the remaining third is build work, not a gate.
 *
 * States 23 (board load failed) and 28 (board loading skeleton) are NOT behind this flag -- they are
 * structural/negative states and ship unconditionally; they are now reachable through the board's
 * own fetch rather than only through the gallery. The block-dock group (states 16-18) is also NOT
 * behind this flag and never was.
 *
 * **To revert:** set this to `false`. The Board tab returns to the honest `NotYetAvailable` panel;
 * Block a dock and Review proposal keep working, as they always did. The backend route is additive
 * and harmless if unread.
 */
export const dockBoardEnabled = true

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
