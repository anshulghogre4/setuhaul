---
title: SetuHaul Implementation Flow
type: topic
status: compiled
scope: delivery
last_verified: 2026-08-14
---

# Implementation

The master plan defines three gated vertical sprints. Owner POC UI for Sprint 1–2 is a **simple two-portal** contract:

| Entry | After login |
|---|---|
| `/driver/login` | Chat (+ light context/quick actions), profile, logout. Chat mounts in Sprint 2 (`DriverHome` → `POST /api/v1/chat`). |
| `/ops/login` | One read-only ops **dashboard** (shipments/exceptions/schedule/docks/rules). Operator facility-scoped and Admin global RO share this shell; JWT decides scope. Logout. |

Prefer shared Driver + Ops Auth accounts. Seeded Operator/Admin may both use `/ops/login`. No maps, GPS, user management, or booking mutations in the POC. Scheduling mutations are Sprint 3 only.

Sprint goals:

1. Trusted walking skeleton: two entry screens, verified role routing, driver profile/logout shell, current-driver context, read-only ops dashboard, and CI baseline. **No chat mount.** **COMPLETE** (exit gate 2026-08-07 17:55 IST).
2. Conversational exception and ETA/status coordination POC: `ChatOpenAI` + `bind_tools` + manual bounded invoke loop, clarification, one atomic typed ETA/exception command path, Redis 24h conversation state, LangSmith traces, and populated read-only Ops dashboard of stored schedule/dock/rule facts. **COMPLETE** (exit gate 2026-08-07 19:35 IST).
3. Deterministic feasibility and concurrency-safe allocation. **COMPLETE** (exit gate 2026-08-12 00:25 IST).
4. Hosting, AgentCore, observability, Locust. **PLANNED** — scoreboard `plans/sprint-4-hosting.md`. Topology: Vercel frontend, App Runner FastAPI **or ECS Express Mode** (same Docker image if App Runner rejects new accounts), Bedrock AgentCore (AWS-only), Supabase + Upstash, CloudWatch + LangSmith, Locust suites A/B. Vercel production tracks `main` (owner lifted the `hosting`-only merge lock 2026-08-14). Exit gate not struck.

Do not build maps, user management, or the optional facility-wide OR-Tools engine before an owner promotion. Sprint 4 application/deploy work follows `plans/sprint-4-hosting.md` on `main`.

The plan is the **cross-IDE Living sprint scoreboard**. Every Cursor/Claude/Codex/Gemini session must report Living status at startup and strike verified checklist items on durable writeback (root `AGENTS.md`).

**Living status (2026-08-07 19:35 IST):** Sprint 1 **COMPLETE**. Sprint 2 **COMPLETE**. Sprint 3 **TODO** (active next).

**Living status refresh (2026-08-11 23:45 IST):** `plans/implementation-master-plan.md` Living Sprint 3 checklist reconciled again. Struck with dated evidence: demo-day 16 Aug dataset + Auth cast, timestamptz ETA fix, Redis summaries/chat restore, cancel/confirm, feasible/NOSLOT API smoke, request/status/race proofs. Exit gate remains OPEN. Remaining vs deferred scoreboard and §13 next actions updated.

**Living status refresh (2026-08-12 00:15 IST):** Sprint 4 **PLANNED** added as §8.1. AgentCore/CloudWatch/Locust hosting promoted from §12 deferred. Sprint 3 remains **IN PROGRESS** / gate OPEN. No hosting code deployed this turn.

**Living status refresh (2026-08-13 23:50 IST):** Sprint 4 Step 1 host-readiness **code complete** (units 77 passed). Deploy/Locust remaining. Gate OPEN.

**Living status refresh (2026-08-14 01:00 IST):** Sprint 4 Step 6 BFF **PASS** (Express Mode `/health/live` 200). Next Step 7 Vercel. Gate OPEN.

**Living status refresh (2026-08-14 00:45 IST):** Sprint 4 Step 5 ECR **PASS** (`setuhaul-api:latest` in `us-east-1`). Next Step 6 BFF. Gate OPEN.

**Living status refresh (2026-08-14 00:28 IST):** Sprint 4 Step 4 SSM + identity **PASS** (8 `/setuhaul/*` names; CDK bootstrap present). Next Step 5 ECR. Gate OPEN.

**Living status refresh (2026-08-14 00:20 IST):** Sprint 4 Step 3 local Docker **PASS** (`setuhaul-api:step1` `:18000` health + chat). Next Step 4 AWS. Gate OPEN.

**Living status refresh (2026-08-14 00:16 IST):** Sprint 4 Step 2 **browser** Driver chat **PASS** (Vite `/driver` → `/api/v1/chat/message` 200). Next Step 3 Docker. Gate OPEN.

**Living status refresh (2026-08-14 00:12 IST):** Sprint 4 Step 2 local smoke **PASS** (ARN blank; Ravi `/chat/message` 200). Next Step 3 Docker. Gate OPEN.

