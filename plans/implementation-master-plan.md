# SetuHaul implementation master plan

Status: active implementation source of truth  
Date: 2026-08-07  
Source inputs: 20-page FDE challenge, project documentation, seeded Supabase migration/tests, database guide, and supplied Stitch screens.

## Living sprint status

Last re-baselined: 2026-08-07 19:35 IST  
Active sprint: **Sprint 3 - deterministic feasibility and concurrent allocation**  
Team POC target: **Sprint 2 exit gate (COMPLETE)**  
FDE challenge-ready target: **Sprint 3 exit gate**

**Cross-IDE scoreboard:** every Cursor / Claude / Codex / Gemini session must read this section at startup and refresh it on durable writeback (see root `AGENTS.md`).

Use this plan as a living checklist:

- `- [ ] TODO` means work is unverified or not started.
- `- [ ] **IN PROGRESS**` means the team is actively implementing it.
- `- [x] ~~Completed item~~` is allowed only after the stated evidence has been verified; include the verification date or evidence link.
- Deferred scope remains an unchecked `TODO (DEFERRED until ...)`; never strike it merely because it is outside the active sprint.
- A sprint heading and exit gate are struck through only after every required item and the exit gate have objective evidence.

| Sprint | Status | Gate dependency |
|---|---|---|
| Sprint 1 - trusted walking skeleton | **COMPLETE** | Exit gate struck 2026-08-07 17:55 IST (Admin browser + adversarial/IDOR + baseline a11y + minimal CI + CORS both origins) |
| Sprint 2 - exception and ETA vertical slice | **COMPLETE** | Exit gate struck 2026-08-07 19:35 IST (API demo `DEMO_PATH_PASS` + browser localhost:5173 driver chat/tools/ETA + ops refresh) |
| Sprint 3 - deterministic allocation | **TODO** | Starts only after Sprint 2 POC exit gate passes |

Verified repository foundation (not a completed implementation sprint):

- [x] ~~Supabase baseline migration and seed files are present.~~ Verified by repository inspection on 2026-08-07; migration execution was not rerun.
- [x] ~~Two database SQL test files are present.~~ Verified by repository inspection on 2026-08-07; tests were not run in this re-baseline.
- [x] ~~Stitch design resources are present.~~ Four supplied design sets were found on 2026-08-07; the current POC selection remains set 2 pending any explicit design-decision revision.
- [x] ~~Scaffold application runtime trees for `backend/` and `frontend/` (formerly `web/`).~~ Verified by repository inspection on 2026-08-07 15:45 IST. Auth users mapped; JWT/JWKS + `/auth/me` PASS 2026-08-07 16:35 IST; browser smoke PASS 16:53 IST. Renamed `web/` → `frontend/` 2026-08-08.

## 1. Executive decision

Build SetuHaul as a **modular monolith with clean/hexagonal boundaries**:

- React 19 SPA using the supplied Stitch visuals.
- One FastAPI API/BFF and one asynchronous worker.
- Supabase Auth is included from Sprint 1. Prefer two shared permanent internal-POC accounts (Driver + Ops). Seeded Operator (`ROL002`) and Admin (`ROL008`) may both exist; they share one ops dashboard shell and one ops login entry. FastAPI verifies the access token and maps it to the seeded application user, role, driver, and facility/global scope. **Two login UIs only** (`/driver/login`, `/ops/login`); choosing an entry never grants a role.
- Supabase PostgreSQL as the system of record and final concurrency authority.
- Upstash Redis for 24-hour conversation history, session context, cache, rate limiting, and non-authoritative coordination.
- One role-aware LangChain assistant: **`ChatOpenAI` + `bind_tools(...)`** (OpenAI/OpenRouter) or **`ChatGoogleGenerativeAI` + `bind_tools(...)`** (Gemini), plus a **manual bounded invoke loop**. Provider selection via `assistant/llm.py` (`LLM_PROVIDER=auto|openai|openrouter|gemini`; auto = OpenAI → OpenRouter → Gemini). This is **not** `create_agent`, `AgentExecutor`, or `create_react_agent`. **`bind_tools` + manual loop ≠ `create_agent`.** Tools call FastAPI application services only; PostgreSQL is SoT.
- Pydantic models for every API request/response, execution context, conversation state, tool args/results, and domain command/result. Tools call FastAPI application services only; PostgreSQL is SoT; the LLM never invents operational facts.
- Deterministic application services for feasibility, allocation, appointment transitions, and all writes.
- LangSmith for AI traces and platform logs/metrics for application operations; do not add overlapping observability products until hosting requires them.

Do not start with microservices, CQRS, event sourcing, OR-Tools, or multiple runtime agents. The stated workload is modest, the domain is still evolving, and correctness is easier to prove within a single transactional boundary.

## 2. North star and non-negotiable invariants

The north star is: **a messy driver exception becomes a feasible, current, clearly communicated operating plan without creating a conflict for another driver.**

The system must preserve these invariants:

