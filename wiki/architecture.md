---
title: SetuHaul Architecture
type: topic
status: compiled
scope: architecture
last_verified: 2026-08-07
---

# Architecture

SetuHaul is a modular application built as a React 19 SPA, FastAPI API/BFF, asynchronous worker, Supabase Auth/PostgreSQL, Upstash Redis (24h non-authoritative conversation/session memory from Sprint 2), and one role-aware LangChain assistant (`ChatOpenAI` + `bind_tools` + manual bounded invoke loop; not `create_agent` / `AgentExecutor` / `create_react_agent`).

Sprint 1–2 UI is a simple **two-entry** internal POC: `/driver/login` → driver chat/profile/logout; `/ops/login` → shared Operator/Admin read-only dashboard (JWT sets facility vs global RO). No maps, GPS, user management, or booking mutations in the POC. Scheduling mutations begin in Sprint 3.

Core invariants:

- PostgreSQL is authoritative for business facts and concurrency.
- FastAPI derives trusted execution context from verified Supabase tokens. Entry choice never grants a role.
- Routers are thin; services own business rules; repositories own persistence.
- The AI layer uses typed tools that call FastAPI application services only; never executes SQL; never invents operational facts.
- Redis state is bounded, namespaced, expiring, and non-authoritative.
- Business writes require validation, authorization, idempotency, audit logging, and confirmed backend results.

Evidence: `docs/ARCHITECTURE.md`, `plans/implementation-master-plan.md`, `plans/branches/solution-architecture.md`.

Related: [[database]], [[ai-system]], [[implementation]].
