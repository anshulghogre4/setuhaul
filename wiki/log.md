---
title: SetuHaul Wiki Operation Log
type: log
status: append-only
scope: wiki
last_updated: 2026-08-07
---

# Wiki log

## 2026-08-12 02:40 IST | implementation | 5 New Database Tools, Kwargs Unpacking Fix & Driver UI Typing Animation

- Added 5 new database-backed tools (`get_vehicle_and_carrier_details`, `get_gate_and_queue_status`, `get_facility_rules_and_restrictions`, `report_vehicle_breakdown_or_incident`, `get_dock_maintenance_alerts`) in `driver_reads.py` and `tools.py`.
- Fixed `TypeError` in `tools.py` for unpacked keyword arguments from LangChain `StructuredTool.from_function`.
- Fixed tool loop termination in `run_assistant.py` on `CONFIRMATION_REQUIRED` and `PERSISTED` to guarantee non-empty responses.
- Added animated typing indicator bubble in `DriverHome.tsx` and keyframe styles in `App.css`.
- Verification: 48 backend unit tests PASS (`PYTHONPATH=. pytest tests/unit`); Vite build PASS (`built in 588ms`); Live assistant execution verified for all 5 new tools (**200 OK**).

## 2026-08-10 23:21 IST | query | Login preflight hang

- Stuck `/api/v1/auth/me` preflight was caused by dead/crashed backend venv, not duplicate frontend auth calls.
- Backend restarted healthy; CORS OPTIONS verified. Sprint status unchanged.

## 2026-08-10 23:12 IST | ingest | POC roster moved to local share file

- Team share file: gitignored `POC_TEAM_ACCOUNTS.local.md` (all 8 roles × 14 users + 3 shared passwords).
- Cleared POC credentials from `.env` / `.env.local`. No passwords in wiki.
- Sprint status unchanged.

## 2026-08-10 23:05 IST | ingest | Full Auth inventory + remove reset script

- Created Auth for USR102–USR106 using existing role-shared `.env.local` passwords; live `auth.users=14` all mapped.
- Expanded ops portal/permissions for deferred roles; deleted `docs/scripts/create_poc_auth_users.py`.
- Updated [[database]] full inventory table. No passwords in wiki.
- Verification: password-grant PASS; execution_context unit tests PASS (6). Sprint 3 status unchanged.

## 2026-08-10 22:39 IST | configuration | Local Gemini key and Flash Latest default

- Stored the provided Gemini key in gitignored `.env.local`, selected `LLM_PROVIDER=gemini`, and set `LLM_MODEL=gemini-flash-latest`.
- Updated the backend Gemini default and active docs from `gemini-2.5-flash` to `gemini-flash-latest` after Google REST reported older pinned Flash models unavailable to this key.
- Verification: LLM factory unit tests PASS, direct Gemini REST smoke PASS. LangChain live invoke timed out locally and remains a restart/recheck item.

## 2026-08-10 22:31 IST | implementation | Authenticated ops dashboard polish

- Refined `frontend/src/features/operator/OpsHomes.tsx`, `frontend/src/layouts/ProtectedLayout.tsx`, and `frontend/src/App.css` for a more enterprise-looking authenticated ops dashboard and profile menu.
- Preserved the POC boundary: no maps, no user management, no scheduling mutation controls, and no invented operations data.
- Verification: frontend lint/build PASS; local frontend and backend readiness checks PASS; live Arvind Nair login/profile/ops summary/exceptions API checks PASS. Headless screenshot capture was attempted but blocked by local command policy.

## 2026-08-10 22:20 IST | correction | Redis-only memory architecture

- Owner clarified that SetuHaul has no project Memory MCP; Redis is the only memory layer and is limited to application conversation/session memory.
- Removed Memory MCP server configs and preserved Cursor Supabase MCP only.
- Updated active agent instructions, tooling docs, and wiki topic pages to stop requiring Memory MCP startup/writeback or degraded-memory handoff notes.
- Verification: documentation/config change only; app tests not run.

## 2026-08-10 22:11 IST | operations | Extra POC Auth accounts and Redis env