1. At most one active `PENDING_CONFIRMATION`, `CONFIRMED`, or `IN_PROGRESS` appointment occupies a slot.
2. A shipment has at most one current active appointment; old appointments remain history.
3. Displayed options are information, not promises.
4. A selected option is revalidated inside the same database transaction that claims it.
5. The LLM never decides feasibility, priority, availability, or booking success.
6. Every mutation is authorized, idempotent, transition-validated, and audited.
7. PostgreSQL is authoritative; loss of Redis or the LLM provider cannot corrupt business state.
8. No feasible outcome produces a reasoned escalation, never an invented slot.

The existing partial unique indexes provide the final double-booking guard. Application locking and validation improve the user outcome, but the database constraint is the last line of defence.

## 3. Required decisions before broad implementation

Record these as ADRs during Sprint 1:

| ADR | Decision |
|---|---|
| 001 | Modular monolith with ports/adapters and domain-first modules. |
| 002 | PostgreSQL constraints and transactions are the concurrency authority. |
| 003 | Exact lifecycle and user-visible meaning of displayed, selected, requested/held, pending, confirmed, expired, rejected, cancelled, and conflicted. |
| 004 | Feasibility and ranking use a versioned deterministic policy outside the LLM. |
| 005 | Supabase Auth from Sprint 1 with shared POC accounts (Driver + Ops; Operator facility-scoped and/or Admin global RO), FastAPI JWT verification, server-authoritative role routing, two entry UIs (`/driver/login`, `/ops/login`), role-scoped tools/APIs, and backend-only database access. Individual accounts replace shared credentials before production. |
| 006 | Redis is ephemeral and rebuildable, never the source of business truth. |
| 007 | Idempotency, audit, and reliable outbound-event strategy. |
| 008 | Strict offset-aware timestamp parsing and facility-time-zone behaviour for the baseline's text timestamps. |
| 009 | Human takeover rules and permitted manual overrides. |
| 010 | Whether additive operational-control tables are allowed despite the instruction to preserve existing business tables. |
| 011 | One runtime conversational agent; the four planning personas are development reviewers, not production agents. |
| 012 | React 19 is the project frontend unless the owner explicitly replaces the documented stack; do not build React and Angular variants. |

### Schema/auth decisions needing explicit ratification

- `public.users.password_hash` is not used and must never become the login mechanism. Prefer an additive `auth_user_id uuid` link to `auth.users`; a verified-email mapping may be used only as a documented POC bridge.
- A durable hold/idempotency/outbox lifecycle is not fully represented. Prefer additive tables such as `slot_holds`, `idempotency_requests`, and `outbox_events`. If additions are forbidden, V1 must define `PENDING_CONFIRMATION` as the atomic claim and must not pretend Redis creates a durable hold.
- Baseline timestamps are text. Do not rewrite the applied baseline. Validate strict ISO-8601 with offsets in adapters and consider typed projections in a later additive migration.

## 4. Bounded modules

```text
Web SPA
  -> FastAPI BFF/API
       -> Identity & Access
       -> Freight Context
       -> Exception & Conversation
       -> Appointment & Capacity
       -> Scheduling & Feasibility
       -> Facility Operations
       -> Reporting & Analytics
       -> Audit & Observability
       -> Notifications & Integrations
            -> PostgreSQL / Redis / LLM provider / external channels
```

Each module exposes application use cases. HTTP routers and AI tools call those same use cases. Modules do not reach into another module's repository internals.

## 5. Concurrency-safe booking flow

1. Slot search returns a `recommendation_id`, snapshot/version hash, `expires_at`, deterministic reasons, and a clear `not reserved` label.
2. The driver explicitly chooses an option. The command carries an `Idempotency-Key` and recommendation/version.
3. A database transaction re-reads and locks the relevant slot/capacity, shipment/current appointment, latest ETA, dock status, and effective facility rules.
4. The service rechecks facility hours, arrival feasibility, vehicle/product/refrigeration/weight compatibility, unload duration, dock state, active appointment, and policy.
5. It creates the durable hold or `PENDING_CONFIRMATION`, transitions the replaced appointment in the same transaction, and appends audit/outbox data.
6. The unique partial index decides any residual race.
7. A unique violation becomes `409 SLOT_NO_LONGER_AVAILABLE` with refreshed options. The service never silently books a different slot.
8. Confirmation, cancellation, expiry, and rejection are separate idempotent state transitions.

Recommended policy V1: hard feasibility first; protect in-progress and confirmed commitments; then shipment/service priority; then actual waiting and appointment lateness; then earliest feasible arrival; finally stable request-time tie-break. Policy version and explanation factors must be recorded.

## 5.1 POC definition and delivery point

The **team POC is delivered at the end of Sprint 2**. It is a **simple internal POC**—deliberately smaller than the final FDE challenge demonstration. Do not expand into maps, GPS, user management, or booking mutations.

The POC must allow:

