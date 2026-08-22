# Comparison — architecture (Phase 0 of TASKS.md)

> Scope: `SYSTEM_DESIGN.md` §3 (12 modules) + `SOLUTION_DESIGN.md` §6/§7.5 (module map, tool catalogs)
> against the live `backend/app/`, `frontend/src/`, `supabase/migrations/` as read on this pass (2026-08-22).
> Comparison only — nothing under `backend/`, `frontend/`, `supabase/` was edited.

---

## 1. Module mapping — the 12 enforced boundaries vs. live code

| # | Module (`SYSTEM_DESIGN.md` §3) | Live file(s) | Status |
|---|---|---|---|
| 1 | Driver Conversation | `backend/app/assistant/{tools,prompts,run_assistant,agentcore_runtime,agentcore_main,llm}.py`, `backend/app/api/v1/routers/chat.py` | **Implemented**, driver-scoped only. `run_assistant.py` is a hand-rolled bounded tool loop (`MAX_TOOL_ROUNDS = 6`), not `create_agent`/`AgentExecutor` — matches the doc's own framing in TASKS.md Phase 6.3. |
| 2 | Exception Intake | `backend/app/services/eta_service.py` (writes `driver_exceptions` inline inside `record_eta_update`), `backend/app/services/driver_reads.py::report_vehicle_breakdown_or_incident` | **Implemented but not module-owned** — no standalone exception-intake service; the write path is embedded inside the ETA-update transaction and a separate driver-read helper. No dedicated dedupe/typing service. |
| 3 | ETA Service | `backend/app/services/eta_service.py` | **Implemented.** Append-only `eta_updates` insert + `shipments.latest_eta_ts` update, single transaction, idempotency-keyed. |
| 4 | Feasibility & Ranking Engine | `backend/app/scheduling/feasibility.py`, `backend/app/scheduling/constraints.py` | **Partially implemented.** Stage 1 hard constraints and Stage 2 weighted ranking exist. Stage 0 (multi-day horizon, `NO_SAME_DAY_SLOT` vs `NO_FEASIBLE_SLOT` split) and the facility-rules/driver-window additions from `SOLUTION_DESIGN.md` §5 Stage 1 are **absent** — see Finding F4 below. |
| 5 | Allocation & Promise Lifecycle | `backend/app/scheduling/allocation.py`, `backend/app/api/v1/routers/scheduling.py` | **Partially implemented.** `request_slot`/`cancel_appointment`/`confirm_appointment`/`reject_appointment`/`expire_appointment`/`reschedule_appointment` all exist with `Idempotency-Key` support. Concurrency control is `SELECT … FOR UPDATE` + the two legacy unique constraints (`ux_active_appointment_per_slot`, `ux_current_active_appointment_per_shipment`) — **not** D1's `dock_occupancy` + GiST `EXCLUDE`. See Finding F1. |
| 6 | Facility Sequencer | — | **Not implemented.** No `scheduling_runs` table, no `propose_facility_schedule`/`apply_schedule_proposal`, no greedy-insertion engine anywhere in `backend/app/`. |
| 7 | Gate & Yard | `backend/app/services/driver_reads.py::get_gate_and_queue_status` (read-only, driver-scoped) | **Not implemented as a writable module.** `facility_checkins` has no write path anywhere (`grep` for `record_gate_in`/`record_dock_in`/`record_unload_start_end`/`record_gate_out` returns nothing). This corrects a TASKS.md Phase 2 assumption — see §4 below. |
| 8 | Capacity & Rules Admin | `backend/app/api/v1/routers/operations.py` (`dock-status`, `facility-constraints`, `dock-snapshot` — all read-only) | **Read-only today.** No `block_dock`, `end_dock_block`, `create_facility_rule`/`update_facility_rule`, or policy-weight writes exist. |
| 9 | Escalation & Human Takeover | `backend/app/services/escalation_service.py`, `backend/app/api/v1/routers/operations.py` | **Partially implemented.** `escalate_exception`, `get_exception_queue`, `resolve_escalation` exist. `acknowledge_escalation`, `reassign_escalation`, `take_over_thread`, `hand_back_thread`, `cancel_escalation`, `request_sequencer_proposal` (§7.5.5) do **not** exist. |
| 10 | Notification / Outbox | — | **Not implemented.** No `notification_outbox` table, no outbox drain job, no EventBridge sweeper, no web-push/SES wiring found anywhere in `backend/app/`. |
| 11 | Observability & Audit | `backend/app/assistant/observability.py` (LangSmith/OTel spans), inline `audit_logs` inserts in `eta_service.py`/`allocation.py` | **Partially implemented.** Turn-level tracing and per-write audit rows exist; there is no `allocation_decisions`/`scheduling_runs` decision-receipt table — the receipt currently lives only in the in-memory `ranking_factors`/`ranking_explanation` returned to the caller, not persisted. |
| 12 | Identity & RBAC | `backend/app/core/execution_context.py`, `backend/app/core/deps.py`, `backend/app/core/security.py` | **Implemented, but without `user_scopes`.** Scope is read directly off `users.facility_id`/`users.driver_id` columns (`deps.py` lines 97-138), not a separate `user_scopes` table as `SOLUTION_DESIGN.md` §6.1 specifies. Functionally equivalent for single-facility-per-user scoping today, but does not support a user with multiple facility scopes. |

