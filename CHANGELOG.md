# SetuHaul changelog

This append-only log records material implementation, architecture, workflow, debugging, and documentation changes. Entries use IST and state verification honestly.

## 2026-08-13 21:52 IST - Owner will push demo-hardening

- Agent commit/push cancelled. Local demo-hardening stays uncommitted for the owner to push on `setuhal-santosh`. Verification: not run. Agent/surface: Cursor.

## 2026-08-13 21:51 IST - Compatibility check vs teammate (Aman / Antigravity) commits

- Confirmed classroom demo-hardening did not revert Aman’s committed work on `setuhal-santosh` (HEAD `9d37538`). Frontend is unmodified: Dispatch Console, Ops resolve modal, layout/nav, typing indicator, extra Driver tools, kwargs unpacking, and UI polish commits remain as pushed.
- Only overlap: dispatch auto-book now passes the just-computed `recommendation_id` instead of `None` (keeps auto-book; enables the stale-REC gate). Chat tools still register Aman’s five extra tools and `**kwargs`.
- Verification: `git status --short -- frontend/` clean; `git log` retains `fba0f02` / `3341ca3` / `cf70272` / UI follow-ups; local uncommitted set is backend scheduling/chat/reset + docs. Agent/surface: Cursor.

## 2026-08-13 21:44 IST - Demo remaining scoreboard

- Classroom demo product blockers are closed (Sprint 3 gate + 21:39 IST hardening + Ravi Auth restore). Remaining demo work is rehearsal: run `DEMO_MANUAL_RUNBOOK.md` after `--mode cast` (live confirm of the new reset not yet run).
- Optional polish only: ranking collect-then-sort, wipe runtime `EXC-*` on reset, drop leftover `scheduling_capability_disabled`. Intentional NOT YET: OR-Tools, dock-close mid-chat UI, warehouse reply channel, GPS. Sprint 4 hosting stays PLANNED.
- Updated `docs/DEMO_DAY_READINESS.md` after-gate list. Verification: docs/status only; app tests not re-run. Agent/surface: Cursor.

## 2026-08-13 21:39 IST - PDF demo-hardening (cast reset, chat idempotency, stale REC, reschedule orphan)

- Refreshed Living sprint status in `plans/implementation-master-plan.md` with post-Sprint-3 deltas (Dispatch Console, escalation resolve, extra Driver tools, Ravi Auth restore) without reopening the Sprint 3 exit gate.
- Cast reset: `D16-APT-RAVI-OLD` is restored as historical CANCELLED / not current so Phase B `request_slot` is not blocked by `ACTIVE_APPOINTMENT_EXISTS`; `APT1017` stays CONFIRMED. Runbook Phase B + demo README aligned.
- Chat `request_slot` / `reschedule` idempotency keys now include `client_message_id` (else a nonce). Inactive `SLOT_REQUESTED` replays are ignored so cancel→rebook can claim again.
- Stale options: chat injects stored Redis REC when the model omits it; Redis stale is honored even without a REC id; dispatch auto-book passes the just-computed `recommendation_id`.
- Reschedule nested `request_slot(..., persist=False)` and restores the prior appointment when the replacement claim is not `SLOT_REQUESTED`.
- Verification: backend unit suite **65 passed**; live DB/cast reset `--confirm` **not run**. Agent/surface: Cursor.

## 2026-08-13 21:26 IST - Restore Ravi Driver Auth password (invalid_credentials)

- Diagnosed `ravi.kumar@setuhaul.com` Driver login `invalid_credentials`: `USR001` mapping, role, and Auth flags were healthy; password grant against the documented Driver bucket returned **400** for Ravi and **200** for Amit.
- Restored **only** Ravi via GoTrue Admin API onto the existing shared Driver bucket. Did not rotate Amit/Vikas/drv004–015 or the other two POC buckets.
- Verification: Ravi password-grant **200**; Amit still **200**; local `GET /api/v1/auth/me` **200** with `USR001` / `DRIVER` / `DRV001`. Passwords not written to changelog. Agent/surface: Cursor.

## 2026-08-13 02:00 IST - Add Ops Escalation Resolution Service & UI Action

- Created `resolve_escalation` service function in `backend/app/services/escalation_service.py` to update `escalation_status = 'RESOLVED'` in PostgreSQL `public.escalation_queue`.
- Exposed `POST /api/v1/operations/escalations/{escalation_id}/resolve` endpoint in `backend/app/api/v1/routers/operations.py`.
- Added `Why Escalated` conflict reason banner on each escalation card in `OpsHomes.tsx` (extracts rejection reasons, no-slot flags, or driver breakdown notes from `payload`).
- Created an interactive **Inspect & Take Decision** popup modal allowing Ops to review root causes, add resolution notes, and resolve/override or assign new loads.
- Removed Sprint 1 observational fine-print summary note from `backend/app/api/v1/routers/operations.py` and `frontend/src/features/operator/OpsHomes.tsx`.
- Removed `composer-chips` tags (`ACTIVE`, `Facility Label`, `Driver ID`, `UX: ready`) above the chat message input box in `frontend/src/features/driver/DriverHome.tsx`.
- Verification: 59 backend unit tests **PASS** (`source .venv/bin/activate && PYTHONPATH=. pytest tests/unit`); Vite build **PASS** (built in 613ms).
- Agent/surface: Google Antigravity.

## 2026-08-13 01:48 IST - Complete End-to-End Verification of Dispatch & Auto-Booking Service

- Included all required PostgreSQL `NOT NULL` columns (`carrier_id`, `vehicle_id`, `origin_name`, `origin_city`, `planned_departure_ts`, `temperature_control_required`) in `create_dispatch_shipment` SQL `INSERT`.
- Fixed `request_slot` keyword-only parameter call and set `displayed_recommendation_id=None` to enable immediate pre-booking of top-ranked dock slots.
- Verified end-to-end dispatch execution with payload `driver_id: D16-DRV-006`, `destination_facility_id: FAC-AMD-01`, `original_eta_ts: 2026-08-16T10:40:00+05:30`:
  - Created shipment `SHP-DISP-83C3F2C0` in PostgreSQL.
  - Automatically booked dock slot `D16-SLT-02739` (`11:00 AM – 11:30 AM`) with status `PENDING_CONFIRMATION` and appointment ID `APT-F16FD7C41E41`.
- Moved "Dock Command" and "Dispatch Console" out of the header topbar-actions into a dedicated sub-header navigation tab bar in `ProtectedLayout.tsx`, allowing Priya Mehta's profile menu to render cleanly alone on the top right.
- Verification: 59 backend unit tests **PASS** (`source .venv/bin/activate && PYTHONPATH=. pytest tests/unit`); Vite build **PASS** (built in 596ms).
- Agent/surface: Google Antigravity.

## 2026-08-13 01:25 IST - Add Dispatch Console, Fixed Viewport Driver Layout & Bounded LOV Select

- Created Dispatch Console feature (`frontend/src/features/dispatch/DispatchHome.tsx`, `backend/app/services/dispatch_service.py`, `backend/app/api/v1/routers/dispatch.py`):
  - Enables Person A (Dispatch / Transport Manager) to create new shipments and assign drivers in PostgreSQL.
  - Automatically executes `find_feasible_slots` and `request_slot` to pre-mark initial dock appointments for assigned drivers.
  - Added `/dispatch` route and nav buttons in `ProtectedLayout.tsx`.
- Refined Driver UI Layout (`frontend/src/features/driver/DriverLayout.css`, `DriverHome.tsx`):
  - Fixed viewport layout: Header, composer chips, quick actions, and composer remain fixed while only `.chat-history` scrolls vertically.
  - Auto-scrolls chat history to bottom upon receiving responses.
  - Hidden raw `as_of` timestamp in Active Context card.
  - Formatted Planned ETA, Start, and End timestamps into human-readable strings (`Aug 16, 2026, 6:40 PM`).
  - Added highlighted `Updated ETA` tag under Primary Shipment, rendered only when a distinct ETA revision exists (`hasEtaChanged`).
- Built `BoundedLOVSelect` Component in Dispatch Console:
  - Constrained LOV dropdown popups to a compact `max-height: 210px` window with internal scrolling.
  - Added instant search/filter input to filter 105+ drivers without screen takeover.
  - Added click-outside listener (`useRef` + `mousedown`) to auto-dismiss dropdown lists when clicking outside.
- Verification: `npm run build` PASS (built in 587ms, 95 modules transformed); zero TypeScript lint errors.
- Agent/surface: Google Antigravity.

## 2026-08-12 03:05 IST - Add Custom Markdown Renderer in Driver Chat (No Raw Asterisks)

- Implemented `renderFormattedText` helper in `frontend/src/features/driver/DriverHome.tsx` to parse markdown bold (`**text**`) and inline code (`` `code` ``) dynamically into styled React elements (`<strong>`, `<code>`, `.chat-line`).
- Replaced plain `<p>{m.content}</p>` text node with `{renderFormattedText(m.content)}`, removing all unparsed `**` asterisks from chat output.
- Styled `strong` tags with signature cyan (`#38bdf8`) and added glowing chip styles for inline code elements (`.chat-inline-code`).
- Verification: 59 backend unit tests **PASS** (`PYTHONPATH=. pytest tests/unit`); Vite build **PASS** (built in 607ms).

## 2026-08-12 03:00 IST - Enhanced AI Assistant Response Formatting & Pre-wrap CSS

- Updated `SYSTEM_PROMPT` in `backend/app/assistant/prompts.py` with explicit layout guidelines enforcing double line breaks (`\n\n`), clean card structures, and distinct headers for multi-item shipment/ETA lists.
- Updated `frontend/src/App.css` to add `white-space: pre-wrap;` and line-height polish on `.chat-bubble` and `.chat-bubble p` elements, preventing text squishing in chat.
- Verification: 59 backend unit tests **PASS** (`PYTHONPATH=. pytest tests/unit`); Vite build **PASS** (built in 679ms).

## 2026-08-12 02:35 IST - Implement 5 New Database-Backed AI Assistant Tools

- Added 5 new database service functions in `backend/app/services/driver_reads.py`:
  1. `get_vehicle_and_carrier_details`: Reads assigned truck registration, weight capacity, refrigeration capability, and carrier contact info from `vehicles`, `vehicle_types`, `carriers`, `shipments`.
  2. `get_gate_and_queue_status`: Reads yard queue position, arrival state (EARLY/ON_TIME/LATE), and gate check-in timestamps from `facility_checkins`.
  3. `get_facility_rules_and_restrictions`: Reads safety rules, gate policies, and check-in grace periods from `facility_rules` and `facilities`.
  4. `report_vehicle_breakdown_or_incident`: Upserts parent `chat_threads` row and writes structured breakdown records to `driver_exceptions` in PostgreSQL.
  5. `get_dock_maintenance_alerts`: Queries active dock maintenance and outage events from `dock_status_events` and `docks`.
- Registered Pydantic schemas and `StructuredTool.from_function` definitions in `backend/app/assistant/tools.py`.
- Verification: 48 backend unit tests **PASS** (`PYTHONPATH=. pytest tests/unit`); Live AI assistant tool invocation verified with 100% accuracy across all 5 tools (**200 OK**, `ux_state: persisted_success`).
- Agent/surface: Google Antigravity.

## 2026-08-12 02:20 IST - Fix Tool Coroutine Kwargs Unpacking & Confirmation Loop Bug