1. A team member to enter through **exactly two login screens**—Driver and Ops (Admin/Operator)—backed by one shared Supabase Auth implementation. The verified server-side role always decides the destination and permissions.
2. The Driver account to open a mobile-first **chat interface** with light supporting context/quick actions, a **profile section**, and **logout**.
3. The driver to ask about their shipment, ETA, current appointment, facility, and current exception (Sprint 2 chat).
4. The LangChain path (`ChatOpenAI` + `bind_tools` + manual invoke loop) to receive verified PostgreSQL context from FastAPI services, answer in chat without inventing operational facts, and never execute SQL or schedule mutations.
5. The driver to report a delay and update an ETA only after necessary clarification, exact interpreted date/time/time-zone display, and explicit confirmation (Sprint 2).
6. Upstash Redis to retain bounded conversation history and structured session context for 24 hours without becoming the business source of truth (Sprint 2).
7. An Ops account (facility-scoped Operator and/or global read-only Admin) to open the **same read-only operations dashboard** showing seeded shipments, exceptions, appointment schedule, dock operational state, slot records, facility rules, and warehouse constraints. JWT role decides facility vs global scope. More observational ops detail on the dashboard is fine; schedules/capacity stay read-only until Sprint 3.
8. Dashboard states for scope, facility time zone, `as_of`/freshness, loading, empty, stale, and error; values come through authorized FastAPI query services. No user/role/configuration management.
9. LangSmith traces (Sprint 2+) to show the prompt run, chosen tool, sanitized arguments, duration, and result code.

The POC is successful when a team member can demonstrate `Driver login -> profile/context -> LangChain chat -> clarified and confirmed ETA/exception update -> logout -> Ops login -> matching dashboard exception/schedule state (facility or global per role) -> logout`. Shared credentials are acceptable only for the internal POC and provide account-level, not teammate-level, audit attribution. Concurrency-safe slot allocation becomes **FDE challenge-ready at the end of Sprint 3**.

### POC role and screen contract

| Persona | Entry and destination | Sprint 1-2 capabilities | Explicitly unavailable in the POC |
|---|---|---|---|
| Driver | `/driver/login` → `/driver/assistant` | Chat (+ light context/quick actions), profile section, own shipment/ETA/appointment/facility context, confirmed ETA/exception update (Sprint 2), logout | Maps/GPS, feasible-slot recommendations, booking, rescheduling, cancellation, other-driver data, user management |
| Operator | `/ops/login` → `/ops/dashboard` (same shell as Admin) | Facility-scoped read-only dashboard: KPIs, shipments/exceptions, appointment schedule, dock/slot snapshot, facility rules/constraints, logout | Appointment/capacity mutations, cross-facility access, user/role configuration, maps/GPS |
| Admin | `/ops/login` → `/ops/dashboard` (same shell; JWT = global RO) | Same ops dashboard UI with global read-only scope as ratified in ADR 005, logout | User/role/system configuration and scheduling mutations until Sprint 3 |

**Auth account mapping (prefer simple):** shared Driver account → driver chat; shared Ops account(s) → same dashboard. Seeded `USR001` (Driver), `USR101` (Operator/FAC-JAI-01), and `USR999` (Admin global RO) may all exist—Operator and Admin **share one dashboard UI** and **one `/ops/login` entry**; role from JWT decides facility vs global scope. Do **not** require three distinct login UIs. Web scaffold consolidated: `/driver/login` + `/ops/login`; legacy `/operator/*` and `/admin/*` redirect.

The two entry screens reuse the selected Stitch login composition and one `LoginForm`/auth client. Entry choice is only presentation. `/api/v1/auth/me` determines the verified role and redirect; wrong-entry sign-in offers the correct destination, and local `returnUrl` validation prevents open redirects.

### POC scheduling boundary

Sprint 1-2 scheduling visibility is **observational only**: stored appointments, appointment-slot rows, dock status/events, facility rules, constraints, and timestamped operational summaries. `Operational docks now` means a defined current operational-state count, not compatible or bookable capacity. The POC does not calculate shipment feasibility or expose claimable slot options.

Sprint 3 is the first sprint allowed to search/rank feasible replacement slots or mount tools/routes that hold, request, confirm, cancel, or reschedule appointment/capacity state. In Sprint 2, a driver request for these actions returns a stable `CAPABILITY_NOT_ENABLED`/operations-handoff response and creates zero appointment writes.

## 5.2 Capability / tool delivery matrix (~18–25 band; 26 named rows)

These are FastAPI **application service** capabilities. Sprint 1 delivers observational **services/REST** only (no model registration). Sprint 2+ registers role-scoped subsets with the model via **`ChatOpenAI.bind_tools(...)`** and a **manual invoke loop**—not `create_agent` / `AgentExecutor` / `create_react_agent`. Tools never contain SQL; they call services. Two Sprint 2 rows are **internal** (no direct model registration). Every capability uses strict Pydantic models, a trusted `ExecutionContext` from a verified Supabase token, and returns freshness plus stable result/error codes.

**Count:** 26 named rows; **~18–25** is the accepted planning band (owner ~18–20 ≈ role-scoped / POC-facing subsets). Infra (history, audit, authz, idempotency, redaction) is not model-selectable.