**Search (`search_records`, §7.5.8)**: no code exists yet (no route, no service). Correctly absent rather than wrongly present — nothing to flag.

---

## 2. Layering violations

**F-L1 — Routers with embedded business SQL, not thin.**
`backend/app/api/v1/routers/operations.py` (`dashboard_summary`, `list_exceptions`, `appointment_schedule`,
`dock_snapshot`, `facility_constraints` — lines 119-403) and `backend/app/api/v1/routers/driver.py`
(`driver_context`, lines 20-127) build and execute raw `text()` SQL directly inside the router function,
including scope-resolution logic (`_resolve_facility`, `operations.py` lines 39-46). `SYSTEM_DESIGN.md` §3's
first enforced rule is "routers thin → services hold rules → repositories hold persistence." These five
endpoints hold rules and persistence inline. Contrast with `chat.py`, `shipments.py`, `scheduling.py`, which
correctly delegate to `services`/`scheduling` modules.

**F-L2 — No repository layer anywhere.**
There is no `backend/app/repositories/` (or equivalent) directory. Every service (`eta_service.py`,
`escalation_service.py`, `dispatch_service.py`, `scheduling/allocation.py`, `scheduling/feasibility.py`,
`driver_reads.py`) embeds `sqlalchemy.text()` SQL directly. `SYSTEM_DESIGN.md` §3's layering rule names
repositories as the third tier, and its "no cross-module table access" enforcement plan is a "CI check on
repository imports" — a check with nothing to anchor on until a repository tier exists. This is not
necessarily wrong for a five-person team at this stage, but it means the two named CI enforcements
(import-linting, repository-import checks) are currently **unimplementable as written**, not merely unbuilt.

**F-L3 — `escalation_service.py` reads across future-module boundaries directly.**
`get_dock_status` (queries `docks`/`appointment_slots`), `get_queue_status` and `get_pending_confirmations`
(query `appointments`/`appointment_slots`/`shipments`) all live inside a file named for module 9
(Escalation & Human Takeover) but read tables that `SOLUTION_DESIGN.md` §3 assigns to modules 5, 7, and 8.
Because no module boundaries are enforced yet (F-L2), this is not a rule violation today — there is no rule
to violate — but it is exactly the shape of coupling that has to be undone before any module boundary could
be drawn, and it should not be extended further without a plan to split it.