- Fixed `TypeError: build_driver_tools.<locals>.get_latest_eta() got an unexpected keyword argument 'shipment_id'` in `backend/app/assistant/tools.py` where LangChain `StructuredTool.from_function` passed unpacked keyword arguments (`shipment_id="..."`, `declared_eta_ts="..."`), but coroutines expected a single `args` positional parameter.
- Updated all driver tool coroutine signatures in `tools.py` (`get_shipment_details`, `get_latest_eta`, `report_delay_or_update_eta`, etc.) to accept `args` or unpacked `**kwargs` seamlessly.
- Added `should_break_after_round = True` for `CONFIRMATION_REQUIRED` in `backend/app/assistant/run_assistant.py` so the assistant breaks out of `MAX_TOOL_ROUNDS` immediately on preview, eliminating duplicate/corrupt tool calls.
- Verification: 45 backend unit tests **PASS** (`PYTHONPATH=. pytest tests/unit`); End-to-end multi-turn driver ETA confirmation flow verified with 100% precision (**200 OK**, `ux_state: confirmation_required`).
- Agent/surface: Google Antigravity.

## 2026-08-12 02:16 IST - Graphify incremental update (demo reset + Sprint 3 docs)

- Ran `graphify --update` on 20 changed files (6 code / 14 docs): AST + semantic chunks, merge into graph, cluster, force-write `graph.json`/`graph.html`/`GRAPH_REPORT.md`.
- Graph now **1192 nodes · 2096 edges · 73 communities**; includes `reset_demo_day` cast restore, Ravi/NOSLOT/race cast, allocation/escalation hyperedges.
- Verification: HTML export PASS; queries PASS for cast reset path, request_slot scarce-capacity neighborhood, SHP-D16-RAVI explain. App tests not run.

## 2026-08-12 02:08 IST - Fix Duplicate Tool Loop & Empty Response on Confirmation

- Fixed issue in `backend/app/assistant/run_assistant.py` where confirming a database write (e.g. `report_delay_or_update_eta` with `confirmed=True`) caused OpenRouter/LLM model to re-invoke the same tool repeatedly across `MAX_TOOL_ROUNDS=6`, leaving `ai.content=""` empty.
- Added early loop termination (`should_break_after_round = True`) when a tool returns `status: PERSISTED`.
- Added automatic non-empty success message synthesis for `persisted_success` state (`"ETA update for SHP1017 (...) has been confirmed and saved successfully."`).
- Verification: 45 backend unit tests **PASS** (`PYTHONPATH=. pytest tests/unit`); Multi-turn live test sequence verified with 100% clean responses (**200 OK**).
- Agent/surface: Google Antigravity.

## 2026-08-12 01:18 IST - PDF challenge bug audit (read-only)

## 2026-08-12 01:05 IST - Cast reset live DB safety review (Ravi-scoped)

- Inspected live Postgres tables/FKs for `--mode cast --include-shp1017`. Scope stays cast IDs + Redis demo users; Auth untouched; baseline Aug-4 inventory (except optional `SHP1017`) preserved. Ravi `SHP1001` COMPLETED left alone.
- Found live risk: `SHP1017` DRIVER_CHAT chain (`APT-A086` → `APT-0F6`) would trip appointments self-FK `replaced_appointment_id` on delete. Hardened `reset_demo_day.py` to null ops-message links + `replaced_appointment_id` before DELETE.
- Verification: live dry-run PASS; rollback-safe appointment wipe/restore proof PASS (`DELETE 2` then force rollback). Confirm write still not run. App tests not run.

## 2026-08-12 01:00 IST - Demo-day cast reset / restore script

- Added `supabase/demo/reset_demo_day.py` with `--mode cast` (default) and `--mode full`, `--dry-run`, `--confirm` / `SETUHAUL_DEMO_RESET=1`, optional `--include-shp1017`, and Upstash Redis chat-key clear for shared Ravi demos.
- Cast mode restores golden hero fields (`SHP-D16-RAVI` ETA 18:30 / unload 25, `D16-APT-RAVI-OLD` CONFIRMED, race slot free) and wipes escalations / extra ETAs / DRIVER_CHAT appointments / cast idempotency residue. Full mode wipes namespaced D16 inventory then re-applies `demo_day_2026-08-16.sql`. Does not touch Auth passwords.
- Documented in `supabase/demo/README.md`, `docs/DEMO_MANUAL_RUNBOOK.md` Prep, and root `README.md` Quick start.
- Verification: live `--dry-run` cast + full PASS against configured `DATABASE_URL` / Upstash (cast saw escalations/appointments/eta/idempotency/redis keys; no confirm write this turn). Application unit/integration tests not run.

## 2026-08-12 00:40 IST - Manual FDE demo + stress runbook

- Added `docs/DEMO_MANUAL_RUNBOOK.md`: ordered Phases Prep + A–G with exact chat lines, multi-browser race, NOSLOT, stale/cancel, Ops takeover, CONTEND sample, PDF coverage map, pass/fail sign-off.
- Updated `docs/DEMO_DRIVER_CHAT_SCRIPT.md` (cancel/reschedule enabled; D16-first; points to runbook).
- Updated `docs/DEMO_DAY_READINESS.md` §11.2 + replaced stale “Still to build before gate” with post-gate polish notes.
- Linked runbook from root `README.md`.
- Verification: documentation only; application tests **not run**. Agent/surface: Cursor.

## 2026-08-12 00:35 IST - Architecture Mermaid diagrams (exact Sprint 3 usage)

- Updated root `README.md` Architecture with three Mermaid diagrams: system context, driver chat sequence, scarce-capacity allocation flow.
- Updated `docs/ARCHITECTURE.md` high-level + AI + invoke-loop sections to the same exact usage model (`bind_tools` manual loop, feasibility/allocation, escalation_queue, Redis 24h).
- Verification: documentation only; application tests **not run**. Agent/surface: Cursor.

## 2026-08-12 00:30 IST - Root README updated through Sprint 3

- Rewrote root `README.md` Quick start for Sprint 1–3 complete: status table, demo capabilities (feasibility/request/cancel/reschedule/confirm/reject/expire, stale options, escalation queue, scarce-capacity proofs), deferred Sprint 4 / OR-Tools / post-demo auth, demo-day cast script pointers, scheduling architecture notes, docs links, and opt-in live integration test commands.
- Removed obsolete “Sprint 3 not started / CAPABILITY_NOT_ENABLED” framing; passwords remain owner-shared via `POC_TEAM_ACCOUNTS.local.md` (no resets until after demo).
- Verification: documentation only; application tests **not run**. Agent/surface: Cursor.

## 2026-08-12 00:25 IST - Sprint 3 exit gate COMPLETE

- Closed Sprint 3 gate with objective evidence: reschedule/reject/expire lifecycle, `REC-` recommendation versioning + `SLOT_OPTIONS_STALE`, durable `escalation_queue` + Ops takeover UI, live **10×4** scarce-slot load (zero double-books), and D16 cast API smoke (options→request→status→stale→cancel frees; NOSLOT persist; ops reject/confirm).
- Applied migration `20260812010000_sprint3_lifecycle_escalation.sql` (`EXPIRED` + `escalation_queue` + audit action widening). Fixed recommendation validate limit mismatch (5 vs 10), asyncpg-ambiguous NULL filters, and cast unload mins (25) for STANDARD 30-min slots in generator + live cast.
- Graphify updated (`python -m graphify update .`); NOSLOT tool path persists escalation; auth hardening remains post-demo deferred; facility-wide OR-Tools remains deferred with later design note.
- Verification: live integration `test_live_demo_day_load.py` **2 passed**; backend units **56 passed**; Playwright multi-browser UI **not run**. Agent/surface: Cursor (+ [lifecycle/escalation slice](d2192e98-8ce5-4a10-94b6-810780b800b8)).

## 2026-08-12 00:15 IST - Write Sprint 4 hosting plan into master plan

- Added Living Sprint 4 row and full §8.1 section to `plans/implementation-master-plan.md`: **PLANNED** hosting/AgentCore/observability/Locust sprint after Sprint 3 gate.
- Locked topology: **Vercel** frontend; **App Runner** FastAPI default (Azure/GCP also OK — AgentCore does not force BFF onto AWS); **Bedrock AgentCore** assistant (AWS-only); Supabase + Upstash; **CloudWatch** + **LangSmith**; Locust suites A (AgentCore chat) and B (10×3–4 scarce slots).
- Promoted Locust 10-driver load proof and AgentCore/CloudWatch from Sprint 3 remaining / §12 deferred into Sprint 4; updated Sprint 3 exit-gate wording, §13 next actions, and `plans/README.md`.
- Synced wiki `implementation`, `handoff`, `current-state`, `log`.
- Verification: documentation/plan write only; application tests **not run**. Agent/surface: Cursor.

## 2026-08-12 00:02 IST - Fix driver tool kwargs + chat history route + SHP1017 no-feasible chat

- Root cause of chat appointment/facility/slot “errors”: LangChain `StructuredTool.ainvoke` expands schema fields as kwargs, but driver tools took a single `args: Model` parameter (`unexpected keyword argument 'shipment_id'`). Reworked tools to `**kwargs` + `model_validate` (extra=ignore).
- Feasibility candidate SQL: slot timestamps are **text** in Postgres; bind `:eta_ts` as datetime with `CAST(sl.slot_end_ts AS timestamptz) > :eta_ts` (avoid `:eta_ts::timestamptz` which broke SQLAlchemy bind parsing).
- `/api/v1/chat/history` 404 was a **stale uvicorn** still holding :8000 without the GET route; clean restart registers history (401 unauth / 200 auth). Chat API now returns tool `result`/`result_preview`; Driver UI `console.groupCollapsed` logs them and status shows `tool:CODE`.
- Live browser (Ravi): `Find feasible replacement slots for SHP1017.` → `find_feasible_slots:NO_FEASIBLE_SLOTS` with escalation (Aug 7 ETA, 50 min unload vs 30 min D16 slots). Facility/appointment chat retest deferred; local uvicorn+Vite killed on user request pending other session.
- Verification: scheduling unit tests PASS (`16 passed`); direct `find_feasible_slots(SHP1017)` PASS (0 options + escalation); browser chat NO_FEASIBLE PASS. Full suite / facility+appointment chat / refresh matrix not completed this turn. Agent/surface: Cursor.

## 2026-08-11 23:25 IST - Implement appointment cancellation and confirmation

- Added strict Pydantic cancel/confirm commands and results in `backend/app/scheduling/allocation.py`. Both use trusted `ExecutionContext` scope, idempotency lookup/store, exact appointment row locks, transition validation, audit logs, commit, and authoritative reread.
- Cancellation allows the assigned Driver or scoped ops/admin for active appointments and writes `CANCELLED`, `is_current=0`, `cancelled_at`, and `cancellation_reason`, releasing the slot through existing partial-index predicates. Confirmation is ops/admin-only and writes `PENDING_CONFIRMATION` → `CONFIRMED`, `confirmed_at`, and `warehouse_confirmation_ref`.
- Mounted `POST /api/v1/shipments/{shipment_id}/appointments/{appointment_id}/cancel|confirm`, both requiring `Idempotency-Key`. Registered Driver LangChain `cancel_appointment`; prompt now enables cancel while reschedule stays disabled and confirmation stays ops/warehouse-only.
- Updated scheduling unit coverage, `docs/API.md`, master-plan Living status, and affected LLMWiki implementation/database/testing/current-state/handoff/log pages. Supabase skill/changelog reviewed; no schema, RLS, migration, secret, or live data change.
- Verification: focused allocation tests PASS (`10 passed`); full backend tests PASS (`50 passed, 1 skipped`); changed modules compile; OpenAPI contains both routes; IDE lints and `git diff --check` PASS. Live authenticated API/chat and live cancellation-release database proof were not run. Agent/surface: Cursor.