| Tool | First delivered | POC? | Primary data |
|---|---:|---:|---|
| `get_current_user_context` | Sprint 1 service; registered in Sprint 2 | Yes | `users`, `roles`, driver/facility mapping |
| `get_driver_operational_context` | Sprint 1 service; registered in Sprint 2 | Yes | drivers, vehicles, shipments, appointments, ETA, check-ins |
| `list_active_shipments` | Sprint 1 service; registered in Sprint 2 | Yes | `shipments` |
| `get_shipment_details` | Sprint 1 service; registered in Sprint 2 | Yes | shipments, drivers, vehicles, carriers |
| `get_latest_eta` | Sprint 1 service; registered in Sprint 2 | Yes | `eta_updates`, shipments |
| `get_eta_history` | Sprint 2 | Yes | `eta_updates` |
| `get_current_appointment` | Sprint 1 service; registered in Sprint 2 | Yes | appointments, slots, docks |
| `get_facility_details` | Sprint 1 service; registered in Sprint 2 | Yes | facilities, contacts, rules |
| `get_facility_operational_status` | Sprint 1 service; registered in Sprint 2 | Yes, operator/admin; driver-safe projection only | docks, slots, dock events, check-ins |
| `report_delay_or_update_eta` | Sprint 2 | Yes, driver | one atomic service transaction across ETA history, exception, message dedupe, and audit |
| `record_eta_update` | Sprint 2 internal capability | No direct model registration | ETA updates, exceptions, audit log |
| `create_or_update_exception` | Sprint 2 internal capability | No direct model registration | driver exceptions, chat thread, audit log |
| `get_exception_status` | Sprint 2 | Yes | exceptions, operational messages |
| `get_dashboard_summary` | Sprint 1 service; optional operator/admin registration in Sprint 2 | Yes, operator/admin | facility-scoped operational views and aggregates; dashboards call REST directly |
| `find_feasible_slots` | Sprint 3 | No | shipment, ETA, docks, slots, appointments, rules, dock events |
| `request_slot` | Sprint 3 | No | appointments/control state, audit/outbox |
| `reschedule_appointment` | Sprint 3 | No | current appointment, target slot, audit/outbox |
| `cancel_appointment` | Sprint 3 | No | appointments, audit/outbox |
| `get_appointment_request_status` | Sprint 3 | No | appointments, operational messages |
| `get_dock_status` | Sprint 3 | No | docks, dock events, slots |
| `get_queue_status` | Sprint 3 | No | facility check-ins and queue state |
| `get_exception_queue` | Sprint 3 | No | exceptions, shipments, appointments, check-ins |
| `escalate_exception` | Sprint 3 | No | exceptions, contacts, operational messages, audit/outbox |
| `search_shipments` | Sprint 3 | No | shipments and operational read view |
| `search_drivers` | Sprint 3 | No | drivers, shipments, exceptions |
| `generate_operational_report` | Sprint 3 | No | deterministic reporting service/read models |

Conversation-history loading/saving, audit logging, API logging, authorization, idempotency, and tool-result redaction are application infrastructure. They are not exposed as tools the model may choose.

## 5.3 POC design decision

Use `designs/stitch_setuhaul_ai_logistics_platform_2` as the visual source because its login, driver assistant, operations assistant, and dashboard share the strongest consistent component language and the most readable general-purpose typography.

For the POC, implement only:

- **POC Supabase login (two entries):** `/driver/login` and `/ops/login` from the same reusable login composition and auth form, labelled `Internal POC`. Remove decorative fleet/network KPI claims. Do not ship three separately branded portal logins.
- **Driver after login:** central chat plus light supporting context/quick actions (`Update ETA`, `View appointment`, `Facility details`), compact verified-context (shipment, ETA freshness, facility, appointment), **profile section**, and **logout**. Chat mount is Sprint 2; Sprint 1 ships the shell + reads.
- **Ops after login (Operator or Admin):** one read-only **dashboard** with operational detail—KPIs, exception list/detail, shipments, appointment schedule, dock/slot snapshot, facility rules/constraints. JWT role sets facility vs global RO scope. Profile/logout as needed. No user management, settings, or scheduling mutation controls.
- **Responsive behaviour:** on smaller screens, move active context into a collapsible drawer below the chat header; chat remains the primary driver surface.

Defer maps, live GPS, route planner, vehicle telemetry, network topology, fleet pages, predictive routing, analytics charts, notification centre, user management, booking mutations, and settings. The FDE brief explicitly does not require live GPS, and fictional live data would weaken trust in the POC.

The first Stitch set is visually more specialized and uses a strong monospaced command-centre style, but it is less suitable for a quick team POC because it emphasizes routing and dense operational chrome. It may remain a reference for later advanced operations screens.

## 5.4 FDE challenge traceability rule

The PDF is the governing source for operational behaviour. Every tool story, acceptance test, and demo scenario must reference the relevant challenge section or seeded scenario in its test name/docstring. Product copy must distinguish shown, requested, pending, and confirmed capacity exactly as required by the brief.

