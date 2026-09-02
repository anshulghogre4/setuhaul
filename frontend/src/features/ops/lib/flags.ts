/**
 * Ops-surface feature flags.
 *
 * Named for the DEPENDENCY, not the feature, per E5.1's precedent
 * (`features/driver/lib/flags.ts`) -- so it is obvious what removes a flag rather than obvious
 * what it hides. Each names the issue that has to close before it can flip.
 */

/**
 * Gates every live behaviour on this surface: prompt 3's "N new · press S" count, `edge-cases.md`
 * section 2's assertive race announcement, section 9's inline new-fact notice, and the status bar's
 * polite connection row.
 *
 * **ON since 2026-08-31 (issue #59).** The owner decided the transport: **polling**, not SSE and
 * not WebSocket. This queue is multi-viewer (several coordinators on one facility) and the only
 * stream in the product -- the driver `/chat` SSE -- is single-consumer, so extending it would mean
 * reworking its race semantics for a case it was never built for. At 5 concurrent users a poll is
 * sufficient and adds nothing to deploy, monitor or secure.
 *
 * **It reuses `GET /api/v1/operations/escalation-queue`. No new endpoint was added**, and none is
 * needed: the existing read already carries every field the four behaviours turn on
 * (`owner_user_id`/`owner_name` for the race, `escalation_status` + `stepper_position` for the
 * lifecycle, `thread_status` for takeover, `updated_at` to name a time). A count/delta endpoint
 * would have been a second source of truth for the same rows at this scale.
 *
 * **The one thing it genuinely cannot do**, reported rather than approximated:
 * `edge-cases.md` section 9's example sentence is *"SHP1015 was confirmed by another planner at
 * 09:58"* -- a **shipment** fact. `get_exception_queue`'s SELECT returns no shipment or appointment
 * status, so the inline notice names every escalation-level change (ownership, status, takeover)
 * and does not invent the shipment-level one. Closing that needs a server-side field, not a client
 * workaround.
 *
 * **Interval 15s, visible tabs only, exponential backoff with jitter on failure** --
 * `shared/lib/live-poll.ts` states why 15s and why a hidden tab stops entirely.
 *
 * **To revert:** set this to `false`. The console returns to a snapshot refreshed by explicit
 * action; nothing else needs touching.
 */
export const opsLiveUpdatesEnabled = true