- Created six additional live Supabase Auth POC accounts for real-name Driver, Ops, and Admin personas, mapped them to `public.users.auth_user_id`, and verified password-grant login status `200` for each.
- Added gitignored local env files for backend/frontend execution. Root env includes Supabase + Upstash Redis REST configuration; frontend env contains only browser-safe Vite values.
- Verified Upstash Redis through REST (`/ping`, short-lived set/get). `redis-cli` is unavailable in this sandbox. No app tests run because this was credential/data setup only.

## 2026-08-10 18:29 IST | ingest | Role-specific login hero assets

- Added generated Driver portal hero `frontend/src/assets/setuhaul-driver-eta-hero.png` and updated `LoginForm` so Driver and Ops login screens use distinct imagery, copy, and metrics.
- Ops continues to use `frontend/src/assets/setuhaul-dock-command-hero.png`; Driver now focuses on ETA/exception reporting and single-truck context.
- Verification: `npm run lint` PASS; `npm run build` PASS; screenshots `tmp/ui-polish/driver-login-role-hero.png` and `tmp/ui-polish/ops-login-role-hero.png` visually spot-checked. Sprint status unchanged.

## 2026-08-10 18:22 IST | ingest | Generated login hero asset

- Replaced the weak abstract/fake-map login right panel with a generated dock-command hero image saved as `frontend/src/assets/setuhaul-dock-command-hero.png`.
- Updated `LoginForm` and `App.css` so the image carries the visual while overlay copy and classroom-scale metrics remain readable.
- Verification: `npm run lint` PASS; `npm run build` PASS; `tmp/ui-polish/driver-login-dock-hero.png` visually spot-checked. Sprint status unchanged.

## 2026-08-10 18:12 IST | ingest | Frontend UI polish

- Implemented UI polish in `frontend/src/App.css`, `frontend/src/index.css`, `frontend/src/features/auth/LoginForm.tsx`, `frontend/src/features/driver/DriverHome.tsx`, `frontend/src/features/operator/OpsHomes.tsx`, and `frontend/src/layouts/ProtectedLayout.tsx`.
- Scope stayed within the two-portal POC: login aesthetics, structured driver context, ops metric/status presentation, typography, shell layout, and hook warning cleanup; no booking, map/GPS, user-management, or scheduling mutation behavior added.
- Verification: `npm run lint` PASS; `npm run build` PASS; unauthenticated login screenshots captured and visually checked. Authenticated screens not live-smoked because local env files are absent and pasted secrets were not persisted.

## 2026-08-10 17:51 IST | query | FDE challenge PDF analysis

- Analyzed `docs/SetuHaul_FDE_Challenge.pdf` across all 20 pages; rendered representative pages 1, 10, and 18.
- Durable conclusion: the brief leaves implementation choices open, but FDE challenge readiness requires Sprint 3 evidence for deterministic feasibility, allocation semantics, same-slot competition, stale option handling, idempotent retries, and no-feasible-slot escalation.
- Updated [[implementation]], [[current-state]], [[handoff]], and CHANGELOG. Checked-in context is authoritative.

## 2026-08-08 13:45 IST | ingest | Rename web â†’ frontend

- Directory `web/` renamed to `frontend/`; CI/README/package updated; build PASS. Updated [[handoff]], CHANGELOG, master-plan scaffold wording.

## 2026-08-08 13:35 IST | ingest | Root GET / health ping

- FastAPI `GET /` returns alive JSON; README Quick start note. Smoke PASS. Updated [[handoff]], CHANGELOG.

## 2026-08-07 20:25 IST | verify | Gemini live PASS

- Google key saved gitignored; `gemini-2.5-flash` invoke PASS via `ChatGoogleGenerativeAI`. All three providers live-verified. Updated [[handoff]], [[current-state]], CHANGELOG, Memory.

## 2026-08-07 20:20 IST | verify | OpenAI+OpenRouter smoke; Gemini native class

- Live invoke: OpenAI PASS, OpenRouter PASS; Gemini key was OpenAI-shaped (FAIL). Switched Gemini to `ChatGoogleGenerativeAI`. Unit 20 passed. Updated [[handoff]], [[ai-system]], [[current-state]], CHANGELOG, Memory.

## 2026-08-07 20:00 IST | ingest | README + multi-provider LLM

