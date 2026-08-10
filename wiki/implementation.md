---
title: SetuHaul Implementation Flow
type: topic
status: compiled
scope: delivery
last_verified: 2026-08-07
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
3. Deterministic feasibility and concurrency-safe allocation. **IN PROGRESS** — started after Sprint 2 gate; exit gate remains open.

Do not build maps, user management, booking mutations, or the full chatbot tool catalogue before the active exit gate passes.

The plan is the **cross-IDE Living sprint scoreboard**. Every Cursor/Claude/Codex/Gemini session must report Living status at startup and strike verified checklist items on durable writeback (root `AGENTS.md`).

**Living status (2026-08-07 19:35 IST):** Sprint 1 **COMPLETE**. Sprint 2 **COMPLETE**. Sprint 3 **TODO** (active next).

**Living status refresh (2026-08-10 19:50 IST):** `request_slot` is implemented as the first Sprint 3 transactional pending-confirmation path after `find_feasible_slots`, `get_appointment_request_status` reports authoritative pending/confirmed/closed/no-request lifecycle state, and allocation unique-index races now map to HTTP 409 conflict refresh. No Sprint 3 exit gate item was struck; live authenticated smoke, real same-slot concurrency proof, and reschedule/confirm/cancel/reject/expire flows remain TODO.

## Challenge brief analysis

Verified against `docs/SetuHaul_FDE_Challenge.pdf` on 2026-08-10: the classroom brief defines the core problem as driver exception chat plus simultaneous scarce dock-capacity coordination. It intentionally does not prescribe agent framework, tool list, storage design, concurrency mechanism, allocation algorithm, or deployment pattern.

The brief's expected demonstration requires: driver delay clarification, later-slot comparison, several requests against the same facility schedule, at least two requests competing for the same capacity, stale/disappearing option handling, and at least one no-feasible-slot escalation. This confirms the master plan's sequencing: Sprint 1-2 POC is valid as an internal ETA/exception/read-model proof, but FDE challenge readiness depends on Sprint 3 feasibility, allocation semantics, idempotent concurrency, conflict recovery, and escalation evidence.

## UI polish

On 2026-08-10, the React frontend was aesthetically tightened without expanding POC scope: the login screens gained role-specific generated hero assets (`frontend/src/assets/setuhaul-driver-eta-hero.png` for Driver and `frontend/src/assets/setuhaul-dock-command-hero.png` for Ops) plus security badges; the driver assistant gained a console header and structured context fields instead of raw JSON; the ops dashboard gained accented metric cards and proportional status bars; the app shell and typography were aligned with the selected Stitch design set. This did not add booking, map/GPS, user-management, or scheduling mutation behavior.

Immediate action: live-smoke `find_feasible_slots`, `request_slot`, and `get_appointment_request_status`, then add same-slot concurrency tests and the reschedule/confirm/cancel flows.

## Redis Conversation Memory Tool

On 2026-08-10, the Driver LangChain allowlist gained `get_conversation_memory`, backed by `ConversationMemory.snapshot(...)` in `backend/app/services/redis_memory.py`. The tool reads only the authenticated user and current thread's bounded Upstash Redis history/session context, returns 24-hour TTL/degraded-state metadata, and labels the result as non-authoritative.

This is application memory for chat continuity. It does not replace the coding-agent Memory MCP and must never be treated as PostgreSQL business truth for shipments, ETA, appointments, docks, or facilities.

## Sprint 3 constraints registry

On 2026-08-10, Sprint 3 started with an editable deterministic constraints registry at `backend/app/scheduling/constraints.json`. The file centralizes the project constraints that must shape implementation: PostgreSQL authority, LangChain-only typed orchestration, Redis as 24-hour non-authoritative state, no invented operational data, feasibility hard constraints, deterministic ranking, appointment lifecycle semantics, option invalidation triggers, no-slot escalation payloads, and required write-safety controls.

The registry is loaded through `backend/app/scheduling/constraints.py` using strict Pydantic models. This is a foundation for the pure feasibility engine; it does not yet expose scheduling mutation routes or claim appointment capacity.

## Sprint 3 LangChain slot search

On 2026-08-10, the first end-to-end Sprint 3 LangChain read path was added. `backend/app/scheduling/feasibility.py` loads the constraints registry, verifies trusted user scope, reads latest ETA/facility/slot/dock/active appointment data from PostgreSQL, filters candidate slots, ranks options deterministically, and returns non-reserved options with explanations and snapshot metadata.

`backend/app/api/v1/routers/scheduling.py` exposes `GET /api/v1/shipments/{shipment_id}/slots/feasible`, and `backend/app/assistant/tools.py` registers `find_feasible_slots` in the driver LangChain allowlist. The system prompt now allows slot search but still forbids booking, holding, rescheduling, cancellation, or confirmation until transactional allocation services exist.

## Sprint 3 Slot Request

On 2026-08-10, `backend/app/scheduling/allocation.py` added `request_slot` as the first transactional scheduling command. It requires an `Idempotency-Key`, verifies the driver owns the shipment, locks shipment and slot rows, checks current active appointments and slot occupancy, reuses the feasibility evaluator, inserts a `PENDING_CONFIRMATION` appointment only after revalidation, writes `BOOK_APPOINTMENT` audit, stores the idempotent response, commits, and rereads the appointment.

The REST route is `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request`, and the Driver LangChain allowlist includes `request_slot` for exact selected slot IDs. This is still not final confirmation; reschedule, cancellation, and confirmation remain separate TODO flows.

On 2026-08-10, `request_slot` was hardened for residual allocation races. If PostgreSQL rejects an insert through `ux_active_appointment_per_slot` or `ux_current_active_appointment_per_shipment`, the service rolls back, recomputes options, records the 409 idempotency response, and returns `SLOT_CONFLICT_REFRESH_REQUIRED` with zero appointment writes. The HTTP route now returns 409 for this conflict outcome while preserving refreshed options in the response body.

## Sprint 3 Appointment Request Status

On 2026-08-10, `backend/app/scheduling/allocation.py` added `get_appointment_request_status` as a read-only companion to `request_slot`. It verifies trusted driver/operator/admin scope, reads the authoritative appointment request row and recent appointment history from PostgreSQL, maps lifecycle states to stable codes, and explicitly marks `PENDING_CONFIRMATION` as still requiring human/warehouse confirmation.

The REST route is `GET /api/v1/shipments/{shipment_id}/appointment-request/status` with optional `appointment_id`, and the Driver LangChain allowlist includes `get_appointment_request_status`. The tool never mutates appointment state and should be used for “is my requested slot confirmed yet?” questions instead of relying on conversation memory.

Related: [[current-state]], [[architecture]], [[testing]], [[ai-system]].