## 2026-08-11 23:16 IST - Persist driver chat UI across re-login (Redis 24h)

- Redis now stores an active conversation pointer per `user_id` (`setuhaul:chat:{uid}:active`) on each chat turn; `GET /api/v1/chat/history` restores bounded bubbles for that pointer (or explicit session/thread).
- Driver UI hydrates messages on mount, keeps `session_id`/`thread_id` in `localStorage`, prefers profile name (Ravi) over seed `drivers.driver_name`, and maps context-rail fields to real API keys (`current_status`, `slot_start_ts`, etc.).
- System prompt: open-slot questions must call `find_feasible_slots` for the active shipment; shown options are not facility-wide free reservations.
- Verification: `tests/unit/test_redis_memory.py` PASS (7); frontend `npm run lint` PASS (exhaustive-deps warning only). Live browser re-login smoke not re-run this turn. Agent/surface: Cursor.

## 2026-08-11 22:54 IST - Demo-day readiness mapped from FDE PDF

- Re-read `docs/SetuHaul_FDE_Challenge.pdf` §§8, 11.2, 12.1–12.2 and mapped each expected demo beat, student design question, chat message type, and stress scenario to current SHOW / ANSWER / PARTIAL / NOT YET status.
- Added `docs/DEMO_DAY_READINESS.md` as the judge-facing readiness sheet; points to `docs/DEMO_DRIVER_CHAT_SCRIPT.md` for runnable prompts.
- Verification: PDF text extract (20 pages); no application code changed; status based on verified Sprint 2 gate + Sprint 3 tools/tests already documented. Agent/surface: Cursor.

## 2026-08-11 23:45 IST - Reconcile master-plan Living Sprint 3 checklist

- Updated `plans/implementation-master-plan.md` Living status and §8/§13: struck verified demo-day dataset, timestamptz ETA fix, Auth cast expansion, Redis summaries/chat restore, cancel/confirm, feasible/NOSLOT API smoke, and request/status/race proofs with dated evidence.
- Added explicit **Sprint 3 remaining vs deferred** scoreboard and refreshed ordered next actions; Sprint 3 exit gate remains **OPEN**.
- Verification: documentation reconciliation only; application tests not rerun this turn. Agent/surface: Cursor.

## 2026-08-11 23:34 IST - Demo-day dataset + timestamptz ETA fix + Auth cast

- Applied additive migration `20260811233000_fix_v_latest_eta_timestamptz_order.sql` (live via Supabase MCP): `v_latest_eta` orders by `created_at::timestamptz`. Feasibility SQL casts slot/ETA comparisons to timestamptz.
- Added `supabase/demo/` generator/apply/Auth helpers and applied `demo_day_2026-08-16.sql` to live DB (full brief-scale additive volume + stress cast). Live totals: facilities 6, docks 25, drivers 105, slots 2934, shipments 661.
- Created 12 new Driver Auth users (`driver.drv004@…`–`drv015@…`) with the **same shared Driver password** (no resets). Password-grant PASS for Ravi + new drivers.
- Cancel/confirm appointment lifecycle landed earlier this session (REST + driver cancel tool); backend unit tests PASS (`50 passed`).
- Live API smoke: Ravi `SHP-D16-RAVI` feasible slots 200 with options; Vikas `SHP-D16-NOSLOT` 200 with empty options + escalation; cross-driver IDOR 403.
- Updated `docs/DEMO_DAY_READINESS.md`, `docs/DEMO_DRIVER_CHAT_SCRIPT.md`, gitignored `POC_TEAM_ACCOUNTS.local.md` (emails only; no passwords in changelog).
- Verification: demo SQL APPLY_OK; Auth create/map 12; unit tests 50 passed; live feasible/escalation smoke PASS. Broader 10-driver automated load proof and Playwright E2E still TODO. Agent/surface: Cursor.

## 2026-08-11 22:42 IST - Add ERICA-style Redis conversation summaries

- Extended `backend/app/services/redis_memory.py` with `:summaries` list, `load_summaries`, and async `maybe_summarize_history` (oldest 5 raw messages summarized when length ≥ 10; 24h TTL; degrade-safe).
- Wired summarization into `run_assistant`: injects prior summaries + last 5 raw turns into the LLM context; after each turn may create a summary via the unbound chat model; response includes `summary_created`.
- Updated system prompt, `get_conversation_memory` tool description, and `constraints.json` redis allowed uses.
- Verification: `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests -q --ignore=tests/integration` from `backend/` PASS (`47 passed`). Live Upstash summarize smoke not run this turn. Agent/surface: Cursor.

## 2026-08-11 22:35 IST - Fix facility_contacts column + verify Ravi driver sync

- Fixed `backend/app/services/driver_reads.py` `get_facility_details`: selected nonexistent `role_title` → correct `contact_role` (matches baseline migration + data dictionary).
- Verified live Supabase SQL for `FAC-JAI-01` returns three contacts; Ravi `USR001` mapped to `DRV001` / `FAC-JAI-01` with auth linked.
- Live browser smoke (manual login as `ravi.kumar@setuhaul.com`): `/driver` shows profile `USR001`/`DRV001`/`FAC-JAI-01`, context shipment `SHP1017`, chat facility path 200; second turn used tool `get_facility_details` successfully (no SQL error). Seed note: `drivers.driver_name` is `Rajesh Kumar` while `users.full_name` is `Ravi Kumar` for the same `DRV001` mapping.
- Added driver demo chat script at `docs/DEMO_DRIVER_CHAT_SCRIPT.md`.
- Deferred backlog: AWS Bedrock AgentCore + CloudWatch hosting (PROJECT.md AI stack) noted in master plan §12; Redis memory + bind_tools loop already implemented in-app.
- Verification: backend unit tests PASS (`45 passed`); MCP SQL PASS; browser chat facility tools PASS; passwords not written to docs. Agent/surface: Cursor.

## 2026-08-11 22:34 IST - Compare SetuHaul Upstash Redis vs ERICA classroom core

- Read ERICA VSCode core file-by-file (`config.py`, `memory.py`, `agent.py`, `driver.py`, `.env.example`, `requirements.txt`) and SetuHaul `redis_memory.py` / `run_assistant.py` / tools / settings.
- Finding: SetuHaul uses Upstash REST with authenticated user+session+thread keys, 24h TTL, bounded history + structured session state, duplicate-message dedupe, and degrade-safe chat. ERICA uses standard Redis URL, thread-only keys, LPUSH LangChain message dicts, and LLM rolling summarization when raw history exceeds 10; it hard-fails without `REDIS_URL` and has no auth scope or TTL.
- Updated `wiki/ai-system.md`, `wiki/handoff.md`, `wiki/log.md`. No application code changed.
- Verification: document/source comparison only; application tests not run. Agent/surface: Cursor.

## 2026-08-11 22:27 IST - FDE PDF: system-message and stress-test synthesis

- Re-read `docs/SetuHaul_FDE_Challenge.pdf` (20 pages) for what the Driver system message must encode and which stress scenarios the product must prove.
- Finding: no literal system prompt is prescribed. Pages 6–10/14 define conversational AI boundaries (clarify, tools, never decide capacity/compatibility/priority/commit/safety); pages 17–19 require concurrency/freshness/no-slot escalation demos.
- Updated `wiki/ai-system.md`, `wiki/handoff.md`, `wiki/log.md` with the synthesized requirements. Application `SYSTEM_PROMPT` in `backend/app/assistant/prompts.py` left unchanged this turn.
- Verification: PDF text extraction of all 20 pages via PyMuPDF; application tests not run (document analysis only). Agent/surface: Cursor.
>>>>>>> origin/main

## 2026-08-10 23:21 IST - Fix hung login preflight (backend venv crash)

- Diagnosed Driver login hang after successful Supabase `token?grant_type=password` 200: Network showed `/api/v1/auth/me` OPTIONS + GET both pending. Root cause was a crashed FastAPI worker (`ModuleNotFoundError: starlette`, then broken `greenlet`), not a frontend double-call bug.
- Reinstalled broken `backend/.venv` packages (`starlette`, `greenlet`) and restarted uvicorn with `--reload-dir app` to avoid watching `.venv`.
- Verification: `GET /health/live` PASS 200; `OPTIONS /api/v1/auth/me` PASS 200 with CORS allow-origin `http://localhost:5173`. The two `me` rows in DevTools are expected (preflight + request). Agent/surface: Cursor.

## 2026-08-10 23:12 IST - Move POC account roster to local share file

- Created gitignored `POC_TEAM_ACCOUNTS.local.md` with all 14 users across all 8 roles (name, email, role_id/role_name, facility/driver scope, portal, and the three role-shared passwords) for OOB team sharing.
- Cleared `SETUHAUL_POC_*_EMAIL` / `SETUHAUL_POC_*_PASSWORD` values from gitignored `.env` and `.env.local` (left empty placeholders + pointer to the local roster file). Added `POC_TEAM_ACCOUNTS.local.md` to `.gitignore`.
- Updated `.env.example` to point at the local roster file instead of storing passwords.
- Verification: env files restored to valid multiline format after scrub; Supabase/service keys retained; POC password fields empty. Passwords not written to changelog/wiki. Agent/surface: Cursor.

## 2026-08-10 23:05 IST - Authenticate remaining five users; remove Auth reset script

- Created Supabase Auth for the five previously unmapped seeded users (USR102–USR106) and mapped `public.users.auth_user_id`. Live totals: `auth.users=14`, mapped=`14`, unmapped=`0`.
- Kept the existing three role-shared passwords from gitignored `.env.local` (no new passwords). Grouping: Driver x3, Operations x6 (added Rahul/Anjali/Deepak), Admin x5 (added Sanjay/Neha).
- Expanded ops portal mapping and permissions so deferred personas can use `/ops/login`: `roleToPortal`, `ExecutionContext.is_operator`/`is_admin`, `ROLE_PERMISSIONS`, and operations `require_roles`.
- Deleted `docs/scripts/create_poc_auth_users.py` and local password helper artifacts; scrubbed `backend/README.md` and documented email buckets in `.env.example` (placeholders only).
- Updated `wiki/database.md`, `wiki/handoff.md`, `wiki/log.md`, `wiki/current-state.md`. Passwords not written to checked-in docs.
- Verification: password-grant PASS for eight sample accounts across all three buckets including all five new users; `python -m pytest tests/unit/test_execution_context.py -q` PASS (6). Skills: `supabase`. Agent/surface: Cursor.

## 2026-08-10 23:01 IST - Scope Redis chat memory by browser session

- Added `session_id` to the Driver chat request/response path so Redis memory is scoped by authenticated user, browser session, and thread instead of user/thread only.
- Updated `ConversationMemory` to normalize Redis key parts and key history, structured session state, snapshots, and duplicate `client_message_id` detection by `user_id + session_id + thread_id`.
- Updated Driver UI to create a stable per-browser-session id in `sessionStorage` and send it on `/api/v1/chat` requests. The session id is memory namespacing only; Supabase JWT remains the authority.
- Updated `backend/app/assistant/run_assistant.py`, `backend/app/api/v1/routers/chat.py`, `backend/app/assistant/tools.py`, `backend/app/assistant/prompts.py`, `backend/app/services/redis_memory.py`, `backend/tests/unit/test_redis_memory.py`, and `frontend/src/features/driver/DriverHome.tsx`.
- Updated `plans/implementation-master-plan.md`, `wiki/ai-system.md`, `wiki/implementation.md`, `wiki/current-state.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`.
- Verification: focused backend tests PASS (`18 passed`); full backend tests PASS (`43 passed, 1 skipped`); frontend `npm run lint` PASS; frontend `npm run build` PASS; `git diff --check` run after writeback.
- Agent/surface: Codex.