**F-L4 — A capability exists that the target architecture explicitly excludes.**
`backend/app/services/dispatch_service.py::create_dispatch_shipment`, wired through
`backend/app/api/v1/routers/dispatch.py` and rendered by `frontend/src/features/dispatch/DispatchHome.tsx`,
lets an ops user pick a driver, pick a facility, and create a new `shipments` row with that driver assigned
— including an automatic best-slot pre-booking (`dispatch_service.py` lines 162-187). `SOLUTION_DESIGN.md`
§0.9's WON'T list states plainly: *"shipment creation and driver/vehicle assignment"* is out of scope —
*"both are TMS/carrier territory… neither has a tool, screen, or role anywhere in this design that performs
it. If that ever needs to change, it is a new integration with the TMS, not an extension of an existing
SetuHaul surface"* (§0.9, "WON'T" section). This is not a layering nit; it is a live capability that
contradicts a locked architectural boundary (§1: *"SetuHaul does not create shipments or assign drivers and
vehicles to them"*). See Finding F5 below.

---

## 3. Frontend — actual state, stated plainly

`frontend/src/` has 13 substantive files (excluding assets/CSS): `App.tsx`, `main.tsx`,
`layouts/ProtectedLayout.tsx`, `core/auth/supabase.ts`, `core/http/api.ts`,
`features/auth/LoginForm.tsx`, `features/dispatch/DispatchHome.tsx`, `features/driver/DriverHome.tsx`
(+ `DriverLayout.css`), `features/operator/OpsHomes.tsx`.

Only **three routes** exist (`App.tsx`): `/driver` (chat), `/ops` (one combined dashboard for every
non-driver role), `/dispatch` (shipment-creation console, see F-L4/F5). There is no `features/admin/`
directory — `ADMIN`/`TRANSPORT_MANAGER`/`REGIONAL_OPERATIONS_HEAD` all resolve to the same `/ops` route via
`roleToPortal()` in `core/auth/supabase.ts`, differentiated only by a `global` boolean inside `OpsHomes.tsx`.

Against the six UI-UX surfaces + shared shell:

| Surface | Live state |
|---|---|
| `01-driver-chat` | **Real implementation.** `DriverHome.tsx` is a working chat UI wired to `/api/v1/chat`, with client-side logging of scheduling-tool results. |
| `02-ops-exception-console` | **Partial/ad-hoc implementation.** `OpsHomes.tsx` renders a dashboard with shipment-status counts, an exception list, an escalation queue with a resolve modal, and a pending-confirmations list with a confirm button. It does not match U89's three-pane shell or any co-pilot affordance (U57) — it is a single-column dashboard, not the designed console. |
| `03-planner-dock-board` | **Nothing.** No Gantt, no dock board, no two-tab shell. |
| `04-gate-yard-kiosk` | **Nothing.** |
| `05-carrier-portal` | **Nothing.** |
| `06-admin-console` | **Nothing.** Admin users land on the same generic `/ops` dashboard as facility ops roles. |
| Shared shell (`00-foundations`) | **Nothing.** No notifications panel, no search palette, no role picker, no account/settings page, no password-reset flow. `ProtectedLayout.tsx` provides only a profile-menu dropdown with a logout button. |

**One additional structural note**: `DispatchHome.tsx` is a fully-built, real feature (driver/facility
pickers, priority/category/dock-type selects, a submit flow that creates a shipment and shows the resulting
pre-booked appointment) — it is not a stub. It is real, working frontend effort spent on a capability the
target architecture (§0.9) says should not exist in this product at all.

---

## 4. `[A]`-marked assumptions in `TASKS.md` Phase 0/1/2 — confirmed or corrected

| TASKS.md item | Assumption | Finding |
|---|---|---|
| 0.1 — `assistant/tools.py` | `[A]` | **Confirmed.** Exists, 839 lines, driver-scoped `StructuredTool` factory. |
| 0.1 — `assistant/prompts.py` | `[A]` | **Confirmed.** Exists, single `SYSTEM_PROMPT` string. |
| 0.1 — `scheduling/{feasibility,allocation}.py` | `[A]` | **Confirmed**, both exist at those exact paths, plus a third file `scheduling/constraints.py` (loads `constraints.json`) not named in the assumption. |
| 0.1 — `db/session.py` | `[A]` | **Confirmed.** Exists; `Database` class with `configure()`/`session()`/`ping()`/`dispose()`. |
| 0.2 — frontend structure | `[A]` "17 files … across `features/{admin,auth,dispatch,driver,operator}`" | **Corrected.** There is no `features/admin/` directory. The actual set is `features/{auth,dispatch,driver,operator}` — four feature folders, not five. Admin is not a separate feature at all; it reuses `features/operator/OpsHomes.tsx`. File count (13 substantive + assets/CSS) is roughly right, but the claimed `admin` folder does not exist. |
| 0.5 — `btree_gist` status / `text` vs `timestamptz` | Re-audit requested | **Confirmed unchanged from the 2026-08-19 finding.** No migration installs `btree_gist`; `grep` across `supabase/migrations/` for `dock_occupancy`, `btree_gist`, `EXCLUDE USING gist`, `tstzrange` returns nothing. `appointment_slots.slot_start_ts`/`slot_end_ts`, `eta_updates.declared_eta_ts`, `facility_checkins.gate_in_ts` are still declared `TEXT` in `supabase/migrations/20260805201923_setuhaul_baseline.sql`. Phase 1 (database migration) has **not started**. |
| 0.6 — D12 worklist re-count (85/116) | Flagged as needing re-measurement | **Not verified this pass.** This requires a live query against the Supabase project, which is outside what a code read can confirm. Left open, not inferred. |
| Phase 2 preamble — "§7.5.2 (gate/yard) and §7.5.4 (driver) already existed before this redesign" | Assumption baked into the phase framing | **Partially corrected.** §7.5.4 (driver) is substantially true — `tools.py` already implements a driver catalog close to the designed allowlist (plus several extra tools not in the 12-tool list: `get_current_user_context`, `get_conversation_memory`, `get_vehicle_and_carrier_details`, `get_gate_and_queue_status`, `get_facility_rules_and_restrictions`, `report_vehicle_breakdown_or_incident`, `get_dock_maintenance_alerts`). **§7.5.2 (gate/yard) did not already exist** — only a read (`get_gate_and_queue_status`, driver-scoped) exists; none of the five write tools (`record_gate_in`, `update_queue_state`, `record_dock_in`, `record_unload_start_end`, `record_gate_out`) exist anywhere. Phase 2's gate/yard work is a from-scratch build, not an extension. |
| Phase 2.1 — "extend §7.5.1 — add `block_dock`/`end_dock_block`" (implying the rest of the planner catalog already exists) | Implicit assumption | **Substantially confirmed.** `confirm_appointment`, `reject_appointment`, `expire_appointment`, `cancel_appointment`, `reschedule_appointment` all exist in `scheduling/allocation.py` with idempotency-key support, exposed via `scheduling.py`. Missing from the catalog: `get_planner_queue` (a `pending-confirmations` read exists but without the composite-urgency ordering, TTL remaining, or `snapshot_hash`), `counter_offer`, `hold_for_information`, `bulk_confirm`, `escalate_request`, `block_dock`, `end_dock_block`. None of these use a `snapshot_hash` guard on the write path the way `request_slot` does. |

---

## 5. Four-tag findings

### F1 — Concurrency control is still the row-lock design D1 explicitly replaces
- **Keep as-is / Needs improvement**: **Needs improvement.** `scheduling/allocation.py::request_slot`
  (lines 814-833) takes `SELECT … FOR UPDATE OF s` on the `shipments` row and relies on
  `ux_active_appointment_per_slot`/`ux_current_active_appointment_per_shipment` unique-constraint violations
  (`IntegrityError` caught at line 1017) to detect conflicts. `SOLUTION_DESIGN.md` §5 Stage 3 states this
  exact pattern is what D1's `dock_occupancy` + GiST `EXCLUDE` constraint is designed to replace, "because
  those are two different rows" — a 75-minute unload at 11:00 colliding with a 12:00 booking is invisible to
  a row lock or a per-slot unique index. Concretely: `supabase/migrations/` contains no `dock_occupancy`
  table and no `btree_gist` extension (confirmed §4 above), so the migration in `SOLUTION_DESIGN.md` §0 "D1
  in concrete terms" has not been applied.
- **Functional requirement mapping**: **M6** ("Capacity can never be double-promised… 50-way race yields
  exactly 1 winner"), **D1**.
- **Wrong optimisation flag**: This is not over-engineering — it is the opposite: a correctness mechanism
  the design treats as non-negotiable is currently backed by a weaker, order-of-magnitude coarser lock
  (whole-slot-row uniqueness rather than interval overlap). At 5 concurrent operators this has not yet
  produced an observed double-booking, but it is a latent defect, not a scale-appropriate simplification —
  the seeded weight/overlap violations (§6.2 #1/#7 in `SOLUTION_DESIGN.md`) exist precisely because slot-row
  granularity cannot represent true interval overlap.

### F2 — Feasibility engine is missing facility-rule and driver-window checks named in the design
- **Needs improvement.** `scheduling/feasibility.py::evaluate_candidate_slot` (lines 185-280) checks: slot
  open, no active appointment, no dock event, dock ACTIVE, dock-type match, refrigeration, weight, ETA+unload
  fits the slot, facility operating hours. It does **not** query `facility_rules` at all (no `RULE003`
  reefer-pin, `RULE004` weight-routing, `RULE005` 21:00 new-start cutoff evaluation), and does not read
  `driver_exceptions.earliest_acceptable_ts`/`latest_acceptable_ts`. `SOLUTION_DESIGN.md` §5 Stage 1 lists
  both as required additions ("facility rule evaluation with time-bounded effectivity," "the driver's own
  constraints — both ends").
- **Functional requirement mapping**: **M3** ("Deterministic feasibility — hard constraints evaluated in
  code"); `SOLUTION_DESIGN.md` §5 Stage 1's four required additions.
- **Wrong optimisation flag**: Missing optimisation, not excess — the weight check *is* implemented
  correctly (compares `load_weight_kg` against `docks.max_vehicle_weight_kg`, matching the design's §6.2 #7
  resolution), which shows the pattern is understood; the facility-rules and driver-window checks were
  simply not carried over yet.

### F3 — Stage 0 (multi-day horizon) is absent; every "no slot" outcome is currently `NO_FEASIBLE_SLOT`-shaped
- **Needs improvement.** `find_feasible_slots` (feasibility.py lines 396-422) queries candidates with only
  `slot_end_ts > eta_ts`, ordered by start time, `LIMIT 200` — there is no explicit horizon cutoff (default
  48h in the design) and no split between "today exhausted, tomorrow has options" vs. "whole horizon
  exhausted." `escalation` is built from `rejected_reasons` with a single shape (feasibility.py lines
  452-464); there is no `NO_SAME_DAY_SLOT` code path anywhere in the file.
- **Functional requirement mapping**: `SOLUTION_DESIGN.md` §5 Stage 0 ("no slot today is not the end of the
  conversation"); traceability row 10 in §0.9 ("What happens when there is no feasible slot?").
- **Wrong optimisation flag**: Missing, not excess. At current single-day-seed-plus-generated-volume scale
  this has not yet caused an observable defect, but it is the one piece of Stage 0/1 explicitly called out in
  the design as changing the SHP1015 walkthrough's correct answer.

### F4 — No repository tier means the two named CI enforcements have nothing to attach to
- **Needs improvement.** (Detailed in F-L2 above.) `SYSTEM_DESIGN.md` §11 open item 3 already flags
  "import-linting for module boundaries not yet specified as a concrete CI check" — this pass confirms the
  deeper reason: there is no repository layer, so there is nothing for such a check to inspect. Recommend
  either (a) introduce a thin repository module per future module before writing enforcement tooling, or (b)
  explicitly defer the CI check decision until module extraction actually begins, rather than treating it as
  a near-term todo.
- **Functional requirement mapping**: None directly — this is an architectural-hygiene item from
  `SYSTEM_DESIGN.md` §3, not a numbered FR/NFR.
- **Wrong optimisation flag**: Not urgent at 5-person-team scale. Building import-linting machinery now,
  before any module boundary is real, would be effort spent enforcing a rule nothing yet violates in a way
  the team could detect mechanically anyway (everything is one `services/` package).

### F5 — `dispatch_service.py`/`DispatchHome.tsx` implement an explicitly out-of-scope capability
- **Needs improvement** (structural, not cosmetic). See F-L4. The fix is not a refactor of the existing
  code — it is a scope decision: either (a) retire `dispatch.py`/`dispatch_service.py`/`DispatchHome.tsx` as
  pre-redesign scaffolding that predates the locked WON'T-list decision, or (b) if the owner wants to keep a
  synthetic "create a demo shipment" utility for testing/demos, gate it clearly as a non-product debug tool
  rather than a reachable ops-portal feature, and say so in the design doc rather than silently keeping a
  capability the architecture forbids.
- **Functional requirement mapping**: None — and that absence is itself the finding. `SOLUTION_DESIGN.md`
  §0.9 WON'T list explicitly excludes "shipment creation and driver/vehicle assignment"; no FR/NFR anywhere
  authorizes this feature.
- **Wrong optimisation flag**: **Yes, bluntly.** This is real engineering effort (a searchable driver/facility
  picker, an auto-pre-booking call into `find_feasible_slots`/`request_slot`, a results panel) built for a
  capability the target architecture says must not exist in this product — "a new integration with the TMS,
  not an extension of an existing SetuHaul surface." It is the clearest over-build in the current codebase
  relative to the locked design.

### F6 — `user_scopes` was not created; scope rides directly on `users.facility_id`
- **Keep as-is, provisionally.** `core/deps.py::get_execution_context` (lines 97-138) reads `facility_id`
  and `driver_id` directly off `public.users`. This works today because v1 personas are single-facility or
  single-driver. `SOLUTION_DESIGN.md` §6.1 specifies a separate `user_scopes` table as "the scoping half of
  RBAC," anticipating multi-scope users (e.g., a facility manager over two facilities, or the deferred
  regional-ops-head persona).
- **Functional requirement mapping**: **M15** ("RBAC with scope… scope is derived from the authenticated
  identity and enforced in the repository layer").
- **Wrong optimisation flag**: Not wrong for current scale — building a generalized many-to-many scope table
  before a single user needs more than one facility would be speculative. Flag as a known simplification to
  revisit if/when a multi-facility ops role is actually needed, not a defect to fix now.

---

## Summary for the reader in a hurry

- **Driver conversation + ETA + allocation-lifecycle-minus-concurrency** are the only modules with real
  depth. Everything else in the 12-module map is either read-only, partial, or entirely unbuilt.
- **The single most important gap is F1**: the correctness mechanism the whole modular-monolith argument in
  `SYSTEM_DESIGN.md` §2 is built around (D1's GiST exclusion constraint) has not been migrated. Phase 1 of
  `TASKS.md` is accurately described as blocking — it is not done, and nothing after it should be treated as
  done either, because several other findings (F2, F3) sit downstream of the same feasibility/allocation code
  Phase 1 touches.
- **The frontend is three routes, not six surfaces** — stated plainly per the task brief, not forced into a
  comparison that doesn't exist yet for gate/yard, carrier portal, admin console, planner board, or shared
  shell.
- **F5 is the one finding that isn't "unfinished" — it's "built the wrong thing."** Everything else here is
  a gap; the dispatch console is effort spent on a capability the locked architecture excludes.