## Challenge brief analysis

Verified against `docs/SetuHaul_FDE_Challenge.pdf` on 2026-08-10: the classroom brief defines the core problem as driver exception chat plus simultaneous scarce dock-capacity coordination. It intentionally does not prescribe agent framework, tool list, storage design, concurrency mechanism, allocation algorithm, or deployment pattern.

The brief's expected demonstration requires: driver delay clarification, later-slot comparison, several requests against the same facility schedule, at least two requests competing for the same capacity, stale/disappearing option handling, and at least one no-feasible-slot escalation. This confirms the master plan's sequencing: Sprint 1-2 POC is valid as an internal ETA/exception/read-model proof, but FDE challenge readiness depends on Sprint 3 feasibility, allocation semantics, idempotent concurrency, conflict recovery, and escalation evidence.

## UI polish

On 2026-08-10, the React frontend was aesthetically tightened without expanding POC scope: the login screens gained role-specific generated hero assets (`frontend/src/assets/setuhaul-driver-eta-hero.png` for Driver and `frontend/src/assets/setuhaul-dock-command-hero.png` for Ops) plus security badges; the driver assistant gained a console header and structured context fields instead of raw JSON; the ops dashboard gained accented metric cards, proportional status bars, compact scope/freshness metadata, a stronger status/exception split, improved empty states, and a better anchored profile menu. The app shell and typography were aligned with the selected Stitch design set. This did not add booking, map/GPS, user-management, or scheduling mutation behavior.

Immediate action: live-smoke authenticated API/chat paths for `find_feasible_slots`, `request_slot`, and `get_appointment_request_status`, then add reschedule/confirm/cancel/reject/expire flows and the no-slot escalation demo.

## Redis Conversation Memory Tool

On 2026-08-10, the Driver LangChain allowlist gained `get_conversation_memory`, backed by `ConversationMemory.snapshot(...)` in `backend/app/services/redis_memory.py`. The tool reads only the authenticated user and current thread's bounded Upstash Redis history/session context, returns 24-hour TTL/degraded-state metadata, and labels the result as non-authoritative.

This is application memory for chat continuity. It must never be treated as PostgreSQL business truth for shipments, ETA, appointments, docks, or facilities. SetuHaul does not use a project Memory MCP; durable project context stays in checked-in docs/source.

On 2026-08-10 23:01 IST, Redis chat memory was tightened to include a browser `session_id` namespace in addition to authenticated `user_id` and `thread_id`. The Driver UI now creates a stable per-tab/browser-session id in `sessionStorage` and sends it to `/api/v1/chat`; `ConversationMemory` normalizes Redis key parts and scopes history, structured session state, and client-message dedupe to `user_id + session_id + thread_id`. This prevents two active sessions that reuse a thread id from reading each other's Redis memory. The session id is not an authorization source; Supabase JWT and server-side profile mapping remain authoritative.

On 2026-08-10 23:24 IST, backend settings were hardened to load gitignored backend/repo `.env` and `.env.local` files through source-relative paths, fixing the local `No LLM API key configured` chat error after a backend restart. Driver chat welcome copy now renders from the verified live driver context so it cannot show a stale auth-profile name while the header shows a different driver.

## Sprint 3 constraints registry

On 2026-08-10, Sprint 3 started with an editable deterministic constraints registry at `backend/app/scheduling/constraints.json`. The file centralizes the project constraints that must shape implementation: PostgreSQL authority, LangChain-only typed orchestration, Redis as 24-hour non-authoritative state, no invented operational data, feasibility hard constraints, deterministic ranking, appointment lifecycle semantics, option invalidation triggers, no-slot escalation payloads, and required write-safety controls.

The registry is loaded through `backend/app/scheduling/constraints.py` using strict Pydantic models. This is a foundation for the pure feasibility engine; it does not yet expose scheduling mutation routes or claim appointment capacity.

## Sprint 3 LangChain slot search

On 2026-08-10, the first end-to-end Sprint 3 LangChain read path was added. `backend/app/scheduling/feasibility.py` loads the constraints registry, verifies trusted user scope, reads latest ETA/facility/slot/dock/active appointment data from PostgreSQL, filters candidate slots, ranks options deterministically, and returns non-reserved options with explanations and snapshot metadata.

`backend/app/api/v1/routers/scheduling.py` exposes `GET /api/v1/shipments/{shipment_id}/slots/feasible`, and `backend/app/assistant/tools.py` registers `find_feasible_slots` in the driver LangChain allowlist. The system prompt permits only lifecycle actions backed by completed transactional services.

On 2026-08-10 20:16 IST, ranking was upgraded from earliest-slot ordering to explicit deterministic scoring. Each feasible option now includes `rank_score` and `ranking_factors` for priority, lateness, wait after ETA, fit slack, dock match, operational disruption score, and stable shipment/slot tie-breaker. The editable weights live in `backend/app/scheduling/constraints.json` under `ranking_policy.priority_scores` and `ranking_policy.score_weights`.