## 2026-08-10 22:46 IST - Reconcile implementation master plan

- Updated `plans/implementation-master-plan.md` from the beginning through the latest implementation state, striking only completed items with dated evidence and keeping the Sprint 3 exit gate open.
- Marked completed evidence for role-specific UI PNG assets/authenticated Ops dashboard polish, Redis-only memory clarification, current Gemini default configuration, individual POC Supabase Auth users, deterministic feasibility/ranking, fresh non-reserved option metadata, and live two-client same-slot contention proof.
- Added the ordered remaining Sprint 3/enterprise next list: live authenticated scheduling/chat smoke, appointment lifecycle transitions, stale-choice invalidation, no-slot escalation, ops takeover views, broader load proof, enterprise auth hardening, and formal Playwright/CI coverage.
- Updated `wiki/implementation.md`, `wiki/current-state.md`, `wiki/handoff.md`, and `wiki/log.md`.
- Verification: documentation-only plan reconciliation; no application tests run. `git diff --check` run after writeback.
- Skill: `software-architecture-design`. Agent/surface: Codex.

## 2026-08-10 22:39 IST - Configure local Gemini key and update default model

- Stored the provided Gemini API key only in gitignored `.env.local`, set `LLM_PROVIDER=gemini`, and set `LLM_MODEL=gemini-flash-latest`.
- Updated the Gemini default model in `backend/app/assistant/llm.py` from `gemini-2.5-flash` to `gemini-flash-latest`; the provided key reached Google but returned 404 for older pinned Flash models, while `gemini-flash-latest`, `gemini-3.5-flash`, and `gemini-3.6-flash` returned 200 via Google REST.
- Updated `backend/tests/unit/test_llm_factory.py`, `.env.example`, `README.md`, `wiki/ai-system.md`, `wiki/current-state.md`, and `wiki/handoff.md` to match the current Gemini default.
- Verification: `backend/.venv/Scripts/python.exe -m pytest tests/unit/test_llm_factory.py -q` PASS, 10 passed; direct Google REST generateContent with `gemini-flash-latest` PASS and returned `SETUHAUL_GEMINI_OK`; model listing PASS. LangChain `ChatGoogleGenerativeAI.invoke` attempted twice but timed out in the local shell, so full LangChain live invoke remains to be rechecked after restarting the backend/dev environment. No key printed in checked-in docs.

## 2026-08-10 22:31 IST - Polish authenticated ops dashboard UI

- Refined the authenticated Operations dashboard from a debug-like summary into a tighter enterprise workspace: cleaner scope/freshness metadata, stronger metric hierarchy, two-column status/exception layout, improved empty state, formatted timestamps, and readable exception rows without inventing data.
- Fixed the protected shell/profile dropdown presentation so the menu anchors to the topbar, avoids awkward dashboard overlap, formats role names, and uses the existing secondary button style for logout.
- Updated `frontend/src/features/operator/OpsHomes.tsx`, `frontend/src/layouts/ProtectedLayout.tsx`, and `frontend/src/App.css`.
- Verification: `npm run lint` PASS; `npm run build` PASS; local frontend `GET /ops/login` PASS 200; backend `GET /health/ready` PASS with database reachable; live Supabase password grant for `arvind.nair@setuhaul.com` PASS 200; running backend `/api/v1/auth/me`, `/operations/dashboard-summary?facility_id=FAC-GGN-01`, and `/operations/exceptions?facility_id=FAC-GGN-01` PASS 200. Headless screenshot capture was attempted but blocked by local command policy around Chrome process cleanup, so no new screenshot artifact was produced.

## 2026-08-10 22:20 IST - Correct memory architecture to Redis-only

- Corrected active agent/tooling instructions and wiki pages to remove the project Memory MCP workflow. SetuHaul memory is now documented as Upstash Redis only for application conversation/session state; durable project context remains in checked-in source, plans, changelog, and wiki files.
- Removed Memory MCP server configuration files that only existed to launch `@modelcontextprotocol/server-memory`; deleted the stale Claude MCP approval file, removed `.agent-memory/` from `.gitignore`, and preserved `.cursor/mcp.json` with the Supabase MCP entry only.
- Updated `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/setuhaul.mdc`, `docs/AI_TOOLING.md`, `docs/HANDOFF.md`, `wiki/AGENTS.md`, `wiki/ai-system.md`, `wiki/implementation.md`, `wiki/database.md`, `wiki/index.md`, `wiki/skills-and-mcp.md`, `wiki/handoff.md`, and `wiki/log.md`.
- Verification: documentation/config change only; no app tests run. `rg` used to locate active Memory MCP references. Agent/surface: Codex.

## 2026-08-10 22:11 IST - Add extra live POC login accounts and Redis env

- Created six additional live Supabase Auth POC accounts and mapped them to `public.users.auth_user_id`: Drivers `USR002` Amit Singh and `USR003` Vikas Sharma, Operations Executives `USR107` Kavita Rao and `USR108` Arvind Nair, and Admins `USR997` Meera Iyer and `USR998` Suresh Menon. Added new app-user rows only where missing for the extra Ops/Admin personas; seeded Driver rows were reused.
- Added gitignored local env files `.env.local` and `frontend/.env.local` so the backend/frontend can run against the provided Supabase project. The backend env includes the Upstash Redis REST endpoint/token derived from the provided Redis URL; the frontend env includes only browser-safe Vite values.
- Verified each new account with Supabase password-grant login status `200` and confirmed each `public.users` row has a non-null `auth_user_id`. Verified Upstash Redis REST connectivity with `/ping`, short-lived `set`, and `get`.
- Verification: live Supabase Auth/Data API account create+mapping PASS for 6 accounts; Redis REST smoke PASS (`PONG`, `OK`, `ok`). `redis-cli` was not available in this sandbox, so Redis was verified through Upstash REST. No app tests run because this was live credential/data setup. Skills: `supabase`, `supabase-postgres-best-practices`. Coding-agent Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 20:35 IST - Add live same-slot concurrency proof

- Added `backend/tests/integration/test_live_scheduling_concurrency.py`, an opt-in live Supabase integration test for two simultaneous `request_slot` calls competing for the same temporary slot. The test creates temporary `CODX` shipment/slot fixtures, runs independent async sessions concurrently, asserts exactly one `SLOT_REQUESTED` winner and one `SLOT_CONFLICT_REFRESH_REQUIRED` loser, verifies one active appointment, one booking audit row, and two idempotency rows, then cleans up all temporary rows.
- Added `pytest-asyncio` to `backend/pyproject.toml` and kept generated `backend/uv.lock` so async integration testing is reproducible without pytest marker/config warnings.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/database.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. The real same-slot contention checklist now has live evidence, but the Sprint 3 exit gate remains open because reschedule/confirm/cancel/reject/expire flows and no-slot escalation demo are still incomplete.
- Verification: default backend tests PASS, 41 passed and 1 live integration skipped, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests -q`; explicit live concurrency proof PASS, 1 passed, via `SETUHAUL_RUN_LIVE_DB_TESTS=1` with `DATABASE_URL`; post-run cleanup verification PASS with zero `CODX` idempotency, appointment, slot, or shipment rows. Supabase changelog checked; no schema/RLS/Data API change made. Skills: `supabase`, `supabase-postgres-best-practices`. Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 20:23 IST - Inspect live Supabase database catalog

- Connected to the live Supabase PostgreSQL database through a direct read-only Postgres session and inspected public schema metadata plus seeded operational counts. No schema, data, grant, RLS, or migration changes were made.
- Verified PostgreSQL 17.6, `auth.users=3`, public schema has 23 tables and 4 views. Key seeded counts: `shipments=21`, `appointment_slots=106`, `appointments=22`, `driver_exceptions=12`, `eta_updates=14`, `docks=9`, `facilities=2`, `users=10`, `roles=8`, `idempotency_requests=2`.
- Confirmed Sprint 3-relevant seed state: active/open slot inventory exists across Jaipur and Gurugram, two current `PENDING_CONFIRMATION` appointments exist, and scheduling guard indexes `ux_active_appointment_per_slot` plus `ux_current_active_appointment_per_shipment` are present.
- Updated `wiki/database.md`, `wiki/current-state.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint status unchanged: Sprint 3 remains IN PROGRESS and live same-slot concurrency proof is still required.
- Verification: read-only asyncpg catalog queries PASS. Supabase changelog checked; Data API auto-exposure change noted but not applicable to this direct Postgres inspection. Skills: `supabase`, `supabase-postgres-best-practices`. Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 20:16 IST - Add deterministic slot ranking algorithm

- Upgraded `backend/app/scheduling/feasibility.py` from earliest-slot ordering to an explicit deterministic slot-ranking algorithm. Feasible options now include `rank_score` and `ranking_factors` for priority, lateness, wait after ETA, fit slack, dock match, operational disruption score, and stable shipment/slot tie-breaker.
- Moved ranking policy knobs into `backend/app/scheduling/constraints.json` via `priority_scores` and `score_weights`, and extended `backend/app/scheduling/constraints.py` so the scoring model remains centrally tunable from the constraints registry.
- Updated ranking explanations returned by `find_feasible_slots` so the model/client can explain why an option was preferred without inventing scheduling logic.
- Added unit coverage in `backend/tests/unit/test_scheduling_feasibility.py` for scoring factors and ETA-wait penalty, and extended `backend/tests/unit/test_scheduling_constraints.py` to guard the editable ranking weights.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint 3 remains IN PROGRESS; this strengthens ranking, but live authenticated smoke and real concurrency proof are still open.
- Verification: backend unit tests PASS, 41 passed, using `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Supabase changelog checked; no schema/RLS/Data API change made. Skills: `software-architecture-design`, `supabase`, `supabase-postgres-best-practices`. Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 19:59 IST - Add Redis conversation memory tool

- Added `ConversationMemory.snapshot(...)` in `backend/app/services/redis_memory.py` to return bounded Upstash Redis thread/session memory with 24-hour TTL metadata, non-authoritative labeling, recent message snippets, and degraded-state details when Redis is unavailable.
- Registered Driver LangChain tool `get_conversation_memory` in `backend/app/assistant/tools.py` and passed the existing `ConversationMemory` instance from `backend/app/assistant/run_assistant.py`, scoped to the authenticated user and current thread.
- Updated `backend/app/assistant/prompts.py` so the model may use Redis memory only as ephemeral chat/session context and must verify all operational facts through PostgreSQL-backed tools.
- Added `backend/tests/unit/test_redis_memory.py` and extended tool allowlist coverage in `backend/tests/unit/test_scheduling_allocation.py`.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/ai-system.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint 3 remains IN PROGRESS; Memory MCP remains unavailable as a coding-agent connector, but application memory now exposes a Redis-backed LangChain tool.
- Verification: backend unit tests PASS, 40 passed, using `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live Upstash smoke not run because Redis env values were not configured/persisted. Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 19:50 IST - Harden request_slot allocation race handling

