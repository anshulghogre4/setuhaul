---
title: SetuHaul Current Verified State
type: state
status: authoritative
scope: repository
last_verified: 2026-08-07
---

# Current state

## Verified

- Planning, architecture, API/database documentation, Supabase baseline + additive `auth_user_id` migration, seed data, and database tests exist.
- Live hosted DB via MCP `project-0-Setuhaul-supabase` (2026-08-07): **`auth.users=3`**; USR001 / USR101 / USR999 **`auth_user_id` mapped**.
- Sprint 1 scaffolds: `backend/` + `web/`. **Owner POC UI in code:** `/driver/login` and `/ops/login` only; Operator and Admin share `/ops`.
- React 19 frontend; FastAPI API/BFF; Supabase PostgreSQL SoT.
- Product AI (Sprint 2+): LangChain **`ChatOpenAI` + `bind_tools(...)`** + manual bounded invoke loop. Not `create_agent` / `AgentExecutor` / `create_react_agent`.
- Admin POC scope is global read-only (ADR 005). Operator facility-scoped FAC-JAI-01. Driver USR001/DRV001.
- Anon/publishable keys **and** `DATABASE_URL` / service role **populated locally** (gitignored).
- Password-grant JWT + `JwtVerifier` JWKS verify: **PASS** for Driver/Operator/Admin.
- `/health/live` **PASS**; `/health/ready` **PASS** (`database_reachable=true`); `/api/v1/auth/me` **PASS**.
- asyncpg engine uses `statement_cache_size=0` for Supabase PgBouncer compatibility (2026-08-07).
- CORS allowlist includes `http://localhost:5173` and `http://127.0.0.1:5173` (2026-08-07 17:55 IST).
- Browser exit-gate suite **PASS** (2026-08-07 17:55 IST): Admin global RO dashboard + logout; Driver/Operator reconfirm; wrong-portal redirects without elevation; baseline a11y labels/`aria-live`. Screenshots `tmp/poc-screenshots/05`–`10` (gitignored).
- API adversarial/IDOR suite **PASS** (2026-08-07 17:55 IST): missing/invalid/forged → 401; driver IDOR 403; Operator facility vs Admin global; no mutation routes; no web `SERVICE_ROLE`.
- Minimal CI workflow present: `.github/workflows/ci.yml`. Local unit **4 passed**; frontend build **PASS**.
- **Sprint 1 exit gate COMPLETE.** Living status: Sprint 2 ACTIVE / TODO ready to start.

## Verify before claiming

- Formal Playwright suite in CI (local one-shot smoke only).
- Database SQL test files present but **not executed** this session.
- Worker and Docker Compose remain TODO (DEFERRED).
- Full Stitch visual parity (sidebar/search chrome) still partial.
- Deep SQLAlchemy repositories deferred to Sprint 2+.

Related: [[implementation]], [[testing]], [[handoff]], [[database]], [[ai-system]].