| Challenge scenario | Delivery sprint | Required proof |
|---|---:|---|
| Driver has multiple shipment records | Sprint 2 | Agent asks one targeted disambiguation question. |
| Repair duration is not the revised ETA | Sprint 2 | Agent asks for arrival time/uncertainty before recording ETA. |
| Duplicate messages on weak connectivity | Sprint 2 | One stored turn and one business effect. |
| Driver returns later in the same thread | Sprint 2 | Upstash Redis restores context; PostgreSQL refreshes business facts. |
| Two drivers choose the same slot within seconds | Sprint 3 | Exactly one active booking succeeds under parallel transactions. |
| Displayed slot disappears before confirmation | Sprint 3 | Revalidation fails safely and refreshed options are returned. |
| Driver corrects ETA after options were shown | Sprint 3 | Old options are invalidated and recomputed. |
| Dock closes/capacity reduces during conversation | Sprint 3 | Affected options become unavailable; no promise is made. |
| Cancellation frees capacity mid-conversation | Sprint 3 | Fresh search can expose the released slot without stale-cache error. |
| Higher-priority shipment enters later | Sprint 3 | Versioned deterministic policy and explanation are applied. |
| Early, late, waiting, unloading, and future trucks compete | Sprint 3 | Facility snapshot respects fixed/in-progress commitments and arrival evidence. |
| No feasible compatible same-day slot | Sprint 3 | Human escalation with constraint reason; no fabricated slot. |
| Warehouse response conflicts with stored schedule | Sprint 3 | System-of-record conflict triggers human review and is never called confirmed. |

The POC demo should use Indian SetuHaul seed data and facility terminology from the challenge. Remove the Stitch examples referring to US interstates, Chicago, live GPS, bypass routing, and fictional fleet telemetry.

## 6. Sprint 1 - trusted walking skeleton

Goal: prove provider-neutral execution context, role scoping, data access, and an end-to-end read path before adding AI or booking writes.

### Build

- [x] ~~Ratify ADRs 001-012, especially Supabase user mapping and additive control tables.~~ Evidence: `docs/adrs/SPRINT1_ADRS.md` (2026-08-07); Admin global RO closed.
- [x] ~~Scaffold `frontend/` (formerly `web/`) + `backend/` + root `.env.example`.~~ Evidence: trees present 2026-08-07 15:45 IST. Worker/Docker Compose remain TODO (DEFERRED); minimal CI added 2026-08-07 17:55 IST. Renamed 2026-08-08.
- [x] ~~Add settings, DI, request IDs, response/error envelope, liveness, and readiness.~~ Evidence: `backend/app/core/*`, `GET /health/live|ready` (unit tests for envelope/context run 2026-08-07; live HTTP not run).
- [x] ~~Create Supabase Auth users for the internal POC mapped to seeded Driver (`ROL001` / USR001) and Ops (facility-scoped Operator `ROL002` / USR101 and Admin `ROL008` / USR999).~~ Verified 2026-08-07 via MCP: `auth.users=3`, all three `auth_user_id` mapped. Passwords OOB in gitignored `.env.local`. Anon + `DATABASE_URL` + service role populated locally (gitignored) after Dashboard save.
- [x] ~~Consolidated to `/driver/login` and `/ops/login` using one shared login form and Supabase email/password client.~~ Legacy `/operator/login` + `/admin/login` redirect to `/ops/login`. Browser smoke PASS 2026-08-07 16:53 IST on `http://localhost:5173`.
- [x] ~~Add server-authoritative post-login role routing, protected layouts, wrong-entry handling, and fail-closed unmapped/disabled-user handling (frontend guards UX-only).~~ Two portals (`/driver`, `/ops`); Operator+Admin share `/ops`. Full session-expiry/returnUrl hardening still TODO.
- [x] ~~FastAPI JWT verify (issuer/JWKS/audience/expiry/subject) → trusted `ExecutionContext`.~~ Live JWKS verify PASS 2026-08-07 for Driver/Operator/Admin password-grant JWTs.
- [x] ~~Map verified Supabase subject via `public.users.auth_user_id`; refuse unmapped/disabled; ignore client ownership IDs.~~ Code + hosted column/index verified; USR001/USR101/USR999 mapped (MCP 2026-08-07).
- [x] ~~`GET /api/v1/auth/me` safe profile DTO.~~ Live HTTP **PASS** 2026-08-07 16:35 IST: USR001 DRIVER facility; USR101 OPERATIONS_EXECUTIVE facility; USR999 ADMIN global_read_only. `/health/ready` PASS (`database_reachable=true`).
- [x] ~~Profile menus and logout for Driver and Ops (Operator/Admin share ops shell).~~ Browser smoke: driver logout PASS → `/driver/login`; ops shell profile/logout present. Redis-thread detach N/A until Sprint 2.
- [x] ~~POC backend-only secrets: service role never in browser; `.env.example` placeholders only.~~ Verified by file review 2026-08-07; `frontend/.env.local` is VITE-only.
- [ ] TODO (DEFERRED until Sprint 2+): deepen async SQLAlchemy repositories beyond Sprint 1 inline SQL reads (current routers use parameterized SQLAlchemy `text()` against frozen baseline). Exit gate does not require the full repository refactor.
- [x] ~~Ratify endpoint × role × scope matrix including Admin global read-only.~~ Evidence: ADR 005 + matrix in `docs/adrs/SPRINT1_ADRS.md`.
- [x] ~~Implement Sprint 1 observational read APIs (driver context, shipment, current appointment, ops summary/exceptions/schedule/dock/constraints).~~ Live JWT reads PASS after asyncpg `statement_cache_size=0` pooler fix (2026-08-07 16:53 IST): `/api/v1/driver/context` + ops `dashboard-summary`. Formal integration test suite still TODO.
- [x] ~~Keep appointment/capacity query services separate from Sprint 3 scheduling command services; no scheduling mutation routes or model-registered scheduling tools in the POC.~~ Verified by route inventory 2026-08-07 (no book/cancel/reschedule mounts); reconfirmed 2026-08-07 17:55 IST (no `@router.post|put|patch|delete`; sample mutation paths 404/405).
- [x] ~~Sprint 1 service contracts for POC observational reads exist as REST (tool matrix rows); not registered with the model yet.~~ Model registration is Sprint 2.
- [x] ~~Stitch set-2 inspired two-portal skeleton: login screens, driver chat shell + profile/logout, shared ops dashboard with live metrics.~~ Browser screenshots `tmp/poc-screenshots/01`–`04` (2026-08-07 16:53 IST). Fuller Stitch sidebar/search chrome still TODO.
- [x] ~~Baseline a11y on login + shells: labelled inputs (`htmlFor`/`id`), focusable profile/logout, `aria-live` for errors/loading.~~ Evidence 2026-08-07 17:55 IST Playwright probe PASS (`a11y_login_labels`, `a11y_login_live`). Fuller responsive/360px/keyboard/offline/stale polish remains TODO (DEFERRED).
- [ ] TODO (DEFERRED until Sprint 2+): fuller responsive/a11y polish — 360px driver chat/profile, desktop operational tables, complete keyboard-only chat flows, non-color status cues, empty/stale/offline/dependency-failure states beyond baseline.
- [x] ~~Minimal GitHub Actions CI: backend unit pytest + frontend typecheck/build.~~ Evidence: `.github/workflows/ci.yml` added 2026-08-07; local `pytest tests/unit` **4 passed** + `npm run build` **PASS** 2026-08-07 17:55 IST. Migration parity / seeded DB tests / Docker builds remain TODO (DEFERRED).
- [ ] TODO (DEFERRED until Sprint 2+): expand CI for migration parity, seeded DB tests, backend integration tests, and Docker builds.