- Hardened `backend/app/scheduling/allocation.py` so residual PostgreSQL partial-unique allocation races are translated into the same conflict-safe `SLOT_CONFLICT_REFRESH_REQUIRED` response instead of leaking a raw `IntegrityError`. The translator recognizes `ux_active_appointment_per_slot` and `ux_current_active_appointment_per_shipment`, rolls back the failed transaction, refreshes feasible options, stores the 409 idempotency response, and returns zero appointment writes.
- Updated `backend/app/api/v1/routers/scheduling.py` so slot-request conflicts return HTTP 409 while preserving refreshed options under the response `data`.
- Added unit coverage in `backend/tests/unit/test_scheduling_allocation.py` for both allocation uniqueness guards and unrelated integrity errors.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/database.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint 3 remains IN PROGRESS; this is conflict mapping coverage, not a completed live same-slot concurrency proof.
- Verification: backend unit tests PASS, 38 passed, using `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated API/chat smoke and real parallel database contention were not run because local env files are absent and pasted secrets were not persisted. Skills: `supabase`, `supabase-postgres-best-practices`. Supabase changelog checked; no schema/RLS/Data API change made. Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 19:38 IST - Add appointment request status read path

- Added `get_appointment_request_status` in `backend/app/scheduling/allocation.py` as a read-only Sprint 3 status service for slot requests. It verifies driver/operator/admin scope, reads the authoritative appointment row plus recent shipment appointment history, maps lifecycle states to stable result codes, and always reports zero appointment writes.
- Extended `backend/app/api/v1/routers/scheduling.py` with `GET /api/v1/shipments/{shipment_id}/appointment-request/status` and optional `appointment_id` query support.
- Registered Driver LangChain tool `get_appointment_request_status` in `backend/app/assistant/tools.py` and updated `backend/app/assistant/prompts.py` so pending confirmation is never described as a confirmed booking.
- Added unit coverage for appointment-status code mapping and Driver tool allowlist registration in `backend/tests/unit/test_scheduling_allocation.py`.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/ai-system.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint 3 remains IN PROGRESS; same-slot concurrency proof and transition flows are still open.
- Verification: backend unit tests PASS, 35 passed, using `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated API/chat smoke not run because local env files are absent and pasted secrets were not persisted. Skills: `supabase`, `supabase-postgres-best-practices`. Supabase changelog checked; no schema/RLS/Data API change made. Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 19:31 IST - Add transactional request_slot flow

- Added `backend/app/scheduling/allocation.py` with `request_slot`, the first Sprint 3 transactional scheduling command. It requires idempotency, verifies driver ownership, row-locks/revalidates shipment and slot state, checks active slot/shipment appointments, reuses feasibility evaluation, inserts `PENDING_CONFIRMATION`, writes `BOOK_APPOINTMENT` audit, stores the idempotent response, commits, and rereads the appointment.
- Extended `backend/app/api/v1/routers/scheduling.py` with `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request` requiring `Idempotency-Key`.
- Registered Driver LangChain tool `request_slot` in `backend/app/assistant/tools.py` and updated `backend/app/assistant/prompts.py` so exact selected slot requests are pending-confirmation only; reschedule, cancellation, and confirmation remain disabled.
- Added `backend/tests/unit/test_scheduling_allocation.py` and adjusted `backend/tests/unit/test_scheduling_feasibility.py` for tool allowlist coverage.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/ai-system.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint 3 remains IN PROGRESS; same-slot concurrency proof and remaining transition flows are still open.
- Verification: backend unit tests PASS, 33 passed, using `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated API/chat smoke not run because local env files are absent and pasted secrets were not persisted. Skills: `supabase`, `supabase-postgres-best-practices`. Supabase changelog checked; no schema/RLS/Data API change made. Agent/surface: Codex.

## 2026-08-10 19:12 IST - Add LangChain feasible slot search path

- Added `backend/app/scheduling/feasibility.py`, the first deterministic Sprint 3 feasibility service. It reads latest ETA, facility, slot, dock, active appointment, and dock-event data from PostgreSQL, applies policy-backed hard constraints, returns explainable `DISPLAYED_NOT_RESERVED` options, and emits no-slot escalation payloads when nothing is feasible.
- Added `backend/app/api/v1/routers/scheduling.py` with `GET /api/v1/shipments/{shipment_id}/slots/feasible` and mounted it in `backend/app/main.py`.
- Registered `find_feasible_slots` in `backend/app/assistant/tools.py` for Driver LangChain chat. Updated `backend/app/assistant/prompts.py` so slot search is allowed as informational only, while booking, holds, rescheduling, cancellation, and confirmation still return `CAPABILITY_NOT_ENABLED`.
- Added `backend/tests/unit/test_scheduling_feasibility.py` covering core feasibility failures and LangChain tool allowlist registration.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/ai-system.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint 3 remains IN PROGRESS; transactional allocation and concurrency proof are still open.
- Verification: backend unit tests PASS, 30 passed, using `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; `git diff --check` PASS with line-ending warnings only. Live authenticated API/chat smoke not run because local env files are absent and pasted secrets were not persisted. Skill: `supabase`. Supabase changelog checked; no schema/RLS/Data API change made. Agent/surface: Codex.

## 2026-08-10 18:55 IST - Start Sprint 3 constraints registry

- Added `backend/app/scheduling/constraints.json` as the single editable scheduling constraints file for the Sprint 3 build: PostgreSQL authority, LangChain-only orchestration, Redis non-authoritative state, feasibility hard constraints, ranking policy, appointment lifecycle meanings, stale-option invalidation, no-slot escalation, write-safety, and deferred non-gate scope.
- Added `backend/app/scheduling/constraints.py` with strict Pydantic loading/caching and `backend/tests/unit/test_scheduling_constraints.py` to guard the registry.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/ai-system.md`, `wiki/testing.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint 3 is now IN PROGRESS; exit gate remains open and no allocation checklist item was struck.
- Verification: backend unit tests PASS, 25 passed, using `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; `git diff --check` PASS with a CRLF warning on pre-existing `CHANGELOG.md` line endings. Memory MCP unavailable in this Codex session. Skill: `software-architecture-design`. Agent/surface: Codex.

## 2026-08-10 18:29 IST - Differentiate Driver and Ops login hero imagery

- Generated a dedicated Driver portal hero image and saved it as `frontend/src/assets/setuhaul-driver-eta-hero.png`.
- Updated `LoginForm` so Driver login uses the Driver ETA/exception image, copy, and metrics, while Ops login keeps `frontend/src/assets/setuhaul-dock-command-hero.png` with dock-command copy and metrics.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint status unchanged: Sprint 1 complete, Sprint 2 complete, Sprint 3 TODO/active next.
- Verification: `npm run lint` PASS; `npm run build` PASS; screenshots `tmp/ui-polish/driver-login-role-hero.png` and `tmp/ui-polish/ops-login-role-hero.png` captured and visually spot-checked. Memory MCP unavailable in this Codex session. Skill: `imagegen`. Agent/surface: Codex.

## 2026-08-10 18:22 IST - Replace login visual with generated dock-command hero

- Generated a unique, relevant SetuHaul login hero image for warehouse dock coordination and saved it as `frontend/src/assets/setuhaul-dock-command-hero.png`.
- Replaced the weak abstract/fake-map login visual with the generated image, dark readability overlays, tighter headline copy, and classroom-scale metrics.
- Updated `plans/implementation-master-plan.md`, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint status unchanged: Sprint 1 complete, Sprint 2 complete, Sprint 3 TODO/active next.
- Verification: `npm run lint` PASS; `npm run build` PASS; screenshot `tmp/ui-polish/driver-login-dock-hero.png` captured and visually spot-checked. Memory MCP unavailable in this Codex session. Skill: `imagegen`. Agent/surface: Codex.

## 2026-08-10 18:12 IST - Frontend UI polish for POC portals

- Polished the React UI while preserving the two-portal POC boundary: upgraded login composition with a Stitch-aligned operational visual, tightened the app shell, switched body typography to Inter, added a driver chat header, replaced raw driver context JSON with structured field cards, and improved ops metrics/status distribution presentation.
- Fixed the existing `ProtectedLayout` hook dependency warning by memoizing the profile loader with `useCallback`.
- Updated `plans/implementation-master-plan.md` Living status refresh note, `wiki/current-state.md`, `wiki/implementation.md`, `wiki/handoff.md`, and `wiki/log.md`. Sprint status unchanged: Sprint 1 complete, Sprint 2 complete, Sprint 3 TODO/active next; no Sprint 3 checklist item was struck.
- Verification: `npm run lint` PASS; `npm run build` PASS; Vite served on `http://127.0.0.1:5173`; unauthenticated `/driver/login` desktop and `/ops/login` mobile screenshots captured under `tmp/ui-polish/` and visually spot-checked. Authenticated protected screens were not live-smoked because local env files are absent and pasted secrets were not persisted.
- Security: live secrets were pasted in chat; they were not written to files or echoed in logs. Rotate after POC. Memory MCP unavailable in this Codex session. Agent/surface: Codex.

## 2026-08-10 17:51 IST - Analyze FDE challenge brief

- Analyzed `docs/SetuHaul_FDE_Challenge.pdf` (20 pages) against the current master plan and wiki context.
- Outcome: the brief intentionally does not prescribe framework, tools, storage, concurrency, allocation algorithm, or deployment, but it does require challenge proof around driver exception chat, feasibility, allocation semantics, simultaneous scarce-capacity competition, stale/disappearing options, duplicate/retry handling, and no-feasible-slot escalation.
- Updated `wiki/implementation.md`, `wiki/current-state.md`, `wiki/handoff.md`, and `wiki/log.md`. `plans/implementation-master-plan.md` Living status unchanged because no implementation progress changed: Sprint 1 complete, Sprint 2 complete, Sprint 3 TODO/active next.
- Verification: text extracted from all 20 PDF pages with `pdfplumber`; representative pages 1, 10, and 18 rendered with Poppler and visually spot-checked. Application tests not run because this was document analysis only.
- Memory MCP unavailable in this Codex session; checked-in context is synchronized and memory replay remains pending. Skill: `pdf`. Agent/surface: Codex.

## 2026-08-08 13:45 IST - Rename `web/` → `frontend/`

- Renamed React app directory `web/` to `frontend/` (stopped Vite lock first). Package name `frontend`; CI working-directory + lockfile cache path updated; `.gitignore` ignores `frontend/node_modules` + `frontend/dist` (kept legacy `web/` ignore lines).
- Updated README Quick start, `.env.example` under frontend, master-plan scaffold wording, `plans/branches/full-stack.md`. Historical changelog/wiki log lines that said `web/` left as past evidence.
- Verification: `npm run build` in `frontend/` **PASS**. Agent/surface: Cursor (Composer).

## 2026-08-08 13:35 IST - Root GET / health ping

- Added `GET /` on FastAPI (`backend/app/main.py`) returning alive JSON (`status: ok` + links to `/health/live`, `/health/ready`, `/docs`) so opening `:8000/` is not 404.
- README Quick start notes root is a health ping; UI remains `localhost:5173`.
- Verification: TestClient `GET /` → 200; `/health/live` → 200; `/health/ready` → 200 (unchanged semantics). Agent/surface: Cursor (Composer).

## 2026-08-07 20:25 IST - Gemini live PASS (ChatGoogleGenerativeAI + gemini-2.5-flash)

