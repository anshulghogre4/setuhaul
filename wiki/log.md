---
title: SetuHaul Wiki Operation Log
type: log
status: append-only
scope: wiki
last_updated: 2026-08-07
---

# Wiki log

## 2026-08-10 18:29 IST | ingest | Role-specific login hero assets

- Added generated Driver portal hero `frontend/src/assets/setuhaul-driver-eta-hero.png` and updated `LoginForm` so Driver and Ops login screens use distinct imagery, copy, and metrics.
- Ops continues to use `frontend/src/assets/setuhaul-dock-command-hero.png`; Driver now focuses on ETA/exception reporting and single-truck context.
- Verification: `npm run lint` PASS; `npm run build` PASS; screenshots `tmp/ui-polish/driver-login-role-hero.png` and `tmp/ui-polish/ops-login-role-hero.png` visually spot-checked. Memory MCP unavailable; Sprint status unchanged.

## 2026-08-10 18:22 IST | ingest | Generated login hero asset

- Replaced the weak abstract/fake-map login right panel with a generated dock-command hero image saved as `frontend/src/assets/setuhaul-dock-command-hero.png`.
- Updated `LoginForm` and `App.css` so the image carries the visual while overlay copy and classroom-scale metrics remain readable.
- Verification: `npm run lint` PASS; `npm run build` PASS; `tmp/ui-polish/driver-login-dock-hero.png` visually spot-checked. Memory MCP unavailable; Sprint status unchanged.

## 2026-08-10 18:12 IST | ingest | Frontend UI polish

- Implemented UI polish in `frontend/src/App.css`, `frontend/src/index.css`, `frontend/src/features/auth/LoginForm.tsx`, `frontend/src/features/driver/DriverHome.tsx`, `frontend/src/features/operator/OpsHomes.tsx`, and `frontend/src/layouts/ProtectedLayout.tsx`.
- Scope stayed within the two-portal POC: login aesthetics, structured driver context, ops metric/status presentation, typography, shell layout, and hook warning cleanup; no booking, map/GPS, user-management, or scheduling mutation behavior added.
- Verification: `npm run lint` PASS; `npm run build` PASS; unauthenticated login screenshots captured and visually checked. Authenticated screens not live-smoked because local env files are absent and pasted secrets were not persisted. Memory MCP unavailable.

## 2026-08-10 17:51 IST | query | FDE challenge PDF analysis

- Analyzed `docs/SetuHaul_FDE_Challenge.pdf` across all 20 pages; rendered representative pages 1, 10, and 18.
- Durable conclusion: the brief leaves implementation choices open, but FDE challenge readiness requires Sprint 3 evidence for deterministic feasibility, allocation semantics, same-slot competition, stale option handling, idempotent retries, and no-feasible-slot escalation.
- Updated [[implementation]], [[current-state]], [[handoff]], and CHANGELOG. Memory MCP was unavailable in this Codex session, so checked-in context is authoritative until memory can be replayed.

## 2026-08-08 13:45 IST | ingest | Rename web → frontend

- Directory `web/` renamed to `frontend/`; CI/README/package updated; build PASS. Updated [[handoff]], CHANGELOG, master-plan scaffold wording.

## 2026-08-08 13:35 IST | ingest | Root GET / health ping

- FastAPI `GET /` returns alive JSON; README Quick start note. Smoke PASS. Updated [[handoff]], CHANGELOG.

## 2026-08-07 20:25 IST | verify | Gemini live PASS

- Google key saved gitignored; `gemini-2.5-flash` invoke PASS via `ChatGoogleGenerativeAI`. All three providers live-verified. Updated [[handoff]], [[current-state]], CHANGELOG, Memory.

## 2026-08-07 20:20 IST | verify | OpenAI+OpenRouter smoke; Gemini native class

- Live invoke: OpenAI PASS, OpenRouter PASS; Gemini key was OpenAI-shaped (FAIL). Switched Gemini to `ChatGoogleGenerativeAI`. Unit 20 passed. Updated [[handoff]], [[ai-system]], [[current-state]], CHANGELOG, Memory.

## 2026-08-07 20:00 IST | ingest | README + multi-provider LLM