- README Quick start for Sprint 1â€“2 POC; demo login emails + password env-var names (passwords OOB).
- `assistant/llm.py` ChatOpenAI factory (`auto` OpenAI â†’ OpenRouter â†’ Gemini); settings + `.env.example` extended.
- Unit 18 passed; OpenRouter/Gemini live smoke pending keys. Updated [[handoff]], [[current-state]], [[ai-system]], CHANGELOG, Memory MCP.

## 2026-08-07 19:35 IST | ingest | Sprint 2 exit gate COMPLETE

- Struck Sprint 2 Living Â§7 build + exit gate with API `DEMO_PATH_PASS` and browser localhost:5173 evidence.
- Fixed write path (`UPDATE_ETA`, `DELAY`, JWT leeway, tzdata, env BOM, stale uvicorn). Credentials remain gitignored; rotation recommended in [[handoff]].
- Updated [[handoff]], [[current-state]], [[implementation]], [[ai-system]], master plan, root CHANGELOG, Memory MCP.

## 2026-08-07 19:26 IST | verify | Sprint 2 Living re-baseline

- Inspected dirty-tree Sprint 2 code + live smoke. Struck only verified Â§7 items (repair/ETA distinction; services+tools; role allowlists; bind_tools loop).
- Blocker recorded: confirmed ETA write 500 on audit `ETA_UPDATE` vs `UPDATE_ETA`.
- Living â†’ Sprint 2 ACTIVE / IN PROGRESS; exit gate open. Updated [[handoff]], [[current-state]], [[implementation]], master plan, root CHANGELOG, Memory MCP.

## 2026-08-07 18:36 IST | ingest | .gitignore noise reduction

- Ignored `graphify-out/` and common generated/OS/editor artifacts. Secrets/tmp/venv unchanged. Updated [[handoff]], root CHANGELOG.

## 2026-08-07 17:55 IST | verify | Sprint 1 exit gate COMPLETE

- Exit gate struck: Admin browser global RO, wrong-portal, API 401/IDOR/scope, no mutations, CORS both origins, baseline a11y, minimal CI.
- Deferred honestly: deep SQLAlchemy repos; fuller a11y/responsive; CI DB/Docker expansion.
- Living status â†’ Sprint 2 ACTIVE. Updated [[handoff]], [[current-state]], [[implementation]], [[testing]], [[contradictions]], root CHANGELOG, master plan, Memory MCP.

## 2026-08-07 17:04 IST | ingest | Living sprint catch-up + cross-IDE writeback

- Master plan Living status re-baselined; Sprint 1 mostly complete (exit open); Sprint 2 TODO.
- Root `AGENTS.md` + Claude/Gemini/Cursor/wiki pointers require Living status at startup and checklist strikethrough on durable progress.
- Memory MCP synced (16:53 smoke + policy). Updated [[handoff]], [[implementation]], [[current-state]], root CHANGELOG.

## 2026-08-07 16:53 IST | verify | Browser smoke PASS + pooler fix

- Two-portal UI smoke on `localhost:5173`: Driver login â†’ chat shell â†’ logout; Ops login â†’ dashboard.
- Fixed Vite import path, asyncpg `statement_cache_size=0` for PgBouncer, Stitch chat/ops skeleton polish.
- Screenshots: `tmp/poc-screenshots/01`â€“`04` (gitignored). Updated [[current-state]], [[handoff]], [[testing]], root CHANGELOG, Memory MCP.

## 2026-08-07 16:35 IST | verify | /health/ready + /auth/me PASS

- User saved `.env`; `DATABASE_URL` + service role non-empty. Backend ready; DB ping true.
- `/api/v1/auth/me` PASS for USR001 / USR101 / USR999 with expected roles and scopes.
- Updated [[current-state]], [[handoff]], root CHANGELOG, Memory MCP. Browser smoke still TODO.

## 2026-08-07 16:32 IST | verify | Auth/me blocked â€” empty DATABASE_URL on disk

- Proceed: `/health/live` PASS; `/health/ready` degraded; on-disk `DATABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` empty (anon present).
- Settings now loads `.env.local` paths. `/auth/me` not re-proved.
- Updated [[handoff]], root CHANGELOG, Memory MCP.