/**
 * Gates "Request sequencer proposal" (prompt 14's only action on a capacity incident) and the
 * post-request handoff state ("Proposal requested · routed to Planner queue").
 *
 * **Still OFF as of 2026-09-02 -- but the reason has changed completely, and the new reason is the
 * only thing standing between this and `true`.**
 *
 * ## What is now DELIVERED (issues #54/#49, FR-OPS-004)
 *
 * The old reason -- *"there is nothing to request a proposal FROM"* -- is retired. Section 7.5.3
 * landed this session and section 7.5.5's delegate landed with it, verified by reading the router
 * rather than an issue title:
 *
 *  - **`POST /api/v1/operations/escalations/{escalation_id}/sequencer-proposal`** exists
 *    (`routers/operations.py:211`), gated `OPS_PORTAL_ROLES`, returning `SchedulingRunResult` --
 *    literally *"the same shape section 7.5.3 already defines"*, as the catalog requires.
 *  - It is a **real delegate, not a parallel tool**: `trigger_reason = 'CAPACITY_INCIDENT'` is
 *    server-pinned and this escalation's id is persisted on the run as a real FK
 *    (`scheduling_runs.escalation_id`), so the incident and the run stay linkable.
 *  - **It cannot apply.** `apply_schedule_proposal` sits on `routers/scheduling.py` behind
 *    `WAREHOUSE_PLANNER`/`ADMIN` only -- D5 surviving the two-surface handoff structurally rather
 *    than by UI convention.
 *  - The client half is built and reconciled to that route: `lib/api.ts::requestSequencerProposal`,
 *    plus prompt 14's State 3 handoff and `edge-cases.md` section 4's `RUN_ALREADY_ACTIVE` inline
 *    state in `capacity-incident-row.tsx`. Both scope branches of "View in planner queue" render at
 *    `/ops/_states` plate 14.
 *
 * Two contract details were confirmed against the landed route rather than assumed, because both
 * would have been silent defects: the body is `extra="forbid"` with `facility_id` **optional**, so
 * sending nothing is a supported call and M15 is honoured (the facility comes from the escalation's
 * own row); and there is **no `Idempotency-Key`**, deliberately -- a proposal consumes no capacity,
 * and `scheduling_runs`' partial unique index makes a double-press produce one run plus a named
 * refusal, which is stronger than two runs sharing a key.
 *
 * ## ON since 2026-09-02, on a driven round trip rather than a source read
 *
 * This flag stayed off through two earlier checkpoints. First `request_sequencer_proposal` did not
 * exist; then it was mounted but **500'd** on
 * `UndefinedTableError: relation "public.scheduling_runs" does not exist` -- the migration was
 * written and unapplied. That is why *"the route appears in `/openapi.json`"* was never accepted
 * here as evidence: a mounted route is not a working feature, and flipping then would have put a
 * 500 behind the only action this console has on an incident.
 *
 * The owner applied the migration and the engine now answers. Verified end to end on the live
 * stack, against a real sandbox capacity incident at `FAC-GGN-01`:
 *
 * ```
 * POST /api/v1/operations/escalate              -> 200  (incident created)
 * POST /operations/escalations/{id}/acknowledge -> 200
 * POST /operations/escalations/{id}/sequencer-proposal -> a real SchedulingRunResult
 * POST /operations/escalations/{id}/cancel      -> 200  (probe cleaned up)
 * ```
 *
 * plus the engine's own round trip on the planner side -- propose -> replay -> list -> debounce
 * (`RUN_ALREADY_ACTIVE`) -> deliberate `SNAPSHOT_DRIFT` refusal -- recorded in
 * `features/planner/lib/flags.ts::sequencerProposalEnabled`. **No proposal was ever applied**: this
 * console structurally cannot apply one (D5), and the planner-side probe left its run un-applied.
 *
 * **One real guard proven along the way, and worth keeping in mind when reading Flow 4:** called on
 * an *unacknowledged* incident the delegate answers **409 `NOT_ACKNOWLEDGED`**
 * (`escalation_status=OPEN, stepper=0`) before it touches the sequencer at all. So Flow 4's
 * ordering -- expand, read, *then* act -- is enforced server-side, not merely by this UI's layout.
 * The row surfaces it through the same failure path as any other refusal rather than pretending it
 * cannot happen.
 *
 * **To revert:** set this to `false`. The action returns to Inactive with its reason and the
 * handoff state stops rendering; nothing else needs touching.
 */
export const sequencerProposalEnabled = true

/**
 * Gates the whole coordinator reply path: the takeover control, the thread composer and its Send
 * action (prompt 8; also prompt 12's second gate, which stays unreachable for its own reason --
 * `copilotActiveEnabled` below).
 *
 * **ON as of 2026-08-31. The four exit criteria the previous audit set are all met, and the
 * read/write path is wired end to end rather than merely reachable.**
 *
 * The backends, verified by reading `app/api/v1/routers/operations.py` and
 * `app/services/thread_message_service.py` directly rather than trusting an issue title (#55, #56
 * and #58 are all still OPEN -- this repo closes on owner review, so OPEN never meant unbuilt):
 *
 *  - `POST /api/v1/operations/threads/{thread_id}/messages` (line 248) -- the first code in the
 *    product to write `sender_type = 'OPERATIONS'`. `Idempotency-Key` is **required** here, unlike
 *    `resolve_escalation`'s optional one, because a driver reads this and nobody can unsend it.
 *    Body is `extra="forbid"`: `message_text` + optional `client_message_id` and nothing else --
 *    sender, driver and facility are all derived server-side (M15/NFR-019).
 *  - `GET /api/v1/operations/threads/{thread_id}/messages` (line 230) -- the ops-side thread read
 *    this surface's detail pane was missing (`chat.py`'s history route is DRIVER-only and
 *    Redis-backed).
 *  - `get_escalation_queue` rows carry `thread_id`/`thread_status` via `LEFT JOIN LATERAL`, which
 *    closes the gap E5.2 filed: the console was rendering a takeover button it had no argument to
 *    call.
 *  - `POST /operations/escalations/{id}/start` (line 175) makes `IN_PROGRESS` writable, so the
 *    stepper's middle dot is reachable and `hand_back` could tighten its guard to `IN_PROGRESS`.
 *
 * What this build added, which is what actually justifies the flip:
 *   1. `thread_id`/`thread_status` on `EscalationQueueItem` (`lib/types.ts`).
 *   2. `postOperationsMessage`, `fetchThreadMessages`, `startEscalationWork` (`lib/api.ts`), with
 *      the `Idempotency-Key` owned by the caller so a retry reuses it verbatim.
 *   3. `takeOverThread`/`handBackThread` wired to the now-available id (`takeover-control.tsx`) --
 *      replacing a `<Button variant="cautionary">` that had **no `onClick` at all**.
 *   4. The composer itself (`thread-composer.tsx`) and the transcript (`thread-transcript.tsx`).
 *
 * **#58's residual is surfaced, not hidden.** A message posted while the Redis projection is
 * unavailable is durable in `chat_messages` but **will not appear in the driver's feed even after
 * Redis recovers** -- nothing back-fills. `delivered`/`delivery_reason` come back per call and are
 * rendered as a persistent per-message "Not shown to the driver" marker (`lib/delivery.ts`,
 * `thread-transcript.tsx`), never as an unqualified success and never as a toast that erases the
 * only trace of it.
 *
 * **To revert:** set this to `false`. The detail pane falls back to `UnwiredTakeoverNote` and the
 * composer stops rendering; nothing else needs touching.
 */