- README Quick start for Sprint 1–2 POC; demo login emails + password env-var names (passwords OOB).
- `assistant/llm.py` ChatOpenAI factory (`auto` OpenAI → OpenRouter → Gemini); settings + `.env.example` extended.
- Unit 18 passed; OpenRouter/Gemini live smoke pending keys. Updated [[handoff]], [[current-state]], [[ai-system]], CHANGELOG, Memory MCP.

## 2026-08-07 19:35 IST | ingest | Sprint 2 exit gate COMPLETE

- Struck Sprint 2 Living §7 build + exit gate with API `DEMO_PATH_PASS` and browser localhost:5173 evidence.
- Fixed write path (`UPDATE_ETA`, `DELAY`, JWT leeway, tzdata, env BOM, stale uvicorn). Credentials remain gitignored; rotation recommended in [[handoff]].
- Updated [[handoff]], [[current-state]], [[implementation]], [[ai-system]], master plan, root CHANGELOG, Memory MCP.

## 2026-08-07 19:26 IST | verify | Sprint 2 Living re-baseline

- Inspected dirty-tree Sprint 2 code + live smoke. Struck only verified §7 items (repair/ETA distinction; services+tools; role allowlists; bind_tools loop).
- Blocker recorded: confirmed ETA write 500 on audit `ETA_UPDATE` vs `UPDATE_ETA`.
- Living → Sprint 2 ACTIVE / IN PROGRESS; exit gate open. Updated [[handoff]], [[current-state]], [[implementation]], master plan, root CHANGELOG, Memory MCP.

## 2026-08-07 18:36 IST | ingest | .gitignore noise reduction

- Ignored `graphify-out/` and common generated/OS/editor artifacts. Secrets/tmp/venv unchanged. Updated [[handoff]], root CHANGELOG.

## 2026-08-07 17:55 IST | verify | Sprint 1 exit gate COMPLETE

- Exit gate struck: Admin browser global RO, wrong-portal, API 401/IDOR/scope, no mutations, CORS both origins, baseline a11y, minimal CI.
- Deferred honestly: deep SQLAlchemy repos; fuller a11y/responsive; CI DB/Docker expansion.
- Living status → Sprint 2 ACTIVE. Updated [[handoff]], [[current-state]], [[implementation]], [[testing]], [[contradictions]], root CHANGELOG, master plan, Memory MCP.

## 2026-08-07 17:04 IST | ingest | Living sprint catch-up + cross-IDE writeback

- Master plan Living status re-baselined; Sprint 1 mostly complete (exit open); Sprint 2 TODO.
- Root `AGENTS.md` + Claude/Gemini/Cursor/wiki pointers require Living status at startup and checklist strikethrough on durable progress.
- Memory MCP synced (16:53 smoke + policy). Updated [[handoff]], [[implementation]], [[current-state]], root CHANGELOG.

## 2026-08-07 16:53 IST | verify | Browser smoke PASS + pooler fix

- Two-portal UI smoke on `localhost:5173`: Driver login → chat shell → logout; Ops login → dashboard.
- Fixed Vite import path, asyncpg `statement_cache_size=0` for PgBouncer, Stitch chat/ops skeleton polish.
- Screenshots: `tmp/poc-screenshots/01`–`04` (gitignored). Updated [[current-state]], [[handoff]], [[testing]], root CHANGELOG, Memory MCP.

## 2026-08-07 16:35 IST | verify | /health/ready + /auth/me PASS

- User saved `.env`; `DATABASE_URL` + service role non-empty. Backend ready; DB ping true.
- `/api/v1/auth/me` PASS for USR001 / USR101 / USR999 with expected roles and scopes.
- Updated [[current-state]], [[handoff]], root CHANGELOG, Memory MCP. Browser smoke still TODO.

## 2026-08-07 16:32 IST | verify | Auth/me blocked — empty DATABASE_URL on disk

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
- Passwords only in gitignored `.env.local` (OOB). Anon keys still empty → `/auth/me` not run.
- Updated [[current-state]], [[contradictions]], [[handoff]], [[skills-and-mcp]], [[database]], root CHANGELOG, Memory MCP.
- Verification: MCP SQL proof + backend unit tests 4 passed; JWT e2e not run.

## 2026-08-07 16:20 IST | ingest | Two-portal UI code + Auth create blocked

