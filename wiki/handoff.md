---
title: SetuHaul Session Handoff
type: handoff
status: authoritative
scope: repository
last_updated: 2026-08-07
---

# Session handoff

## Latest work

- **2026-08-10 19:59 IST:** Added Redis-backed Driver LangChain tool `get_conversation_memory`. `ConversationMemory.snapshot(...)` now returns bounded current-thread Upstash history/session context with 24-hour TTL metadata, non-authoritative labeling, and degraded Redis state. `run_assistant` passes its existing memory instance into the tool builder, and the prompt requires PostgreSQL-backed verification for operational facts. Verified backend unit tests: 40 passed; FastAPI import smoke PASS. Live Upstash smoke not run because Redis env values are not configured/persisted. Coding-agent Memory MCP remains unavailable.
- **2026-08-10 19:50 IST:** Hardened `request_slot` against residual PostgreSQL allocation races. `backend/app/scheduling/allocation.py` now recognizes `ux_active_appointment_per_slot` and `ux_current_active_appointment_per_shipment` `IntegrityError`s, rolls back, recomputes options, stores a 409 idempotency response, and returns `SLOT_CONFLICT_REFRESH_REQUIRED` with zero appointment writes. The scheduling route now returns HTTP 409 for conflict-refresh outcomes. Verified backend unit tests: 38 passed; FastAPI import smoke PASS. Real parallel same-slot contention still not run.
- **2026-08-10 19:38 IST:** Implemented `get_appointment_request_status` as the next Sprint 3 read-only scheduling tool after `request_slot`. Added status/result models and scope-safe SQL reads in `backend/app/scheduling/allocation.py`, exposed `GET /api/v1/shipments/{shipment_id}/appointment-request/status`, and registered Driver LangChain tool `get_appointment_request_status`. It reports pending/confirmed/closed/no-request state with zero appointment writes and keeps pending confirmation distinct from booking confirmation. Verified backend unit tests: 35 passed; FastAPI import smoke PASS. Live authenticated smoke and same-slot concurrency proof not run.
- **2026-08-10 19:31 IST:** Implemented `request_slot` as the first Sprint 3 transactional scheduling command. Added `backend/app/scheduling/allocation.py`, extended `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request`, and registered Driver LangChain tool `request_slot`. The service requires idempotency, row-locks/revalidates shipment and slot state, writes `PENDING_CONFIRMATION`, audit, and idempotency, and returns conflict-safe refreshed options. Verified backend unit tests: 33 passed; FastAPI import smoke PASS. Live authenticated smoke and same-slot concurrency proof not run.
- **2026-08-10 19:12 IST:** Implemented the first Sprint 3 LangChain slot-search path. Added deterministic feasibility service `backend/app/scheduling/feasibility.py`, REST route `GET /api/v1/shipments/{shipment_id}/slots/feasible`, and driver tool registration `find_feasible_slots`. System prompt now allows slot search as non-reserved options while booking/hold/reschedule/cancel/confirm remain disabled. Verified backend unit tests: 30 passed. Live authenticated smoke not run because local env files are absent and pasted secrets were not persisted.
- **2026-08-10 18:55 IST:** Started Sprint 3 with a single editable deterministic scheduling constraints registry at `backend/app/scheduling/constraints.json`, plus typed loader `backend/app/scheduling/constraints.py` and unit tests `backend/tests/unit/test_scheduling_constraints.py`. Sprint 3 status is now IN PROGRESS; exit gate remains open because feasibility engine, mutation tools/routes, and concurrency proof are not built. Verified backend unit tests: 25 passed.
- **2026-08-10 18:29 IST:** Differentiated login hero imagery by portal. Driver login now uses generated `frontend/src/assets/setuhaul-driver-eta-hero.png` with driver ETA/exception copy; Ops login keeps `frontend/src/assets/setuhaul-dock-command-hero.png` with command-center copy. Verified `npm run lint` PASS, `npm run build` PASS, and screenshots `tmp/ui-polish/driver-login-role-hero.png` + `tmp/ui-polish/ops-login-role-hero.png`.
- **2026-08-10 18:22 IST:** Replaced the weak abstract/fake-map login visual with a generated project-local dock-command hero asset at `frontend/src/assets/setuhaul-dock-command-hero.png`; wired it into the login panel with readable overlay text/metrics. Verified `npm run lint` PASS, `npm run build` PASS, and screenshot `tmp/ui-polish/driver-login-dock-hero.png`.
- **2026-08-10 18:12 IST:** Frontend UI polish implemented for login, driver assistant, ops dashboard, typography, and shell layout. Verified `npm run lint` PASS and `npm run build` PASS. Screenshots captured for `/driver/login` desktop and `/ops/login` mobile under `tmp/ui-polish/`. Protected authenticated screens not live-smoked because local env files are absent and pasted secrets were not persisted. User pasted live secrets in chat; rotate after POC.
- **2026-08-10 17:51 IST:** Analyzed `docs/SetuHaul_FDE_Challenge.pdf` (20 pages). Finding: brief is intentionally open-ended but challenge readiness requires Sprint 3 proof of feasibility, allocation semantics, same-slot concurrency, stale-option recovery, and no-slot escalation. Memory MCP unavailable in this Codex session; checked-in context updated.