## Sprint 3 Slot Request

On 2026-08-10, `backend/app/scheduling/allocation.py` added `request_slot` as the first transactional scheduling command. It requires an `Idempotency-Key`, verifies the driver owns the shipment, locks shipment and slot rows, checks current active appointments and slot occupancy, reuses the feasibility evaluator, inserts a `PENDING_CONFIRMATION` appointment only after revalidation, writes `BOOK_APPOINTMENT` audit, stores the idempotent response, commits, and rereads the appointment.

The REST route is `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request`, and the Driver LangChain allowlist includes `request_slot` for exact selected slot IDs. This is still not final confirmation; warehouse confirmation is a separate ops/admin transition.

On 2026-08-10, `request_slot` was hardened for residual allocation races. If PostgreSQL rejects an insert through `ux_active_appointment_per_slot` or `ux_current_active_appointment_per_shipment`, the service rolls back, recomputes options, records the 409 idempotency response, and returns `SLOT_CONFLICT_REFRESH_REQUIRED` with zero appointment writes. The HTTP route now returns 409 for this conflict outcome while preserving refreshed options in the response body.

On 2026-08-10 20:35 IST, `backend/tests/integration/test_live_scheduling_concurrency.py` added an opt-in live Supabase proof for two independent async sessions requesting the same temporary slot. The proof verifies exactly one `SLOT_REQUESTED` result, one `SLOT_CONFLICT_REFRESH_REQUIRED` result, one active appointment on the slot, one booking audit row, two idempotency rows, and zero leftover temporary `CODX` rows after cleanup. The test is skipped by default unless `DATABASE_URL` and `SETUHAUL_RUN_LIVE_DB_TESTS=1` are set.

## Sprint 3 Appointment Request Status

On 2026-08-10, `backend/app/scheduling/allocation.py` added `get_appointment_request_status` as a read-only companion to `request_slot`. It verifies trusted driver/operator/admin scope, reads the authoritative appointment request row and recent appointment history from PostgreSQL, maps lifecycle states to stable codes, and explicitly marks `PENDING_CONFIRMATION` as still requiring human/warehouse confirmation.

The REST route is `GET /api/v1/shipments/{shipment_id}/appointment-request/status` with optional `appointment_id`, and the Driver LangChain allowlist includes `get_appointment_request_status`. The tool never mutates appointment state and should be used for “is my requested slot confirmed yet?” questions instead of relying on conversation memory.

## Sprint 3 Cancel and Confirm

On 2026-08-11, `backend/app/scheduling/allocation.py` added strict `CancelAppointmentCommand` and `ConfirmAppointmentCommand` services. Both lock the exact shipment appointment, validate its current state and trusted execution scope, store/replay idempotency responses, write the appointment and audit in one transaction, commit, and return an authoritative reread.

Cancellation accepts the assigned Driver or scoped ops/admin for active `PENDING_CONFIRMATION`, `CONFIRMED`, or `IN_PROGRESS` appointments. It writes `CANCELLED`, `is_current=0`, `cancelled_at`, and `cancellation_reason`; leaving the active-status set releases the slot under the existing partial unique index. The Driver LangChain allowlist now includes `cancel_appointment`, and the prompt requires an explicit reason.

Confirmation is ops/admin REST-only and allows only `PENDING_CONFIRMATION` → `CONFIRMED`, setting `confirmed_at` and `warehouse_confirmation_ref`. Routes are `POST /api/v1/shipments/{shipment_id}/appointments/{appointment_id}/cancel` and `/confirm`, both requiring `Idempotency-Key`. Reschedule/reject/expire remain disabled/incomplete.

## Sprint 3 lifecycle, stale recommendation, and operations takeover

On 2026-08-12, the scheduling service gained reschedule, reject, and expire command paths. Reschedule verifies a fresh policy/recommendation snapshot before replacing an active claim with a new `PENDING_CONFIRMATION` request; reject and expire are scoped operations-only `PENDING_CONFIRMATION` transitions. All routes require `Idempotency-Key`, retain post-commit rereads, and expose stale/conflict refresh results as 409.

Feasibility now carries a stable `REC-` recommendation fingerprint computed from shipment, policy, effective ETA, and ordered displayed slot IDs (or `NOSLOT`). Redis retains an ephemeral, 24-hour recommendation pointer/stale marker; committed ETA writes mark it stale without affecting PostgreSQL write success. `escalation_queue` service/API paths and the Ops dashboard escalation list provide an initial durable human-takeover surface. Focused units and frontend lint/build pass; live migration/API/E2E proof remains required before the Sprint 3 gate can close.

Related: [[current-state]], [[architecture]], [[testing]], [[ai-system]].