- Consolidated `web/src` to `/driver/login` + `/ops/login` / `/driver` + `/ops`; Operator+Admin share ops shell; legacy aliases redirect. ADR 005 + master plan checklist updated.
- AI lock unchanged: `ChatOpenAI` + `bind_tools` + manual loop (ADR 011 / [[ai-system]]); no Erica.
- Auth: passwords in gitignored `.env.local`; create/map **not** completed — Supabase MCP `fetch failed` / connection timeout. Script loads `.env.local`.
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

- Owner clarification: tools via `ChatOpenAI.bind_tools` + manual invoke loop; not create_agent. Upstash 24h non-authoritative memory from Sprint 2. Tool matrix ~18–25 / 26 named with sprint placement.
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
- Catalog still: `cursor-ide-browser`, `user-memory` only. Supabase not found — cannot `mcp_auth`. Live counts/Auth/persona verification still blocked.
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

- Owner vision locked for Sprint 1–2 UI: `/driver/login` → chat/profile/logout; `/ops/login` → one read-only ops dashboard for Operator (facility) and Admin (global RO). Prefer Driver + Ops Auth accounts; three seed personas may share two entries.
- Explicitly out of POC: maps, GPS, user management, booking mutations. Scheduling mutations remain Sprint 3.
- AI locks aligned: `ChatOpenAI` + `bind_tools` + manual loop; no `create_agent` / `AgentExecutor`; Upstash 24h in Sprint 2; Sprint 1 = auth + shells + reads.
- Updated master plan, POC design review, full-stack/business-analysis/solution-architecture branches, [[current-state]], [[implementation]], [[architecture]], [[contradictions]], [[handoff]], root CHANGELOG.
- Scaffold still exposes three login routes — recorded as open contradiction until code consolidates.
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
- Memory MCP unavailable in this Codex session; checked-in context synchronized and memory replay remains pending.
## 2026-08-10 19:12 IST | implementation | LangChain feasible slot search

- Added `backend/app/scheduling/feasibility.py` for deterministic Sprint 3 slot feasibility/ranking using checked constraints, latest ETA, facility hours, slot/dock compatibility, active appointments, dock events, and no-slot escalation payloads.
- Added `backend/app/api/v1/routers/scheduling.py` with `GET /api/v1/shipments/{shipment_id}/slots/feasible`, wired the router into `backend/app/main.py`, and registered `find_feasible_slots` in `backend/app/assistant/tools.py`.
- Updated the assistant prompt so slot search is enabled as informational non-reserved options while booking/hold/reschedule/cancel/confirm mutations remain disabled.
- Verification: backend unit tests PASS, 30 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke not run because local env files are absent and pasted secrets were not persisted.
- Memory MCP unavailable in this Codex session; checked-in context synchronized and memory replay remains pending.
## 2026-08-10 19:31 IST | implementation | Transactional request_slot flow

- Added `backend/app/scheduling/allocation.py` with `request_slot`: idempotency lookup/store, driver ownership checks, row locks, slot revalidation, `PENDING_CONFIRMATION` insert, `BOOK_APPOINTMENT` audit, commit, and authoritative reread.
- Extended `backend/app/api/v1/routers/scheduling.py` with `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request` requiring `Idempotency-Key`, and registered the Driver LangChain `request_slot` tool.
- Updated the assistant prompt so exact selected slot requests are enabled as pending confirmation only; reschedule/cancel/confirm remain disabled.
- Verification: backend unit tests PASS, 33 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and concurrency tests not run because local env files are absent and pasted secrets were not persisted.
- Memory MCP unavailable in this Codex session; checked-in context synchronized and memory replay remains pending.
## 2026-08-10 19:38 IST | implementation | Appointment request status read path

- Added `get_appointment_request_status` in `backend/app/scheduling/allocation.py` for scope-safe, read-only status checks after `request_slot`.
- Exposed `GET /api/v1/shipments/{shipment_id}/appointment-request/status` and registered the Driver LangChain `get_appointment_request_status` tool.
- Updated the assistant prompt so pending confirmation remains distinct from confirmed booking, and updated [[current-state]], [[implementation]], [[ai-system]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 35 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and concurrency tests not run because local env files are absent and pasted secrets were not persisted.
- Memory MCP unavailable in this Codex session; checked-in context synchronized and memory replay remains pending.