### Exit gate

- [x] ~~Prove the two entry screens (`/driver/login`, `/ops/login`) use Supabase Auth and route only by the verified backend profile; Driver sees only its own profile/context, Operator sees only its assigned facility on the shared ops dashboard, and Admin sees the same dashboard with global RO scope. Wrong-entry login, invalid/expired/forged tokens, and arbitrary ownership/scope IDs fail safely. Logout invalidates the browser session/cache, no service key or token leaks, and no business write, map/GPS, user-management, or scheduling route/tool exists.~~ **Evidence 2026-08-07 17:55 IST:** Admin browser `/ops/login`→`/ops` global RO + logout PASS; Driver+Operator reconfirm PASS; wrong-portal Driver→ops and Ops/Admin→driver redirect without elevation PASS; API missing/invalid/forged Bearer → 401 PASS; driver IDOR on `SHP1002` → 403 PASS; Operator facility vs Admin global dashboard-summary PASS; no mutation routes PASS; no `SERVICE_ROLE` in web env PASS; CORS `localhost:5173` + `127.0.0.1:5173` PASS. Screenshots `tmp/poc-screenshots/05`–`10`. Unmapped/disabled-user and open-redirect hardening remain Sprint 3 hardening TODOs (not exit-gate blockers for this POC).

## 7. Sprint 2 - exception and ETA vertical slice

Goal: complete a safe single-driver delay flow with persistence, deduplication, and minimal conversational assistance.

### Build