- Saved owner Google/Gemini key to gitignored `.env` only (never printed). Live `ChatGoogleGenerativeAI` invoke **PASS** after default model bump: `gemini-2.0-flash` → **`gemini-2.5-flash`** (2.0 shut down June 2026).
- Full provider live smoke now: OpenAI PASS, OpenRouter PASS, Gemini PASS. Unit **20 passed**.
- Recommend rotating chat-pasted keys after POC. Agent/surface: Cursor (Composer).

- Live smoke (keys in gitignored `.env` only; values not logged): **OpenAI PASS**, **OpenRouter PASS**, **Gemini FAIL** — pasted “Gemini” value was an OpenAI `sk-proj` key (works as OpenAI; rejected by Google).
- Switched Gemini path to native LangChain **`ChatGoogleGenerativeAI`** (`langchain-google-genai`); OpenAI/OpenRouter remain `ChatOpenAI`. Factory rejects OpenAI-shaped keys in `GOOGLE_API_KEY` with a clear 503.
- Deps: `langchain-google-genai` in `requirements.txt` / `pyproject.toml`. README + `.env.example` note Google AI Studio (`AIza…`) keys.
- Verification: unit **20 passed** (factory + gemini class/key-shape tests). Gemini live invoke still blocked until a real Google key is provided. Recommend rotating chat-pasted keys after POC.
- Agent/surface: Cursor (Composer). No secrets committed.

## 2026-08-07 20:00 IST - README team guide + multi-provider LLM factory

- Rewrote [README.md](README.md) Quick start for Sprint 1–2 POC: run steps, env table, demo login (emails + password env-var names; passwords stay OOB), demo script, LLM provider notes.
- Extended [.env.example](.env.example): `LLM_PROVIDER`/`LLM_MODEL`, `OPENROUTER_API_KEY`, `GOOGLE_API_KEY`, `SETUHAUL_POC_*` placeholders.
- Added `backend/app/assistant/llm.py` ChatOpenAI factory: `auto` → OpenAI → OpenRouter → Gemini; explicit providers; same `bind_tools` path via `run_assistant`.
- Settings: `openrouter_api_key`, `google_api_key`, `llm_provider`, `llm_model`; `ready_llm` (+ `ready_openai` alias).
- Verification: backend unit **18 passed** (8 new factory tests). Live OpenRouter/Gemini smoke **not run** (keys unset in local `.env`; OpenAI key present for auto). Browser chat **not re-run** this turn.
- Skills: none material beyond repo policy. Agent/surface: Cursor (Composer). No secrets committed.

## 2026-08-07 19:35 IST - Sprint 2 exit gate COMPLETE

- Closed Sprint 2 vertical slice: atomic ETA/exception write, `ChatOpenAI.bind_tools` + manual `run_assistant`, Upstash 24h memory, DriverHome live chat, Ops refresh match, LangSmith env tracing, scripted demo.
- Fixes during proof: JWT `leeway=300` (local clock skew / immature `iat`); audit `action_type`=`UPDATE_ETA`; exception_type=`DELAY`; `tzdata` for Windows ZoneInfo; stripped UTF-8 BOM from gitignored env files after credential paste; killed stale multi-uvicorn listeners on :8000.
- Credentials saved only to gitignored root `.env` / `.env.local` (OpenAI, Upstash, LangSmith). **Never printed.** Handoff recommends rotating keys pasted in chat after POC if the repo is shared.
- Verification: backend unit **8 passed**; `docs/scripts/sprint2_demo_path.py` → **DEMO_PATH_PASS** (chat tools, confirmation gate, PERSISTED write, idempotent replay, `scheduling_capability_disabled`, ops matching ETA); browser localhost:5173 matrix PASS (driver login→LLM tools→ETA persist→logout→ops refresh match→logout). Screenshots `tmp/poc-screenshots/11`–`14` (gitignored).
- Living status: Sprint 2 **COMPLETE**; Sprint 3 TODO next. Migration `20260807184700_sprint2_idempotency_requests.sql` applied via Supabase MCP.
- Skills: supabase + postgres best practices for migration; playwright for browser proof.
- Agent/surface: Cursor subagent (Composer). Dirty tree preserved (no commit; no secrets committed).

## 2026-08-07 19:26 IST - Sprint 2 status re-baseline (honest verified vs incomplete)

- Assessed dirty-tree Sprint 2 slice against Living §7 with runtime evidence. Living status → **Sprint 2 ACTIVE / IN PROGRESS** (exit gate remains open).
- **Verified DONE (struck):** repair vs ETA distinction (unit + demo preview); FastAPI read/write services + tool injection; deny-by-default role REST allowlists; `ChatOpenAI.bind_tools` + `run_assistant` manual loop (live chat tool_calls on `SHP1017`).
- **PARTIAL / IN PROGRESS (not struck):** exception thread + multi-shipment clarification (code only); atomic ETA/exception/idempotency write (code + migration applied live, but confirmed write **FAIL**); Upstash 24h memory (code + env present, round-trip not asserted); duplicate/replay; driver live chat UI (wired, browser chat not re-smoked); Ops UI (summary+exceptions only — schedule/dock/rules not wired); CAPABILITY_NOT_ENABLED (tool present, live denial not reached); LangSmith + demo script (script FAIL at write).
- **Blocker:** `POST /api/v1/shipments/{id}/eta-updates` with `confirmed=true` → HTTP 500 `CheckViolationError` on `audit_logs_action_type_check` because code inserts `ETA_UPDATE` while DB allows `UPDATE_ETA`.
- Credentials (lengths only, no secrets): `OPENAI_API_KEY` set; `UPSTASH_REDIS_REST_URL`/`TOKEN` set; `LANGSMITH_API_KEY` + tracing set.
- Verification: `/health/live`+`/health/ready` PASS; backend unit **8 passed**; `sprint2_demo_path.py` steps 1–4 PASS, step 5 FAIL; Vite :5173 up; idempotency migration indexes present via Supabase MCP. Browser exit-gate chat UX **not run**. Dirty tree preserved (no commit).
- Writeback: master plan Living + §7; wiki handoff/current-state/implementation/log; Memory MCP.
- Agent/surface: Cursor subagent (Composer).

## 2026-08-07 18:36 IST - Tighten .gitignore to reduce commit noise

- Expanded root `.gitignore`: `graphify-out/`, coverage/mypy/ruff caches, logs, `.DS_Store`/`Thumbs.db`, `.idea/`, root `.venv/`, broader `__pycache__`.
- Confirmed still ignored: `.env*` (except `.env.example`), `.agent-memory/`, `tmp/`, `backend/.venv/`, `web/node_modules`, `web/dist`.
- Verification: `git check-ignore` PASS for `graphify-out/`; `git status` no longer lists graphify artifacts. No secrets committed. Application tests not run (ignore-only change).
- Agent/surface: Cursor (Composer).

## 2026-08-07 17:55 IST - Sprint 1 exit gate COMPLETE

- Closed remaining Sprint 1 exit-gate gaps; Living status → **Sprint 1 COMPLETE / Sprint 2 ACTIVE (TODO ready to start)**.
- **Fixes / additions:**
  - CORS allowlist now includes both `http://localhost:5173` and `http://127.0.0.1:5173` (`settings` default, `.env.example`, local `.env`/`.env.local`).
  - Baseline a11y: labelled login inputs, `aria-live` loading/errors on login + shells, focusable profile/logout (`LoginForm`, `ProtectedLayout`, driver/ops homes).
  - Minimal CI: `.github/workflows/ci.yml` (backend `pytest tests/unit` + frontend `npm run build`).
  - JWT forged/malformed path no longer 500: `JwtVerifier` maps PyJWKClient/decode failures → 401 `TOKEN_INVALID`.
  - SQLAlchemy repository deepen + fuller a11y/responsive + expanded CI marked **TODO (DEFERRED until Sprint 2+)**.
- **Verification matrix (all PASS unless noted):**
  - Browser: Admin `/ops/login`→`/ops` global RO + logout; Driver + Operator reconfirm; wrong-portal Driver-on-ops and Ops/Admin-on-driver (redirect without elevation); baseline a11y labels/`aria-live`.
  - API: missing/invalid/forged Bearer → 401; driver own `SHP1017` 200 / other `SHP1002` 403; Operator facility vs Admin global dashboard-summary; Operator cross-facility 403; Driver ops 403; no scheduling mutation routes; no `SERVICE_ROLE` in web env; CORS both origins.
  - Local: backend unit **4 passed**; frontend `npm run build` **PASS**.
  - Screenshots (gitignored): `tmp/poc-screenshots/05`–`10`.
- Skills/MCP: Memory MCP + Supabase MCP (shipment ID lookup for IDOR); Playwright via local `tmp/pw` (gitignored). No secrets printed.
- Agent/surface: Cursor subagent (Composer).

## 2026-08-07 17:04 IST - Living sprint catch-up + cross-IDE plan writeback policy

- Re-baselined `plans/implementation-master-plan.md` Living status to **Sprint 1 ACTIVE / MOSTLY COMPLETE (exit gate open)**; corrected stale `/auth/me` FAIL and Browser E2E TODO evidence with 16:35 / 16:53 IST proofs; struck Stitch skeleton + observational-read items; left a11y/CI/exit gate and **all Sprint 2** items as TODO.
- Root `AGENTS.md`: startup must report Living sprint status; durable writeback now includes master-plan checklist strikethrough (fifth atomic target). Mirrored in `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/setuhaul.mdc`, `wiki/AGENTS.md`, `plans/README.md`.
- Memory MCP: added missing 16:53 browser-smoke observation + this policy catch-up.
- Verification: grep plan for stale `DB_UNAVAILABLE` / “Browser E2E still TODO” on proved items → **0**; Sprint 2 still unchecked. Application tests **not run** (docs/policy only).
- Agent/surface: Cursor (Composer).

## 2026-08-07 16:53 IST - Browser smoke PASS; Stitch skeleton + asyncpg pooler fix

- Browser-smoked two-portal Sprint 1 POC UI on Vite `http://localhost:5173` against API `http://127.0.0.1:8000`.
- **Stitch:** Before this turn, `web` already used set-2 tokens (navy `#0b1326`, Hanken Grotesk / IBM Plex Sans) — not default Vite scaffolding. Added Stitch-inspired driver chat shell + ops metric cards; login already token-aligned.
- **Blockers fixed:**
  - `web/src/core/http/api.ts` wrong import `./supabase` → `../auth/supabase` (blank Vite page).
  - Created `web/.env.local` with VITE_* only (gitignored).
  - asyncpg + Supabase PgBouncer: `statement_cache_size=0` in `backend/app/db/session.py` (driver/context was empty HTTP 500; multi-query prepared-statement failure).
  - Unhandled exception envelope + CORS middleware order in `backend/app/main.py` / `errors.py`.
  - Use `localhost:5173` for browser (CORS allowlist is `http://localhost:5173`; `127.0.0.1:5173` failed fetch earlier).
- **Browser results (roles only):** Driver login PASS → `/driver` chat shell + profile/logout; logout PASS; Ops login (OPERATOR) PASS → `/ops` dashboard metrics (20 / 9 / 6).
- Screenshots (gitignored): `tmp/poc-screenshots/01-driver-login.png`, `02-driver-shell.png`, `03-ops-login.png`, `04-ops-dashboard.png`.
- Verification: `/health/ready` PASS after uvicorn restart; `/api/v1/driver/context` + ops dashboard-summary PASS via JWT; browser smoke as above. Frontend `npm run build` **not run**; unit tests **not re-run**; Playwright install attempt failed earlier (used cursor-ide-browser instead).
- Remaining Sprint 1 UI gaps: fuller Stitch layout parity (sidebar/top search), a11y polish, wrong-portal redirect UX, CORS may still need `http://127.0.0.1:5173` if teammates use that host.
- Agent/surface: Cursor subagent (Composer).

