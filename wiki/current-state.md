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
- Owner clarified on 2026-08-10 22:20 IST: there is no project Memory MCP for SetuHaul. Redis is the only memory layer, and it is application runtime conversation/session memory only.
- Frontend UI polish landed 2026-08-10: premium two-portal login surface with role-specific generated Driver ETA and Ops dock-command hero assets, composed driver context rail, denser ops dashboard metrics/status bars, Inter body font, hook-dependency cleanup, and a later authenticated ops dashboard refinement for cleaner scope/freshness metadata, status/exception layout, empty states, and profile menu anchoring. Verified with `npm run lint`, `npm run build`, unauthenticated login screenshots, and live Arvind Nair ops API checks.
- Sprint 3 has started with a deterministic scheduling constraints registry: `backend/app/scheduling/constraints.json` is the single editable policy source for authority boundaries, feasibility hard constraints, ranking policy, lifecycle meanings, Redis limits, no-slot escalation, and write-safety requirements. `backend/app/scheduling/constraints.py` validates/loads it for backend services. Verified 2026-08-10 18:55 IST with backend unit tests.
- Sprint 3 LangChain read path started: `backend/app/scheduling/feasibility.py` implements the first `find_feasible_slots` service, `backend/app/api/v1/routers/scheduling.py` exposes `GET /api/v1/shipments/{shipment_id}/slots/feasible`, and `backend/app/assistant/tools.py` registers the `find_feasible_slots` tool while appointment mutation intents still route to `CAPABILITY_NOT_ENABLED`. The feasibility service now returns explicit deterministic ranking scores/factors driven by editable weights in `backend/app/scheduling/constraints.json`. Verified 2026-08-10 20:16 IST with backend unit tests and FastAPI import smoke.
- Sprint 3 transactional request path started: `backend/app/scheduling/allocation.py` implements `request_slot`, which requires idempotency, locks/revalidates shipment and slot state, inserts `PENDING_CONFIRMATION` appointments, writes audit logs, and returns conflict-safe refreshed options. `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request` and the Driver LangChain `request_slot` tool are wired. Verified 2026-08-10 19:31 IST with backend unit tests and FastAPI import smoke.
- Sprint 3 appointment request status read path started: `backend/app/scheduling/allocation.py` implements `get_appointment_request_status`, `GET /api/v1/shipments/{shipment_id}/appointment-request/status` exposes it, and Driver LangChain tool `get_appointment_request_status` reports pending/confirmed/closed/no-request lifecycle state without mutating appointments. Verified 2026-08-10 19:38 IST with backend unit tests and FastAPI import smoke.
- Sprint 3 allocation race handling is hardened and live same-slot contention is now proved: `request_slot` recognizes PostgreSQL allocation conflicts, returns conflict-safe refreshed options, and surfaces HTTP 409 from the route. Verified 2026-08-10 20:35 IST with `backend/tests/integration/test_live_scheduling_concurrency.py`: two independent async sessions competing for one temporary live Supabase slot produced exactly one `SLOT_REQUESTED` winner and one `SLOT_CONFLICT_REFRESH_REQUIRED` loser, with one active appointment and zero leftover `CODX` rows after cleanup.
- `plans/implementation-master-plan.md` was reconciled on 2026-08-10 22:46 IST from the beginning through the latest UI/auth/Redis/Gemini/scheduling work. Completed items are struck with evidence, and remaining Sprint 3 next/deferred work is ordered explicitly.
- Live Supabase database catalog inspection PASS on 2026-08-10 20:23 IST via read-only asyncpg: PostgreSQL 17.6, `auth.users=3`, public schema has 23 tables and 4 views, and seeded Sprint 3 operational data is present (`shipments=21`, `appointment_slots=106`, `appointments=22`, `driver_exceptions=12`). Scheduling guard indexes are present.
- Live POC Auth account pool expanded on 2026-08-10 22:11 IST: extra Driver users `USR002`/`USR003`, Operations Executive users `USR107`/`USR108`, and Admin users `USR997`/`USR998` are mapped to Supabase Auth and password-grant verified. Auth now has the original 3 POC accounts plus these 6 extra accounts.
- Application Redis memory tool added: Driver LangChain allowlist now includes `get_conversation_memory`, backed by `ConversationMemory.snapshot(...)`, returning bounded current-thread Upstash session/history context with explicit 24-hour TTL, degraded state, and non-authoritative labeling. Verified 2026-08-10 19:59 IST with backend unit tests and FastAPI import smoke; live Upstash Redis smoke later passed on 2026-08-10 22:11 IST after local env was configured.
- Multi-provider LLM: OpenAI + OpenRouter + Gemini live invoke **PASS** (2026-08-07 20:25 IST). Gemini = `ChatGoogleGenerativeAI`; current default is `gemini-flash-latest`, and direct REST smoke with the local Gemini key PASS on 2026-08-10.
- Default backend tests: **41 passed, 1 live integration skipped**. Explicit live same-slot integration: **1 passed**.

## Verify before claiming

- Formal Playwright suite in CI (local one-shot smoke only).
- LangSmith UI trace inspection (env tracing enabled; UI not opened this session).
- Live LangChain Gemini invoke with current key/model after backend/dev environment restart. Direct Gemini REST smoke passed, but `ChatGoogleGenerativeAI.invoke` timed out in the local shell.
- Sprint 3 reschedule/confirm/cancel/reject/expire tools, live authenticated API/chat scheduling smoke, broader load tests, and no-slot escalation demo remain incomplete.
- Enterprise hardening remains incomplete: session revocation, password rotation, disabled-user handling, stale-role-claim handling, formal Playwright/responsive/a11y/CI coverage, and production credential rotation.

Related: [[implementation]], [[testing]], [[handoff]], [[ai-system]], [[database]].