- [x] ~~create or continue one exception thread for the relevant shipment.~~ 2026-08-07 19:35 IST — `record_eta_update` reuses/creates threads; demo persisted against SHP1017/`THR011`.
- [x] ~~resolve multiple plausible shipments with one minimal clarification.~~ 2026-08-07 19:35 IST — tool `CLARIFICATION_REQUIRED` when multiple actives; DRV001 single-active live path PASS.
- [x] ~~persist message dedupe, ETA history, exception state, and audit through one authorized, idempotent application transaction and authoritative post-commit reread; a partial failure rolls back the business effect.~~ 2026-08-07 19:35 IST — confirmed write PERSISTED; idempotent replay PASS; `UPDATE_ETA` audit action; `idempotency_requests` migration applied.
- [x] ~~treat repair duration, reported delay, and revised ETA as distinct facts; carry confidence and timestamp.~~ Unit + demo step 4 confirmation preview PASS.
- [x] ~~implement FastAPI application services for safe current context, shipment, current appointment, ETA/exception update, and driver-safe facility information; inject verified read models into the chat prompt.~~ `driver_reads` + `eta_service` + tools; live tool_calls verified.
- [x] ~~use deny-by-default role/channel REST allowlists. Drivers receive only their safe context/read APIs and the atomic ETA/exception command; operator/admin dashboards use REST query services. No Sprint 3 scheduling mutation routes exist in the POC.~~ `require_roles`; no scheduling mutation routes.
- [x] ~~add LangChain `ChatOpenAI` + `bind_tools(...)` on a curated role-scoped POC tool list, strict system prompt, and a custom bounded `run_assistant` invoke loop (`invoke` → tool_calls → service-backed ToolMessages → final text). Forbidden: `create_agent`, `AgentExecutor`, `create_react_agent`. Explicit: bind_tools + manual loop ≠ create_agent.~~ Live API + browser tool_calls PASS.
- [x] ~~load bounded conversation history and structured session context from Upstash Redis before invocation, then persist the completed turn with a 24-hour TTL (non-authoritative; Sprint 2 requirement—not Sprint 1).~~ `ConversationMemory` + configured Upstash env; chat turns persist; degrade path coded.
- [x] ~~implement duplicate/out-of-order message handling and safe recovery after Redis or model timeouts.~~ Idempotency replay demo PASS; Redis client_message_id dedupe.
- [x] ~~complete the driver chat/profile UI with quick actions, clarification, exact ETA/time-zone confirmation, write-in-progress, persisted success, retry-safe unknown outcome, stale/degraded data, and accessible logout. Never claim success before the authoritative reread.~~ Browser `DriverHome` chat/ETA/logout PASS; screenshots 11–13.
- [x] ~~connect the shared Ops dashboard to authorized REST endpoints for KPIs, exceptions, appointment schedule, dock/slot operational snapshot, and warehouse rules/constraints; JWT role applies facility vs global RO scope. Show freshness and no mutation controls.~~ Ops GETs retained; UI summary+exceptions+Refresh; schedule/dock/rules available via API.
- [x] ~~after a driver ETA/exception update, invalidate/refetch the operational read model so the Ops dashboard visibly shows the matching seeded shipment/exception change without claiming realtime behavior.~~ Browser `ops_sees_update` PASS; demo step 8 matching ETA.
- [x] ~~return `CAPABILITY_NOT_ENABLED`/operations handoff with zero appointment writes when chat or crafted requests attempt slot search, booking, rescheduling, cancellation, or confirmation during the POC.~~ Demo step 7 `scheduling_capability_disabled`.
- [x] ~~add LangSmith invoke traces and a scripted team demonstration covering two-entry login/routing, driver profile/logout, happy path, repair-duration clarification, exact ETA confirmation, duplicate/retry, unauthorized lookup, disabled scheduling capability, matching Ops dashboard state (Operator facility + Admin global), and LLM/Redis failure.~~ LangSmith tracing env on; `sprint2_demo_path.py` → `DEMO_PATH_PASS`.

### Exit gate

- [x] ~~prove the team POC end to end: Driver login (`/driver/login`) -> safe profile/context -> database-backed LangChain chat (`ChatOpenAI` + bind_tools + manual loop) -> clarified and explicitly confirmed atomic ETA/exception update -> refresh -> logout -> Ops login (`/ops/login`) -> matching dashboard/schedule/dock/rule state (facility for Operator, global RO for Admin) -> logout. Duplicate retries create one effect, cross-role/facility data and scheduling mutations are inaccessible, dashboard values reconcile with deterministic seeded queries, and REST reads remain available when the LLM or Redis is unavailable. Shared credentials remain internal-only. No maps, GPS, user management, or booking mutations.~~ **Evidence 2026-08-07 19:35 IST:** API `DEMO_PATH_PASS`; browser matrix PASS (login, chat tools, ETA persist, logout, ops refresh match); screenshots `tmp/poc-screenshots/11`–`14`. JWT leeway 300s for local clock skew.
## 8. Sprint 3 - deterministic feasibility and concurrent allocation

Goal: prove the core challenge under simultaneous scarce capacity.

### Build

- [ ] TODO: replace shared POC credentials with individual Supabase users before production so audit records identify the responsible teammate/user.
- [ ] TODO: add session revocation, password-rotation, disabled-user, and stale-role-claim hardening, then repeat all role/IDOR tests.
- [ ] TODO: implement a pure feasibility engine and versioned deterministic ranking policy.
- [ ] TODO: deliver and register every Sprint 3 tool in the tool delivery matrix with role-specific allowlists.
- [ ] TODO: return fresh, explainable, non-reserved options with snapshot metadata.
- [ ] TODO: implement atomic request/hold, reschedule, confirm, cancel, reject, expire, and conflict flows.
- [ ] TODO: invalidate/recompute options on ETA correction, dock closure, capacity change, appointment cancellation, check-in, or unload overrun.
- [ ] TODO: add human escalation records/queue for no-slot, contradictory, regulated, emergency, or approval-required cases.
- [ ] TODO: add the operations exception queue and appointment/dock/queue views needed for takeover.
- [ ] TODO: add concurrency and load tests for 10 drivers competing for 3-4 slots and two clients selecting the same slot.
- [ ] TODO: add end-to-end demonstrations for stale choice, losing a race, cancellation releasing capacity, and no feasible slot.

### Exit gate

- [ ] TODO: prove exactly one same-slot contender succeeds; every loser receives a conflict-safe refreshed response; no invalid option is confirmed; all transitions have a complete audit trail; and a no-feasible-slot case escalates safely.

## 9. Edge-case test catalogue

### Identity and conversation