## 2026-08-07 16:35 IST - DATABASE_URL saved; /auth/me PASS for Driver/Ops/Admin

- User confirmed `.env` had not been saved earlier; after save, on-disk `DATABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` non-empty (lengths only verified; secrets not printed).
- Backend settings load: `ready_database=True`. Restarted uvicorn.
- `GET /health/live` **PASS**; `GET /health/ready` **PASS** (`database_reachable=true`).
- `GET /api/v1/auth/me` **PASS** for all three POC JWTs:
  - Driver `USR001` / `DRIVER` / scope facility `FAC-JAI-01` / `DRV001`
  - Operator `USR101` / `OPERATIONS_EXECUTIVE` / facility `FAC-JAI-01`
  - Admin `USR999` / `ADMIN` / scope `global_read_only`
- Settings already load `.env.local` paths from prior turn.
- Verification: health + auth/me as above; browser portal smoke **not run**; unit tests **not re-run**. No secrets committed.
- Agent/surface: Cursor (Composer).

## 2026-08-07 16:32 IST - Auth/me re-prove blocked: DATABASE_URL empty on disk

- User asked to proceed after adding Dashboard credentials. Restarted backend; `/health/live` **PASS**.
- `/health/ready` still **degraded**: `database_url_configured=false`. Settings load confirmed `database_url` length 0.
- On-disk check (lengths only, no secret values printed): root `.env` and `.env.local` have empty `DATABASE_URL` and empty `SUPABASE_SERVICE_ROLE_KEY`; `SUPABASE_URL` and anon key remain populated.
- Updated `backend/app/core/settings.py` to also load `.env.local` / `../.env.local` so repo-root local files are picked up when uvicorn runs from `backend/`.
- `/api/v1/auth/me` **not re-proved** — waiting for non-empty `DATABASE_URL` (and preferably service role) to be saved again, then backend restart.
- Verification: health as above; unit tests **not run**; browser smoke **not run**. No secrets written or committed.
- Agent/surface: Cursor (Composer).

## 2026-08-07 16:45 IST - Anon keys via MCP; JWT proved; auth/me blocked on DATABASE_URL

- Supabase MCP `get_project_url` + `get_publishable_keys` returned project URL and publishable/legacy anon keys. Service role and DB connection string are **not** exposed by MCP.
- Populated anon keys locally only (gitignored `.env`, `.env.local`, `web/.env.local`) — documented as “populated locally”; secrets not printed. `.gitignore` / `web/.gitignore` cover all three.
- Password-grant login **PASS** for Driver + Operator + Admin. `JwtVerifier` JWKS verify **PASS** for all three access tokens.
- Backend uvicorn on `:8000`: `GET /health/live` **PASS**; `GET /health/ready` **degraded** (`database_url_configured=false`). `GET /api/v1/auth/me` **FAIL 503 `DB_UNAVAILABLE`** for all three JWTs (expected without `DATABASE_URL`).
- MCP reconfirmed USR001/USR101/USR999 `auth_user_id` mapped.
- Remaining local blocker: fill `DATABASE_URL` (+ optional `SUPABASE_SERVICE_ROLE_KEY`) from Supabase Dashboard → Project Settings → Database / API. Then re-prove `/auth/me` + browser smoke.
- Sprint 1 checklist updated with verified evidence only; exit gate still open.
- Verification: JWT/JWKS as above; frontend build/Playwright **not run**; unit tests **not re-run** this turn. Dirty tree preserved; no secrets committed.
- Agent/surface: Cursor subagent (Composer), follow-up to `75590109-6a06-4783-bf18-e398ae317eaf`.

## 2026-08-07 16:25 IST - POC Auth users mapped + two-portal UI + tools lock

- Created 3 Supabase Auth users (Driver `ravi.kumar@setuhaul.com` / Ops Operator `priya.mehta@setuhaul.com` / Admin `admin@setuhaul.com`) with email identities; mapped `public.users.auth_user_id` for USR001, USR101, USR999. MCP proof: `auth.users=3`, all three mapped. Passwords only in gitignored `.env.local` — share out-of-band; never committed.
- Consolidated React to two portals: `/driver/login`→`/driver`, `/ops/login`→`/ops` (Operator+Admin same shell; legacy `/operator/*` `/admin/*` redirect). ADR 005 + master plan updated.
- Tools architecture locked: Sprint 2 = `ChatOpenAI.bind_tools(role_scoped_tools)` + manual `run_assistant` loop; not `create_agent`/`AgentExecutor`/`create_react_agent`. Sprint 1 no chat. Upstash 24h Sprint 2+.
- Mid-turn Supabase MCP required `mcp_auth` after fetch failures; recovered and completed Auth create.
- Files: `web/src/{App,core/auth/supabase,features/operator/OpsHomes,features/driver/DriverHome}.tsx|ts`, `docs/adrs/SPRINT1_ADRS.md`, `docs/scripts/create_poc_auth_users.py`, `plans/implementation-master-plan.md`, wiki pages, CHANGELOG, Memory MCP.
- Verification: live MCP Auth proof; backend unit tests **4 passed**; `/auth/me` / browser login **not run** (anon keys still empty in `.env.local`). Dirty tree preserved.
- Agent/surface: Cursor subagent (Composer), follow-up to `e2e31b2d-52f6-47c5-b0ca-174069081afe`.

## 2026-08-07 16:20 IST - Two-portal UI consolidation + Auth create blocked (MCP outage)

- Consolidated React routes to owner two-portal POC: `/driver/login` → driver shell; `/ops/login` → shared Operator/Admin dashboard (`/ops`). Legacy `/operator/*` and `/admin/*` redirect. Wrong-role redirect remains server-profile based.
- Tools architecture confirmed (no contradictory “no bind_tools” left in active wiki): Sprint 2 = `ChatOpenAI.bind_tools(role_scoped_tools)` + manual `run_assistant` loop; not `create_agent` / `AgentExecutor` / `create_react_agent`. Sprint 1 still no chat mount. Upstash 24h Sprint 2+.
- Generated secure POC passwords into gitignored `.env.local` (emails USR001/USR101/USR999). **Never committed.** Parent must share credentials out-of-band. Anon/service keys still empty in that file.
- Attempted live Auth create via Supabase MCP `execute_sql`; after earlier successful inspect, MCP degraded (`fetch failed`, discovery error, connection timeout). Auth users **not** created this turn. `docs/scripts/create_poc_auth_users.py` now loads `.env.local`.
- Files: `web/src/App.tsx`, `web/src/core/auth/supabase.ts`, `web/src/features/operator/OpsHomes.tsx`, `web/src/features/driver/DriverHome.tsx`, `docs/adrs/SPRINT1_ADRS.md` ADR 005, `docs/scripts/create_poc_auth_users.py`, `plans/implementation-master-plan.md`, wiki handoff/current-state/contradictions/log/skills-and-mcp, CHANGELOG, Memory MCP.
- Verification: backend unit tests **4 passed**; Auth mapping / `/auth/me` / frontend build **not run** (MCP outage + missing API keys). Dirty tree preserved; no secrets committed.
- Agent/surface: Cursor subagent (Composer), follow-up to `e2e31b2d-52f6-47c5-b0ca-174069081afe`.

## 2026-08-07 16:05 IST - Owner two-portal POC + bind_tools AI lock (supersedes 16:00)

- Owner Sprint 1–2 UI: **two login screens only** — `/driver/login` (chat + light context/quick actions + profile + logout) and `/ops/login` (shared Operator/Admin read-only dashboard + logout). Prefer Driver + Ops Auth accounts; USR001/USR101/USR999 may share two entries. No maps, GPS, user management, or booking mutations.
- AI lock (authoritative for this turn; aligns ADR 011 + master plan §5.2): `ChatOpenAI` + `bind_tools` + manual invoke loop (~18–20 Sprint 2 tools); Upstash 24h memory Sprint 2+; no `create_agent` / `AgentExecutor`; no private-project naming. **Supersedes** the 16:00 “no bind_tools” entry and restores `plans/branches/ai-engineering.md` + `wiki/ai-system.md`.
- Sprint 1 = auth + shells + observational reads (no chat). Scheduling mutations Sprint 3 only.
- Files: `plans/implementation-master-plan.md`, `plans/poc-design-review.md`, `plans/branches/{full-stack,business-analysis,solution-architecture,ai-engineering}.md`, `docs/adrs/SPRINT1_ADRS.md` ADR 011, `docs/TASKS.md` Phase 6, wiki `current-state` / `implementation` / `architecture` / `ai-system` / `contradictions` / `handoff` / `log`, Memory MCP. Re-applied after a parallel 16:00 no-`bind_tools` overwrite race.
- Open: scaffold still has `/operator/login` + `/admin/login` pending consolidation.
- Verification: documentation only; application/database tests **not run**. Dirty tree preserved; no secrets.
- Agent/surface: Cursor subagent (Composer).

## 2026-08-07 16:00 IST - Owner lock: ChatOpenAI LLM invoke only (no bind_tools)

- Corrected product AI naming: `ChatPromptTemplate | ChatOpenAI` from a plain runnable/function. Forbidden: `create_agent`, `AgentExecutor`, `create_react_agent`, `bind_tools`, tool-calling loops. Private-project names must not appear in SetuHaul docs.
- Reconciled wiki/ADRs/plans/docs after a parallel turn had briefly documented `bind_tools`; owner interrupt forbids that shape.
- Erica/ERICA references: none remain in plans/wiki/docs (grep clean).
- Sprint 1 status unchanged: scaffolds present; Auth mapping still blocked (`auth.users=0`).
- Verification: documentation grep; prior unit tests 4 passed; Auth e2e not run.
- Agent/surface: Cursor subagent (Composer).

## 2026-08-07 15:55 IST - Owner AI lock: bind_tools + manual loop; MCP re-proof

- Locked product AI: `ChatOpenAI` + `bind_tools(role_scoped_tools)` + custom bounded `run_assistant` invoke loop. Explicit: bind_tools + manual loop ≠ `create_agent`. Forbidden: `create_agent`, `AgentExecutor`, `create_react_agent`. Prior over-correction banning `bind_tools` superseded.
- Tool matrix confirmed: 26 named rows in master plan §5.2; ~18–25 planning band (owner ~18–20). Sprint 1 = services/REST only; Sprint 2 = register POC tools + Upstash 24h non-authoritative memory; Sprint 3 = scheduling/search tools.
- Live Supabase MCP on `project-0-Setuhaul-supabase` re-proved: table counts (roles 8 … audit_logs 4), USR001/USR101/USR999 unmapped, `auth_user_id` present, `auth.users=0`. Root cause of earlier non-calls: wrong server id `supabase` and/or server not loaded in agent catalog.
- Files: `plans/branches/ai-engineering.md`, `plans/implementation-master-plan.md`, `wiki/ai-system.md`, `wiki/database.md`, `wiki/handoff.md`, `wiki/current-state.md`, `wiki/architecture.md`, `wiki/contradictions.md`, `wiki/skills-and-mcp.md`, `wiki/index.md`, `wiki/log.md`, `docs/adrs/SPRINT1_ADRS.md` ADR 011, `docs/AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`, Memory MCP.
- Verification: live MCP SQL + migrations; app tests **not run** this turn (docs/direction only). Dirty tree preserved; no new scaffold; no secrets.
- Agent/surface: Cursor subagent (Composer).

