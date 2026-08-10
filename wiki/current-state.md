---
title: SetuHaul Current Verified State
type: state
status: authoritative
scope: repository
last_verified: 2026-08-10
---

# Current state

## Verified

- Sprint 1 exit gate COMPLETE (2026-08-07 17:55 IST).
- **Sprint 2 exit gate COMPLETE (2026-08-07 19:35 IST).**
- Challenge brief re-analyzed from `docs/SetuHaul_FDE_Challenge.pdf` on 2026-08-10; it reinforces Sprint 3 as the FDE challenge-ready gate for deterministic feasibility, scarce-capacity allocation, stale option handling, same-slot competition, and safe no-slot escalation.
- React 19 `frontend/` (renamed from `web/` 2026-08-08) + FastAPI + Supabase PG SoT + Upstash 24h chat memory + LangChain `ChatOpenAI.bind_tools` manual loop.
- Frontend UI polish landed 2026-08-10: premium two-portal login surface with role-specific generated Driver ETA and Ops dock-command hero assets, composed driver context rail, denser ops dashboard metrics/status bars, Inter body font, and hook-dependency cleanup. Verified with `npm run lint`, `npm run build`, and unauthenticated login screenshots.
- Sprint 3 has started with a deterministic scheduling constraints registry: `backend/app/scheduling/constraints.json` is the single editable policy source for authority boundaries, feasibility hard constraints, ranking policy, lifecycle meanings, Redis limits, no-slot escalation, and write-safety requirements. `backend/app/scheduling/constraints.py` validates/loads it for backend services. Verified 2026-08-10 18:55 IST with backend unit tests.
- Sprint 3 LangChain read path started: `backend/app/scheduling/feasibility.py` implements the first `find_feasible_slots` service, `backend/app/api/v1/routers/scheduling.py` exposes `GET /api/v1/shipments/{shipment_id}/slots/feasible`, and `backend/app/assistant/tools.py` registers the `find_feasible_slots` tool while appointment mutation intents still route to `CAPABILITY_NOT_ENABLED`. The feasibility service now returns explicit deterministic ranking scores/factors driven by editable weights in `backend/app/scheduling/constraints.json`. Verified 2026-08-10 20:16 IST with backend unit tests and FastAPI import smoke.
- Sprint 3 transactional request path started: `backend/app/scheduling/allocation.py` implements `request_slot`, which requires idempotency, locks/revalidates shipment and slot state, inserts `PENDING_CONFIRMATION` appointments, writes audit logs, and returns conflict-safe refreshed options. `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request` and the Driver LangChain `request_slot` tool are wired. Verified 2026-08-10 19:31 IST with backend unit tests and FastAPI import smoke.
- Sprint 3 appointment request status read path started: `backend/app/scheduling/allocation.py` implements `get_appointment_request_status`, `GET /api/v1/shipments/{shipment_id}/appointment-request/status` exposes it, and Driver LangChain tool `get_appointment_request_status` reports pending/confirmed/closed/no-request lifecycle state without mutating appointments. Verified 2026-08-10 19:38 IST with backend unit tests and FastAPI import smoke.
- Sprint 3 allocation race handling is hardened: `request_slot` now recognizes the existing PostgreSQL partial unique indexes `ux_active_appointment_per_slot` and `ux_current_active_appointment_per_shipment` if a residual race reaches the database, rolls back, returns conflict-safe refreshed options, and surfaces HTTP 409 from the route. Verified 2026-08-10 19:50 IST with backend unit tests and FastAPI import smoke; live parallel contention remains unverified.
- Live Supabase database catalog inspection PASS on 2026-08-10 20:23 IST via read-only asyncpg: PostgreSQL 17.6, `auth.users=3`, public schema has 23 tables and 4 views, and seeded Sprint 3 operational data is present (`shipments=21`, `appointment_slots=106`, `appointments=22`, `driver_exceptions=12`). Scheduling guard indexes are present; live same-slot concurrency proof remains unverified.
- Application Redis memory tool added: Driver LangChain allowlist now includes `get_conversation_memory`, backed by `ConversationMemory.snapshot(...)`, returning bounded current-thread Upstash session/history context with explicit 24-hour TTL, degraded state, and non-authoritative labeling. Verified 2026-08-10 19:59 IST with backend unit tests and FastAPI import smoke; live Upstash smoke not run because Redis env values are not configured/persisted.
- Multi-provider LLM: OpenAI + OpenRouter + Gemini live invoke **PASS** (2026-08-07 20:25 IST). Gemini = `ChatGoogleGenerativeAI` default `gemini-2.5-flash`.
- Unit tests: **41 passed**.

## Verify before claiming

- Formal Playwright suite in CI (local one-shot smoke only).
- LangSmith UI trace inspection (env tracing enabled; UI not opened this session).
- Live chat with OpenRouter or Gemini (keys not set locally as of 20:00 IST).
- Sprint 3 reschedule/confirm/cancel/reject/expire tools, live authenticated scheduling smoke, and real same-slot concurrency tests remain incomplete.

Related: [[implementation]], [[testing]], [[handoff]], [[ai-system]], [[database]].