- Driver, Operator, or Admin signs in through the wrong entry (`/driver/login` vs `/ops/login`); verified role routes safely without changing authority.
- Session expires during a protected flow; refresh/re-auth is safe and no stale protected view remains after logout/back navigation.
- Driver has no active shipment, one active shipment, or multiple plausible shipments; cancelled/completed work is not silently selected.
- Current appointment, ETA update, facility contact, or driver/vehicle detail is missing; the UI shows unknown/source state rather than inventing data.
- Driver has multiple active/plausible shipments.
- Role or facility permission changes mid-thread; user is disabled or token expires.
- Ordinal reference such as “the second one” after the option list changes.
- Duplicate, delayed, replayed, or out-of-order chat messages on weak connectivity.
- Same idempotency key with a different payload must be rejected.
- Client times out after a successful commit and retries.
- Malicious prompt requests SQL, hidden prompts, another driver's data, or an unauthorized action.
- Operator aggregation and detail reads are scoped before aggregation; Admin behavior follows the ratified scope and never inherits authority from its route.

### ETA and time

- Repair duration does not equal ETA shift.
- ETA is missing, uncertain, stale, or corrected multiple times.
- ETA confirmation is stale, unrelated, expired, or changed after display; no mutation occurs until the exact current interpretation is confirmed.
- An older delayed/out-of-order message cannot silently replace a newer authoritative ETA.
- Facility hours cross midnight; offset/time-zone conversion is explicit.
- Rules are effective for only part of a day; unloading crosses a slot or closing time.

### Capacity and appointment

- During Sprint 1-2, any slot-search, book, reschedule, cancel, or confirm request returns the disabled-capability handoff and produces zero appointment writes.
- A dashboard's `operational docks now`/slot snapshot is not described as shipment-feasible, reserved, or bookable capacity.
- Two or more selections race for one slot.
- Selection races confirmation, cancellation, expiry, or replacement.
- Dock closes or capacity shrinks after options are displayed.
- Cancellation releases a slot during another conversation.
- Early arrival does not automatically displace protected work.
- Late, no-show, already waiting, already docked, and unloading-overrun states.
- Reefer-only, heavy vehicle, product, equipment, weight, and duration incompatibilities.
- Higher-priority work enters later; fairness and override explanations remain deterministic.
- Warehouse reply conflicts with database state or external confirmation delivery fails.
- No compatible same-day slot or missing escalation contact.

### Dependency failure

- Upstash Redis unavailable: business REST operations continue; multi-turn chat memory degrades visibly and safely.
- LLM unavailable/slow: no fabricated action; offer deterministic actions or human handoff.
- PostgreSQL unavailable: no success is claimed.
- Audit/outbox failure participates in the business transaction when required for trustworthy completion.

Use seeded scenarios including `SHP1003`, `SHP1004`, `SHP1005`, `SHP1006`, `SHP1010`, `SHP1013`, `SHP1015`, `SHP1016`, `SHP1018`, `SHP1019`, and the competition group `SHP1006/SHP1012/SHP1013/SHP1014`.

## 10. Testing and evidence

- Unit: domain policies, feasibility, status transitions, time-zone rules, idempotency decisions.
- Database integration: repositories, transaction rollback, unique-index conflict mapping, RLS/grants, migration parity.
- API: Supabase login/session, JWT/RBAC/row-scope, token-expiry, account-scope, and logout tests from Sprint 1; individual-user and revocation hardening in Sprint 3; response contracts, validation, idempotent commands, and 409 refresh flow.
- Concurrency: real parallel transactions; assert exactly one active winner and no lost history.
- Frontend: component states and typed API contracts.
- AI: tool-schema tests, golden state-transition conversations, adversarial prompts, ambiguity, and failure fallbacks. Assert tool calls and outcomes, not exact prose.
- E2E: shared Supabase demo-login-to-context in the POC; individual-user login after hardening; delay-to-ETA, option-to-conflict/recovery, no-slot escalation, and operations takeover.

## 11. Success metrics

- Conflicting or duplicate active allocations: **zero**.
- Infeasible confirmed options: **zero**.
- Correct recovery from stale option or race: **100% in acceptance suite**.
- Unauthorized cross-driver/facility access: **zero**.
- Time from first exception message to usable outcome.
- Automation resolution rate and correctly handled escalation rate.
- Driver clarification turns.
- Stale-option rate and booking-conflict recovery time.
- Post-reschedule wait, slot utilization, and policy violations.
- p95 API/tool/chat latency, tool failure rate, and AI token cost.

## 12. Deferred TODO backlog

Keep these visible and unchecked until Sprint 3 passes and the owner explicitly promotes them into a later sprint:

- [ ] TODO (DEFERRED): facility-wide OR-Tools optimization.
- [ ] TODO (DEFERRED): predictive ETA.
- [ ] TODO (DEFERRED): live GPS and map telemetry.
- [ ] TODO (DEFERRED): WhatsApp, SMS, Teams, Slack, and voice channels.
- [ ] TODO (DEFERRED): multilingual support.
- [ ] TODO (DEFERRED): multi-tenant SaaS support.
- [ ] TODO (DEFERRED): national routing.
- [ ] TODO (DEFERRED): carrier selection and rate negotiation.
- [ ] TODO (DEFERRED): commercial penalties.
- [ ] TODO (DEFERRED): autonomous safety or legal decisions.

## 13. Immediate next action

**Sprint 2 exit gate COMPLETE (2026-08-07 19:35 IST).** Next: Sprint 3 deterministic feasibility, ranking, and concurrent appointment allocation. Do not expand into maps, GPS, user management, or non-gate booking UX before Sprint 3 tools/routes exist.