## 2026-08-07 16:45 IST | verify | Anon keys + JWT/JWKS; auth/me DB blocked

- MCP `get_publishable_keys` / `get_project_url`: anon populated locally (gitignored). Service role + `DATABASE_URL` **not** available via MCP.
- Password-grant + `JwtVerifier` JWKS **PASS** (Driver/Operator/Admin). `/health/live` PASS; `/auth/me` FAIL 503 `DB_UNAVAILABLE`.
- Updated [[current-state]], [[handoff]], [[implementation]], [[testing]], master plan Sprint 1 evidence notes, root CHANGELOG, Memory MCP.
- Sprint 1 exit gate still open pending `DATABASE_URL` + browser smoke.

## 2026-08-07 16:25 IST | ingest | Auth mapped + two-portal UI

- Live MCP after re-auth: created 3 Auth users + identities; mapped USR001/USR101/USR999 `auth_user_id`. Proof: `auth.users=3`, all mapped.
- Web consolidated to `/driver/login` + `/ops/login`; Operator+Admin share `/ops`. AI lock: `ChatOpenAI` + `bind_tools` + manual loop.
- Passwords only in gitignored `.env.local` (OOB). Anon keys still empty â†’ `/auth/me` not run.
- Updated [[current-state]], [[contradictions]], [[handoff]], [[skills-and-mcp]], [[database]], root CHANGELOG, Memory MCP.
- Verification: MCP SQL proof + backend unit tests 4 passed; JWT e2e not run.

## 2026-08-07 16:20 IST | ingest | Two-portal UI code + Auth create blocked

- Consolidated `web/src` to `/driver/login` + `/ops/login` / `/driver` + `/ops`; Operator+Admin share ops shell; legacy aliases redirect. ADR 005 + master plan checklist updated.
- AI lock unchanged: `ChatOpenAI` + `bind_tools` + manual loop (ADR 011 / [[ai-system]]); no Erica.
- Auth: passwords in gitignored `.env.local`; create/map **not** completed â€” Supabase MCP `fetch failed` / connection timeout. Script loads `.env.local`.
- Updated [[current-state]], [[contradictions]], [[handoff]], [[skills-and-mcp]], root CHANGELOG, Memory MCP.
- Verification: backend unit tests 4 passed; Auth e2e / `/auth/me` not run.

## 2026-08-07 16:05 IST | scope | Two-portal POC + bind_tools reconcile

- Owner POC UI: `/driver/login` + `/ops/login`; shared ops dashboard; prefer Driver + Ops accounts.
- AI: restored `ChatOpenAI` + `bind_tools` + manual loop (ADR 011). Supersedes 16:00 no-`bind_tools` interrupt for this writeback.
- Complementary MCP diagnosis already in [[database]]: Cursor server id `project-0-Setuhaul-supabase` (not config key `supabase`); live counts + auth.users=0 re-proved ~15:55.
- Updated [[current-state]], [[implementation]], [[architecture]], [[ai-system]], [[contradictions]], [[handoff]], plans (master/design-review/branches), root CHANGELOG, Memory MCP.
- Scaffold three-login routes remain an open contradiction until code consolidates.
- Verification: docs + prior live MCP; app tests not run.

## 2026-08-07 16:00 IST | decision | ChatOpenAI LLM invoke only (no bind_tools)

- Owner interrupt: conversational LLM is `ChatPromptTemplate | ChatOpenAI` only; no `bind_tools` / agent loops; no private-project naming.
- Updated [[ai-system]], [[architecture]], [[handoff]], [[current-state]], [[contradictions]], [[index]], [[skills-and-mcp]], ADR 011, plans/docs.
- Sprint 1 scaffolds remain; Auth mapping still the blocker.

## 2026-08-07 15:55 IST | decision | ChatOpenAI+bind_tools lock + MCP re-proof

- Owner clarification: tools via `ChatOpenAI.bind_tools` + manual invoke loop; not create_agent. Upstash 24h non-authoritative memory from Sprint 2. Tool matrix ~18â€“25 / 26 named with sprint placement.
- [[ai-system]], [[architecture]], [[contradictions]], [[current-state]], [[handoff]], [[database]], [[skills-and-mcp]], [[index]] updated; Erica absent (already stripped).
- Live MCP `project-0-Setuhaul-supabase`: counts + auth_user_id + auth.users=0. Earlier failures = wrong server name / not loaded.
- Verification: MCP SQL; app tests not run.