- **2026-08-08 13:45 IST:** Renamed `web/` → `frontend/`; CI/README/gitignore/package name updated; `npm run build` PASS.
- **2026-08-08 13:35 IST:** Added `GET /` root alive health ping (no more 404 on `:8000/`). README note; `/health/live` + `/health/ready` unchanged.
- **2026-08-07 20:25 IST:** Gemini live **PASS** with `ChatGoogleGenerativeAI` + default `gemini-2.5-flash` (2.0 retired). OpenAI + OpenRouter + Gemini all live-verified.
- **2026-08-07 20:20 IST:** Provider smoke + Gemini native LangChain class (Gemini blocked until real Google key + model bump).
- **2026-08-07 20:00 IST:** README team Quick start + multi-provider LLM factory shipped.
- **2026-08-07 19:35 IST:** Sprint 2 exit gate **COMPLETE**.
- **2026-08-07 17:55 IST:** Sprint 1 exit gate COMPLETE.

## Current state

See [[current-state]]. Sprint 2 complete. Sprint 3 deterministic allocation is IN PROGRESS with constraints registry, `find_feasible_slots`, `request_slot`, `get_appointment_request_status`, allocation unique-index race mapping, and Redis memory tool context in place. **OpenAI + OpenRouter + Gemini live invoke verified.**

## Decisions and blockers

- Product AI: `ChatOpenAI.bind_tools` for OpenAI/OpenRouter; **`ChatGoogleGenerativeAI`** for Gemini; same bind_tools manual loop. Default Gemini model **`gemini-2.5-flash`**.
- JWT verify uses `leeway=300` for local clock skew vs Supabase `iat`.
- **Security:** keys pasted in chat → rotate after POC; never commit. README emails only; passwords OOB.
- Sprint 3 constraints are centralized in `backend/app/scheduling/constraints.json`; change this file when policy wording changes, then keep deterministic services/tests aligned.
- `find_feasible_slots` may show explainable non-reserved options. Appointment writes still require future transactional allocation services and concurrency proof.
- `request_slot` may create `PENDING_CONFIRMATION` after exact slot selection and transactional revalidation. It is not a confirmed booking; same-slot race proof remains pending.
- `get_appointment_request_status` may answer pending/confirmed/closed/no-request status from PostgreSQL with zero appointment writes; use it instead of inferring confirmation from chat history.
- If a residual race reaches PostgreSQL, `request_slot` now maps the existing allocation partial unique indexes to a conflict refresh. This is not a substitute for running real parallel contention tests.
- `get_conversation_memory` reads only current authenticated user/thread Redis memory and labels it non-authoritative; use it for chat continuity only, never as business truth.

## Verification

- Role-specific login heroes: generated `frontend/src/assets/setuhaul-driver-eta-hero.png`, reused `frontend/src/assets/setuhaul-dock-command-hero.png` for Ops, `npm run lint` PASS, `npm run build` PASS, screenshots visually spot-checked.
- Backend scheduling/LangChain allocation/memory path: `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/` PASS: 40 passed, 1 pytest config warning (`asyncio_mode` unknown without `pytest-asyncio` in ephemeral env). FastAPI import smoke PASS with 11 routes.
- Login hero refinement: generated image asset copied into `frontend/src/assets/setuhaul-dock-command-hero.png`; `npm run lint` PASS; `npm run build` PASS; screenshot `tmp/ui-polish/driver-login-dock-hero.png` visually spot-checked.
- Frontend UI: `npm run lint` PASS; `npm run build` PASS; Vite running on `http://127.0.0.1:5173`; unauthenticated login screenshots visually spot-checked. Authenticated driver/ops data screens not smoke-tested this turn because `.env`/`.env.local` files are absent and chat-pasted secrets were not written to disk.
- PDF analysis: text extracted from all 20 pages with `pdfplumber`; representative pages 1, 10, and 18 rendered with Poppler and visually spot-checked. No application tests run because this was document analysis only.

- Unit: **20 passed**.
- Live invoke: OpenAI PASS; OpenRouter PASS; Gemini PASS (`gemini-2.5-flash`).
- Memory MCP: unavailable in the 2026-08-10 Codex session; checked-in wiki/changelog updated and memory replay remains pending when available.

## Next action

1. Live-smoke `find_feasible_slots`, `request_slot`, `get_appointment_request_status`, and `get_conversation_memory` once local env is provided without committing secrets.
2. Add real same-slot contention tests proving one `request_slot` winner and refreshed conflict response for losers.
3. Add reschedule/confirm/cancel services after request-slot race proof.
4. Optionally rotate chat-pasted API keys after POC sharing risk review.


Related: [[current-state]], [[implementation]], [[ai-system]], [[testing]].