export const sendAsOperationsEnabled = true

/**
 * Gates the co-pilot's suggestion panel.
 *
 * **ON as of 2026-08-31, issue #57.** The owner scoped the co-pilot that day and this build gave
 * it a contract, so the exit criterion this flag was written against ("issue #57 closed with a
 * scoped, owner-approved contract") is met.
 *
 * ## What the co-pilot is now, and what it is not
 *
 * It suggests **one resolution action and the facts that point at it** --
 * `GET /api/v1/operations/escalations/{id}/suggestion`,
 * `backend/app/services/ops_copilot.py`. It does **not** summarise the thread and does **not**
 * draft a reply, so `components.md` section 3's three capabilities and `REQUIREMENTS.md`'s
 * `FR-OPS-003` are deliberately unbuilt. The Inactive state (prompt 11) still ships regardless of
 * this flag; only the fetch and the result card are behind it.
 *
 * ## Why this flip is not the trap the last two were
 *
 * The previous gates hid a panel with **no backend at all**. This one is verified hop by hop, and
 * each hop was actually executed rather than reasoned about:
 *
 *  - **SQL against the live schema.** All six SELECTs in `repositories/copilot.py` were run
 *    read-only against the live Supabase Postgres and returned exactly the expected columns; the
 *    engine was then run over every escalation type present in live data.
 *  - **HTTP.** FastAPI `TestClient` through the real ASGI stack: 200 with the `ok()` envelope for
 *    an ops role, 403 for `DRIVER`, and the route table asserts the path is **GET-only** with no
 *    mutating sibling anywhere in the app.
 *  - **The URL seam.** The template literal in `lib/api.ts` is compared against the app's own
 *    OpenAPI path table in `test_the_frontend_calls_the_path_the_backend_actually_mounts` -- the
 *    one typo class neither TypeScript nor pytest would otherwise see.
 *  - **Browser render.** Prompts 11/12/13 rendered in Chromium at `/ops/_states`, zero page
 *    errors, the polite live region present.
 *
 * **What was NOT verified, stated plainly:** an authenticated round trip through the deployed
 * stack. `SETUHAUL_POC_*` credentials in `.env`/`.env.local` are blank, so no real Supabase JWT
 * could be obtained. The auth hop is the standard `require_roles(*OPS_PORTAL_ROLES)` dependency
 * every other ops endpoint already uses, and the scope check is `assert_facility_visible`, which
 * `operations_reads.get_thread_messages` already uses on this same surface -- no new mechanism.
 *
 * ## Blast radius if it is wrong
 *
 * One line of text in the right-hand pane. `CopilotPane` owns its own fetch and its own error
 * state; `ops-console.tsx` neither awaits it nor reads from it, so a failing suggestion cannot
 * touch the queue, the detail pane, the transcript, the composer or any action. That is
 * `edge-cases.md` #5 ("fully operable with the co-pilot entirely down") and U84's secondary-region
 * policy, satisfied structurally rather than by intent.
 *
 * ## Honest note about live data
 *
 * `escalation_queue` currently holds only `NO_FEASIBLE_SLOT` and the two D12 backfill types
 * (`REQUIRES_TIME_RESOLUTION`, `REQUIRES_DOCK_REASSIGNMENT`, neither of which is in §7.4 at all).
 * Six of §7.4's nine reasons have no producer anywhere in `backend/app/`. So in practice the
 * panel will mostly say "Acknowledge" and list facts. That is a statement about the data, not a
 * defect in the engine, and gating it would not change it.
 *
 * **To revert:** set this to `false`. The pane falls back to its Inactive explanation and nothing
 * else needs touching.
 */
export const copilotActiveEnabled = true