## 2026-08-07 15:45 IST | ingest | Live DB + Sprint 1 scaffold + ChatOpenAI lock

- Live MCP inspection recorded in [[database]]; [[current-state]] and [[handoff]] refreshed.
- [[ai-system]] / [[architecture]] / [[contradictions]]: LLM invoke is `ChatPromptTemplate | ChatOpenAI`; no agent loops; no private-project naming.
- Sprint 1 scaffolds in repo; Auth mapping still blocked (`auth.users` empty).
- Verification: MCP SQL; unit tests 4 passed; e2e not run.

## 2026-08-07 15:30 IST | blocker | Supabase MCP still not loaded (follow-up)

- Re-checked `.cursor/mcp.json` (project_ref only; no secrets printed) and MCP catalog via pattern `supabase|memory`, full catalog, and server=`supabase`.
- Catalog still: `cursor-ide-browser`, `user-memory` only. Supabase not found â€” cannot `mcp_auth`. Live counts/Auth/persona verification still blocked.
- Repo-only: baseline `users` lacks `auth_user_id`; seed defines USR001/USR101/USR999. Sprint 1 ordered next steps refreshed in [[handoff]].
- Updated [[handoff]], [[current-state]], [[skills-and-mcp]], [[database]], root CHANGELOG; Memory MCP observations appended.
- Verification: MCP enumeration only. Tests not run.

## 2026-08-07 15:23 IST | blocker | Supabase MCP not loaded in Cursor

- Inspected `.cursor/mcp.json`: Supabase remote MCP URL present with project_ref `kujffzgqjmqphkmrbawy`.
- Agent MCP catalog lacked `supabase`; live project/table/auth inspection stopped per policy.
- Memory MCP: empty SetuHaul search; project entity write succeeded.
- Repo-only: baseline lacks `auth_user_id`; seed personas USR001/USR101/USR999; ADR 005 Admin global RO; untracked `web/` scaffold in dirty tree.
- Updated [[handoff]], [[current-state]], [[skills-and-mcp]], root CHANGELOG.

## 2026-08-07 15:50 IST | scope | Owner two-portal POC contract

- Owner vision locked for Sprint 1â€“2 UI: `/driver/login` â†’ chat/profile/logout; `/ops/login` â†’ one read-only ops dashboard for Operator (facility) and Admin (global RO). Prefer Driver + Ops Auth accounts; three seed personas may share two entries.
- Explicitly out of POC: maps, GPS, user management, booking mutations. Scheduling mutations remain Sprint 3.
- AI locks aligned: `ChatOpenAI` + `bind_tools` + manual loop; no `create_agent` / `AgentExecutor`; Upstash 24h in Sprint 2; Sprint 1 = auth + shells + reads.
- Updated master plan, POC design review, full-stack/business-analysis/solution-architecture branches, [[current-state]], [[implementation]], [[architecture]], [[contradictions]], [[handoff]], root CHANGELOG.
- Scaffold still exposes three login routes â€” recorded as open contradiction until code consolidates.
- Verification: docs only; tests not run. Memory MCP write attempted.

## 2026-08-07 14:50 IST | scope | Three-persona Sprint 1-2 POC contract

- Triple-checked the POC through solution-architecture, full-stack, AI-engineering, and business-analysis reviews and verified the seed contains Driver (`ROL001`), Operations Executive (`ROL002`), and Admin (`ROL008`) identities.
- Expanded Sprint 1-2 to distinct Driver/Operator/Admin portal entry screens sharing one Supabase Auth implementation; added server-authoritative routing, safe profile/logout, read-only Operator schedule/dock/rule views, and a read-only Admin overview.
- Added the boundary that all Sprint 1-2 schedule/dock/slot/constraint visibility is observational and timestamped. Feasibility, booking, rescheduling, cancellation, confirmation, and appointment/capacity mutation remain absent until Sprint 3.
- Added an atomic ETA/exception command, explicit role/scope and failure-state checks, and an end-to-end Driver-to-Operator-to-Admin team-demo gate.
- Verification: 58 actionable open plan items, 3 verified foundation-presence items, zero stale two-account/early-scheduling plan references, and zero disallowed orchestration-framework references. Tests not run because no runtime/schema changed and application code does not yet exist.
- Memory MCP write was retried and failed with the known relative-path `ENOENT`; checked-in context is synchronized and replay remains pending path repair.