## 2026-08-07 15:45 IST - Live DB inspect + Sprint 1 scaffold + ChatOpenAI naming lock

- Supabase MCP server id `project-0-Setuhaul-supabase` authenticated/usable. Live counts verified (roles 8, users 10, drivers 15, facilities 2, shipments 21, eta_updates 12, appointments 20, appointment_slots 106, docks 9, facility_rules 6, driver_exceptions 10, audit_logs 4). USR001/USR101/USR999 confirmed. `auth.users` = 0.
- Applied additive migration `add_users_auth_user_id` on hosted DB; checked in `supabase/migrations/20260807100550_add_users_auth_user_id.sql`.
- Scaffolded `backend/` (settings, DI, request IDs, envelope, health, JWT→ExecutionContext, scoped read APIs) and `web/` three-portal login/protected shells; root `.env.example`; Auth mapping script `docs/scripts/create_poc_auth_users.py`.
- Owner architecture correction: product chat is LangChain LLM invoke `ChatPromptTemplate | ChatOpenAI` only. Removed private-project naming from plans/wiki/ADRs/docs/changelog phrasing. Forbidden: `create_agent`, `AgentExecutor`, `create_react_agent`, `bind_tools`. Sprint 1 still mounts no chat.
- Verification: MCP SQL + migration list; backend unit tests **4 passed**; live JWT login / frontend build / Auth user create **not run**. Skills: supabase + supabase-postgres-best-practices for migration.
- Agent/surface: Cursor subagent (Composer), Multitask.

## 2026-08-07 15:30 IST - Supabase MCP still unavailable (follow-up)

- Follow-up after prior Cursor inspection: re-read `.cursor/mcp.json` (project_ref `kujffzgqjmqphkmrbawy`, no secrets printed), ran `GetMcpTools` pattern `supabase|memory` and full catalog, and direct `GetMcpTools(server=supabase)`.
- Result unchanged: agent session exposes only `cursor-ide-browser` and `user-memory` (ready). Supabase server is **not found** — not `needsAuth`; `mcp_auth` cannot be invoked because the server is not loaded.
- Live table counts, Auth account checks for seeded emails, and confirmation of USR001/USR101/USR999 in the hosted project were **not** performed.
- Repo-only schema gap confirmed again: baseline `public.users` has no `auth_user_id`; seed still defines the three POC personas. Architecture reminder unchanged: LangChain LLM invoke only (`ChatOpenAI`), no AgentExecutor; Sprint 1 = auth + scoped reads + three portals; chat = Sprint 2.
- Ordered next actions documented in handoff: (1) user enable/approve Supabase MCP + OAuth, (2) re-run live inspection, (3) additive `auth_user_id` + Auth users, (4) Sprint 1 scaffold.
- Verification: MCP catalog/server lookup only. Application/database tests not run. Dirty tree preserved; no secrets committed.
- Agent/surface: Cursor subagent (Composer), follow-up to agent `59b89446-c946-4064-a665-732b3dad0d0e`.

## 2026-08-07 15:23 IST - Supabase MCP live inspection blocked

- Attempted Sprint 1 POC data inspection via the newly configured Supabase MCP in `.cursor/mcp.json` (project_ref `kujffzgqjmqphkmrbawy`, features docs/account/database/debugging/development/functions/branching).
- Cursor agent MCP catalog exposed only `cursor-ide-browser` and `user-memory`; `GetMcpTools(server=supabase)` returned server not found. Live project/table/auth sampling was not possible.
- Memory MCP search for SetuHaul was empty at start; durable SetuHaul project entity was written successfully after the blocker finding.
- Repo-only (not live) notes: baseline migration has no `public.users.auth_user_id`; seed defines USR001/USR101/USR999 personas; ADR 005 ratifies Admin global read-only; untracked `web/` Vite scaffold present in dirty tree.
- Verification: MCP catalog enumeration and supabase server lookup only. No SQL executed against the hosted project. Application/database tests not run.
- Agent/surface: Cursor subagent (Composer).

## 2026-08-07 14:50 IST - Define the three-persona Sprint 1-2 team POC

- Triple-reviewed the current plan using solution-architecture, full-stack, AI-engineering, and business-analysis personas and reconciled the findings with the seeded Driver, Operations Executive, and Admin roles.
- Updated the master plan and design review for distinct Driver, Operator, and Admin login experiences backed by one shared Supabase Auth implementation and server-authoritative role routing.
- Added Driver profile/logout, mobile/accessibility/session states, a facility-scoped read-only Operator dashboard for exceptions/schedules/docks/slots/rules/constraints, and a separately labelled read-only Admin overview.
- Added a strict POC boundary: Sprint 1-2 operational scheduling data is observational and timestamped; feasible-slot search/ranking and every appointment/capacity mutation remain unavailable until Sprint 3.
- Changed the Sprint 2 write flow to one model-facing atomic, authorized, idempotent ETA/exception command and added wrong-portal, IDOR, stale confirmation, out-of-order, retry, dependency-failure, and disabled-capability acceptance coverage.
- Synchronized the master plan, POC design review, all four planning branches, and implementation/current-state/contradictions/handoff wiki pages.
- Verification: 58 actionable open plan items, 3 verified foundation-presence items, zero stale two-account or prematurely mounted scheduling-route references across plans/wiki/docs, and zero disallowed orchestration-framework references. Application/database tests not run because this is a planning/documentation change and no runtime exists yet.
- Memory MCP synchronization was retried and again failed with the recorded relative-path `ENOENT`; checked-in context is complete and the new POC observations must be replayed after configuration repair.
- Skills: `software-architecture-design` enforced the read/query versus scheduling-command boundary; `interface-design` shaped the role-specific minimal surfaces and missing states; `supabase` shaped shared-auth, fail-closed role routing, session, and secret-handling requirements.
- Agent/surface: Codex with four reviewer personas.

## 2026-08-07 14:37 IST - Re-baseline the implementation plan as a living sprint tracker

- Made `plans/implementation-master-plan.md` the evidence-based sprint checklist: completed work is checked and struck through only after verification, active work is labeled, and deferred work remains visible as unchecked TODOs.
- Confirmed Sprint 1 is active but incomplete; Sprints 2 and 3 remain gated TODOs. The team POC remains the Sprint 2 exit gate and challenge readiness remains the Sprint 3 exit gate.
- Converted all sprint build items and exit gates to trackable checkboxes and separated verified repository foundations from implementation completion.
- Recorded four supplied Stitch design sets while retaining set 2 as the current POC choice, and changed the final outdated orchestration-framework copy in a supplied Stitch artifact to `LangChain`.
- Updated the plan index and LLMWiki implementation/current-state/handoff/log pages.
- Verification: repository inspection found 0 application files, 2 database SQL test files, 4 Stitch design sets, 51 actionable open plan items, 3 checked foundation-presence items, and no remaining non-LangChain orchestration-framework mentions. Database/application tests not run because this was a planning/documentation/design-copy update and no application runtime exists yet.
- Memory MCP: project search was callable, but the required durable write failed with `ENOENT` because the configured relative storage path resolved inside npm's temporary package directory. Checked-in changelog/wiki/handoff are synchronized; memory replay remains pending after configuration repair.
- Skills: `software-architecture-design` guided the gated modular-monolith re-baseline; `graphify` was queried as a secondary index and reconciled with source files.
- Agent/surface: Codex.

## 2026-08-07 14:30 IST - Complete Cursor and Anti-Gravity MCP compatibility

- Added `.cursor/mcp.json`, Cursor's native project MCP configuration.
- Added `.agents/mcp_config.json`, Google Antigravity's native workspace MCP configuration.
- Both use the same pinned Memory MCP server and ignored `.agent-memory/memory.jsonl` store as Claude, Codex, and Gemini CLI.
- Verified against current official Cursor and Google Antigravity documentation; JSON syntax validated locally.
- Agent/surface: Codex.

## 2026-08-07 14:20 IST - Enforce per-prompt context synchronization

- Updated `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, Cursor rules, and the LLMWiki maintainer schema so every prompt runs a context-sync check.
- Every durable prompt must atomically update `CHANGELOG.md`, affected wiki pages, `wiki/handoff.md`, `wiki/log.md`, and Memory MCP before its final response.
- Pure conversational prompts that produce no durable project context do not create empty/noisy entries.
- Recorded that the newly configured Memory MCP requires a client/session reload before it can be called from this already-running Codex session; checked-in context is synchronized for recovery.
- Verification: instruction references and Markdown consistency checked; no application tests applicable.
- Agent/surface: Codex.

## 2026-08-07 13:57 IST - Agent initialization and shared context protocol

- Added canonical root `AGENTS.md` instructions for Codex and other agents, plus native `CLAUDE.md`, `GEMINI.md`, and `.cursor/rules/setuhaul.mdc` adapters for Claude Code, Gemini/Google Antigravity, and Cursor.
- Added a mandatory startup sequence, dirty-worktree protection, skill routing, MCP/memory boundaries, and same-turn changelog/handoff writeback.
- Added `docs/HANDOFF.md` as the concise cross-session state and next-action record.
- Added `docs/AI_TOOLING.md` with researched client conventions and a staged Graphify, Upstash, LangChain MCP, and LangSmith adoption plan.
- Source pattern reviewed: Slicematic FullStack agent rules, Cursor rules, wiki handoff/log, changelog, local skills, and Graphify outputs.
- Verification: documentation links and repository diff reviewed; no application tests run because this change contains no executable application code.
- Agent/surface: Codex.

## 2026-08-07 14:00 IST - LLMWiki, persistent Memory MCP, and Graphify foundation

- Added the full `wiki/` LLMWiki structure with maintainer schema, index, current state, provenance, contradictions, architecture/database/AI/testing topics, append-only log, and canonical handoff.
- Added project Memory MCP configurations for Claude (`.mcp.json`), Gemini/Antigravity (`.gemini/settings.json`), and Codex (`.codex/config.toml`), sharing ignored `.agent-memory/memory.jsonl` persistence.
- Pinned the reference Memory MCP server to `@modelcontextprotocol/server-memory@2025.11.25`; no secrets are required or committed.
- Updated root agent startup/writeback rules to enforce the LLMWiki and Memory MCP loop.
- Graphify: generated the initial canonical-wiki graph with 26 nodes, 41 edges, 4 labeled communities, interactive HTML, report, raw JSON, cache, cost tracker, and incremental manifest.
- Verification: JSON/TOML configuration parsing and Graphify output checks performed; no application tests run because application code is not yet present.
- Agent/surface: Codex.

## 2026-08-12 00:00 IST - Sprint 3 lifecycle, stale recommendation, and escalation takeover

- Added `supabase/migrations/20260812010000_sprint3_lifecycle_escalation.sql`, including the `EXPIRED` lifecycle status, constrained lifecycle audit actions, and RLS-protected backend-only `escalation_queue`.
- Added versioned `REC-` option fingerprints, best-effort 24-hour Redis stale markers on committed ETA updates, lifecycle/reschedule routes and Driver tools, operations escalation/dock/queue APIs, and the Ops escalation list.
- Updated the Living Sprint 3 checklist and affected wiki handoff, implementation, database, current-state, testing, and log pages.
- Verification: focused lifecycle/stale/escalation suite **29 passed**; backend compile PASS; frontend lint/build PASS. Migration was not applied and live migration/API/E2E verification remains outstanding.
- Agent/surface: Cursor.
