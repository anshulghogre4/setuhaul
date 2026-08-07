# Architecture Decision Records (Sprint 1)

Status: ratified for internal POC — 2026-08-07  
Source: `plans/implementation-master-plan.md`, owner decisions.

## ADR 001 — Modular monolith

**Decision:** FastAPI modular monolith with ports/adapters and domain modules. One API process + one worker later.

**Why:** Single team, evolving domain, transactional booking correctness is easier in one database boundary.

## ADR 002 — PostgreSQL concurrency authority

**Decision:** Supabase PostgreSQL constraints and transactions are the final double-booking guard. Redis and the LLM never authorize scarce capacity.

## ADR 003 — Appointment lifecycle language

**Decision:** Product copy must distinguish `displayed` (not reserved), `requested`/`held`, `pending`, `confirmed`, `expired`, `rejected`, `cancelled`, and `conflicted`. Sprint 1–2 may only **observe** stored appointment/slot/dock/rule state. Mutations begin in Sprint 3.

## ADR 004 — Deterministic feasibility

**Decision:** Feasibility and ranking are versioned deterministic services outside the LLM. N/A until Sprint 3.

## ADR 005 — Supabase Auth and POC accounts

**Decision:** Real Supabase Auth from Sprint 1. Prefer shared Driver + Ops Auth accounts. Seeded application users may include three personas that map to **two login UIs**:

| Login entry | Seeded app user | Role | Scope |
|---|---|---|---|
| `/driver/login` | `USR001` (`ravi.kumar@setuhaul.com`) | `ROL001` DRIVER | Own driver `DRV001`; facility `FAC-JAI-01` context |
| `/ops/login` (shared) | `USR101` (`priya.mehta@setuhaul.com`) | `ROL002` OPERATIONS_EXECUTIVE | Facility `FAC-JAI-01` only |
| `/ops/login` (shared) | `USR999` (`admin@setuhaul.com`) | `ROL008` ADMIN | **Global read-only** (no facility_id) |

Operator and Admin share one ops dashboard shell; JWT/ExecutionContext decides facility vs global RO. FastAPI verifies JWT (issuer, JWKS, audience, expiry, subject), maps `auth.users.id` → `public.users.auth_user_id`, builds trusted `ExecutionContext`. Portal URL never grants role. Shared credentials are internal-only; replace with individual users before production.

## ADR 006 — Redis non-authoritative

**Decision:** Upstash Redis holds bounded conversation/session state with 24-hour TTL. Loss of Redis must not corrupt business state.

## ADR 007 — Idempotency and audit

**Decision:** Commands carry `Idempotency-Key`. Partial failures roll back business effects. Audit participates with the business transaction when trustworthiness requires it. Additive control tables preferred when needed (see ADR 010).

## ADR 008 — Timestamps

**Decision:** Baseline stores timestamps as text. Validate strict ISO-8601 with offsets in adapters; do not rewrite the applied baseline in Sprint 1.

## ADR 009 — Human takeover

**Decision:** Escalation/manual override rules apply when no feasible slot or contradictory warehouse replies exist (Sprint 3+). POC returns `CAPABILITY_NOT_ENABLED` for scheduling asks.

## ADR 010 — Additive control tables

**Decision:** Prefer additive tables (`auth_user_id` link now; later `idempotency_requests`, `slot_holds`, `outbox_events`) without destructive changes to frozen business tables. `public.users.password_hash` is never used for login.

## ADR 011 — One conversational assistant (ChatOpenAI + bind_tools, not create_agent)

**Decision:** One runtime assistant using LangChain **`ChatOpenAI`** with **`bind_tools(...)`** on a curated role-scoped tool list, plus a **custom bounded invoke loop** (`invoke` → tool_calls → service-backed `ToolMessage`s → final text).

```text
llm = ChatOpenAI(...).bind_tools(role_scoped_tools)
# custom run_assistant loop — not create_agent / AgentExecutor
# bind_tools + manual loop ≠ create_agent
```

Do **not** use `create_agent`, `AgentExecutor`, or `create_react_agent`. Tools call FastAPI application services only (no SQL in tools). PostgreSQL is SoT; LLM never invents operational facts. Upstash holds 24h non-authoritative conversation/session memory (Sprint 2+). Planning personas are development reviewers, not production agents.

## ADR 012 — React 19 frontend

**Decision:** React 19 + Vite SPA using Stitch set `stitch_setuhaul_ai_logistics_platform_2`. Do not build an Angular variant.

---

## Endpoint × role × scope matrix (Sprint 1–2)

| Endpoint | Driver | Operator (facility) | Admin (global RO) |
|---|---|---|---|
| `GET /api/v1/auth/me` | own profile | own profile | own profile |
| `GET /api/v1/driver/context` | own only | deny | deny (use ops reads) |
| `GET /api/v1/shipments/{id}` | own shipments | facility shipments | all (read) |
| `GET /api/v1/shipments/{id}/appointment/current` | own | facility | all (read) |
| `GET /api/v1/operations/dashboard-summary` | deny | assigned facility | global |
| `GET /api/v1/operations/exceptions` | deny | assigned facility | global |
| `GET /api/v1/operations/appointment-schedule` | deny | assigned facility | global |
| `GET /api/v1/operations/dock-snapshot` | deny | assigned facility | global |
| `GET /api/v1/operations/facility-constraints` | deny | assigned facility | global |
| `POST /api/v1/shipments/{id}/eta-updates` | own (Sprint 2) | deny | deny |
| `POST /api/v1/chat` | own thread (Sprint 2) | optional later | optional later |
| Scheduling mutations | absent until Sprint 3 | absent | absent |

Client-supplied `driver_id` / `facility_id` / `user_id` are ignored for authorization.