## 2026-08-07 14:37 IST | rebaseline | Living implementation sprint tracker

- Re-analyzed the implementation state against checked-in code, the master plan, database artifacts, and supplied designs.
- Converted all three sprint build sections and exit gates into evidence-based checklists: Sprint 1 is active/incomplete; Sprints 2-3 remain gated TODOs; no sprint is struck through.
- Preserved post-Sprint-3 scope as explicit unchecked `TODO (DEFERRED)` entries and recorded the distinction between present foundation files and executed/verified implementation.
- Found four Stitch design sets and retained set 2 as the current POC decision; corrected the final outdated supplied-design orchestration reference to LangChain.
- Verification: 0 application files, 2 database SQL test files, 4 design sets, 51 actionable open plan items, 3 checked foundation-presence items, and 0 remaining non-LangChain orchestration-framework mentions. Tests not run because no application runtime exists and no database behavior changed.
- Memory MCP degradation: search was callable, but write failed with `ENOENT` because the relative storage path resolved under npm's temporary package directory. Checked-in context is complete; memory replay is pending configuration repair.

## 2026-08-07 14:30 IST | configure | Cursor and Antigravity MCP compatibility

- Verified current native discovery rules: Cursor uses `.cursor/mcp.json`; Google Antigravity uses workspace `.agents/mcp_config.json` and reads `GEMINI.md`/`AGENTS.md`.
- Added both Memory MCP files with the same pinned server and ignored shared JSONL path used by Claude, Codex, and Gemini CLI.
- Result: instruction and Memory MCP configuration now cover Anti-Gravity, Cursor, Codex, Claude, and Gemini CLI.

## 2026-08-07 14:20 IST | rules | Per-prompt atomic context synchronization

- Updated root and native client rules so every prompt runs a context-sync check.
- Durable prompts must update affected wiki pages, [[handoff]], this log, root `CHANGELOG.md`, and Memory MCP before the final response.
- Pure no-op/read-only conversation does not create empty history entries.
- Memory MCP was not callable inside the current already-running Codex session; recorded the required next-session retry in [[handoff]].

## 2026-08-07 14:00 IST | ingest | LLMWiki, Memory MCP, and Graphify initialization

- Compiled initial project knowledge from `PROJECT.md`, plans, docs, Supabase artifacts, and the Slicematic LLMWiki pattern.
- Added [[index]], [[current-state]], [[source-map]], [[contradictions]], system topic pages, [[handoff]], and this operation log.
- Added cross-client Memory MCP configuration with ignored local persistence.
- Completed the initial Graphify build from 13 canonical wiki documents: 26 nodes, 41 edges, 4 labeled communities, plus HTML/report/JSON and incremental manifest.
## 2026-08-10 18:55 IST | implementation | Sprint 3 constraints registry

- Added `backend/app/scheduling/constraints.json` as the single editable scheduling policy source for authority boundaries, feasibility hard constraints, deterministic ranking, lifecycle semantics, option invalidation, no-slot escalation, Redis boundaries, and write-safety rules.
- Added strict Pydantic loader `backend/app/scheduling/constraints.py` and unit coverage in `backend/tests/unit/test_scheduling_constraints.py`.
- Updated [[current-state]], [[implementation]], [[ai-system]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard. Sprint 3 is now IN PROGRESS; no exit gate or allocator item was struck because deterministic feasibility/allocation is not complete.
- Verification: backend unit tests PASS, 25 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; `git diff --check` PASS with only an existing CRLF warning on `CHANGELOG.md`.
-
## 2026-08-10 19:12 IST | implementation | LangChain feasible slot search

- Added `backend/app/scheduling/feasibility.py` for deterministic Sprint 3 slot feasibility/ranking using checked constraints, latest ETA, facility hours, slot/dock compatibility, active appointments, dock events, and no-slot escalation payloads.
- Added `backend/app/api/v1/routers/scheduling.py` with `GET /api/v1/shipments/{shipment_id}/slots/feasible`, wired the router into `backend/app/main.py`, and registered `find_feasible_slots` in `backend/app/assistant/tools.py`.
- Updated the assistant prompt so slot search is enabled as informational non-reserved options while booking/hold/reschedule/cancel/confirm mutations remain disabled.
- Verification: backend unit tests PASS, 30 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:31 IST | implementation | Transactional request_slot flow

- Added `backend/app/scheduling/allocation.py` with `request_slot`: idempotency lookup/store, driver ownership checks, row locks, slot revalidation, `PENDING_CONFIRMATION` insert, `BOOK_APPOINTMENT` audit, commit, and authoritative reread.
- Extended `backend/app/api/v1/routers/scheduling.py` with `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request` requiring `Idempotency-Key`, and registered the Driver LangChain `request_slot` tool.
- Updated the assistant prompt so exact selected slot requests are enabled as pending confirmation only; reschedule/cancel/confirm remain disabled.
- Verification: backend unit tests PASS, 33 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and concurrency tests not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:38 IST | implementation | Appointment request status read path

- Added `get_appointment_request_status` in `backend/app/scheduling/allocation.py` for scope-safe, read-only status checks after `request_slot`.
- Exposed `GET /api/v1/shipments/{shipment_id}/appointment-request/status` and registered the Driver LangChain `get_appointment_request_status` tool.
- Updated the assistant prompt so pending confirmation remains distinct from confirmed booking, and updated [[current-state]], [[implementation]], [[ai-system]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 35 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and concurrency tests not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:50 IST | implementation | Allocation race conflict mapping

- Hardened `request_slot` so PostgreSQL allocation partial unique violations for `ux_active_appointment_per_slot` and `ux_current_active_appointment_per_shipment` return `SLOT_CONFLICT_REFRESH_REQUIRED` instead of raw database errors.
- Updated the scheduling route to return HTTP 409 for conflict-refresh outcomes while preserving refreshed options in the response body.
- Added unit coverage for allocation unique-constraint translation and updated [[current-state]], [[implementation]], [[database]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 38 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and real parallel contention tests not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:59 IST | implementation | Redis conversation memory tool

- Added `ConversationMemory.snapshot(...)` for bounded current-thread Upstash Redis session/history snapshots with explicit 24-hour TTL, non-authoritative status, and degraded-state reporting.
- Registered Driver LangChain `get_conversation_memory` and passed the existing assistant memory instance into the tool builder.
- Updated the assistant prompt to use Redis only for chat/session continuity and to verify operational facts through PostgreSQL-backed tools.
- Updated [[current-state]], [[ai-system]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 40 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live Upstash smoke not run because Redis env values are not configured/persisted.
## 2026-08-10 20:16 IST | implementation | Deterministic slot ranking algorithm

- Upgraded `find_feasible_slots` from earliest feasible slot ordering to explicit deterministic scoring.
- Added `rank_score` and `ranking_factors` for priority, lateness, wait after ETA, fit slack, dock match, operational disruption score, and stable shipment/slot tie-breaker.
- Added editable `ranking_policy.priority_scores` and `ranking_policy.score_weights` to `backend/app/scheduling/constraints.json` so ranking behavior can change without scattering constants across services.
- Updated scheduling feasibility/constraints unit coverage and synchronized [[current-state]], [[implementation]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 41 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and real parallel contention tests not run.
## 2026-08-10 20:23 IST | verification | Live Supabase database catalog inspection

- Connected to the live Supabase PostgreSQL database through direct read-only asyncpg and inspected public schema metadata plus seeded operational counts.
- Verified PostgreSQL 17.6, `auth.users=3`, public schema 23 tables and 4 views.
- Verified key seeded counts: `shipments=21`, `appointment_slots=106`, `appointments=22`, `driver_exceptions=12`, `eta_updates=14`, `docks=9`, `facilities=2`, `users=10`, `roles=8`, and `idempotency_requests=2`.
- Confirmed Sprint 3-relevant live state: open/blocked slot inventory, current confirmed and pending-confirmation appointments, active exceptions, and allocation guard indexes `ux_active_appointment_per_slot` + `ux_current_active_appointment_per_shipment`.
- No schema, data, grant, RLS, or migration changes were made. Supabase changelog checked; Data API public-table auto-exposure change does not affect this direct Postgres inspection.
## 2026-08-10 20:35 IST | verification | Live same-slot concurrency proof

- Added `backend/tests/integration/test_live_scheduling_concurrency.py`, guarded by `DATABASE_URL` and `SETUHAUL_RUN_LIVE_DB_TESTS=1`.
- The test creates temporary live Supabase `CODX` shipment/slot fixtures, runs two independent async sessions through the real `request_slot` service against the same slot, and verifies exactly one `SLOT_REQUESTED` winner plus one `SLOT_CONFLICT_REFRESH_REQUIRED` loser.
- Verified one active appointment on the contested slot, one booking audit row, two idempotency rows, and zero leftover `CODX` idempotency/appointment/slot/shipment rows after cleanup.
- Added `pytest-asyncio` to `backend/pyproject.toml` and kept generated `backend/uv.lock` for reproducible async integration testing.
- Verification: default backend tests PASS, 41 passed and 1 live integration skipped; explicit live concurrency proof PASS, 1 passed. Supabase changelog checked; no schema/RLS/Data API change made.

## 2026-08-10 22:46 IST | planning | Implementation master plan reconciliation

- Refreshed the Living sprint scoreboard in `plans/implementation-master-plan.md` from the beginning through current UI/auth/Redis/Gemini/scheduling work.
- Struck completed evidence for role-specific login visuals, authenticated Ops dashboard polish, Redis-only application memory clarification, current Gemini default configuration, individual POC Auth users, deterministic feasibility/ranking, fresh non-reserved options, and live two-client same-slot proof.
- Kept Sprint 3 IN PROGRESS and the exit gate open for authenticated scheduling/chat smoke, lifecycle transitions, stale-choice invalidation, no-slot escalation, ops takeover views, broader load proof, enterprise auth hardening, and formal Playwright/CI.
- Updated [[implementation]], [[current-state]], [[handoff]], and root CHANGELOG. No Memory MCP sync is expected; SetuHaul durable context is checked-in docs/source, and Redis is runtime app memory only.
- Verification: documentation-only reconciliation; no application tests run. `git diff --check` run after writeback.

## 2026-08-10 23:01 IST | implementation | Redis session-scoped chat memory

- Added `/api/v1/chat` `session_id` support and returned the normalized session id from `run_assistant`.
- Updated `ConversationMemory` so Upstash Redis history, structured session state, snapshots, and duplicate `client_message_id` checks are scoped by authenticated `user_id`, normalized browser `session_id`, and `thread_id`.
- Updated the Driver UI to create a stable `sessionStorage` session id and send it with chat turns; the id is not an authorization source.
- Updated [[ai-system]], [[implementation]], [[current-state]], [[testing]], [[handoff]], the Living sprint scoreboard, and root CHANGELOG.
- Verification: focused backend tests PASS, 18 passed; full backend tests PASS, 43 passed and 1 skipped; frontend lint PASS; frontend build PASS; `git diff --check` run after writeback.

## 2026-08-10 23:24 IST | implementation | Driver chat env and greeting fix

- Hardened `backend/app/core/settings.py` so `.env` and `.env.local` load from source-relative backend/repo paths, fixing the local chat `No LLM API key configured` state after backend restart.
- Changed Driver chat welcome rendering so it uses the verified live driver context name instead of a stale initial auth-profile name.
- Updated [[current-state]], [[implementation]], [[testing]], [[handoff]], the Living sprint scoreboard, and root CHANGELOG.
- Verification: env smoke PASS from both repo root and `backend/` with `ready_llm=True`/Gemini model visible and no secrets printed; focused backend tests PASS, 14 passed; full backend tests PASS, 43 passed and 1 skipped; frontend lint PASS; frontend build PASS. Stale port-8000 backend process was stopped; local policy blocked hidden restart, so manual backend restart is required before browser retest.
