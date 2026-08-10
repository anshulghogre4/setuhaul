---
title: SetuHaul Testing and Evidence
type: topic
status: compiled
scope: testing
last_verified: 2026-08-10
---

# Testing

Current executable evidence:

- Database tests under `supabase/tests/database/` (present; not executed this session).
- Live Supabase catalog/seed inspection: **PASS** (2026-08-10 20:23 IST, direct read-only asyncpg). Verified PostgreSQL 17.6, `auth.users=3`, public schema 23 tables + 4 views, seeded operational counts, RLS enabled flags, and Sprint 3 scheduling guard indexes. No data or schema writes were made.
- Live same-slot concurrency proof: **PASS** (2026-08-10 20:35 IST, `SETUHAUL_RUN_LIVE_DB_TESTS=1` with `DATABASE_URL`, `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\integration\test_live_scheduling_concurrency.py -q` from `backend/`). Two independent async sessions requested the same temporary live Supabase slot; exactly one won, one received conflict refresh, audit/idempotency evidence existed, and post-run cleanup found zero `CODX` rows.
- Backend tests: **41 passed, 1 live integration skipped by default** (2026-08-10 20:35 IST, `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests -q` from `backend/`). This includes scheduling constraints, deterministic feasible-slot scoring/ranking factors, feasibility checks, allocation command schema, appointment request status mapping, PostgreSQL allocation unique-constraint translation, Redis memory snapshot/degraded behavior, and Driver LangChain tool allowlist coverage.
- FastAPI import smoke: **PASS** (2026-08-10 20:16 IST, `from app.main import create_app; app=create_app()` returned 11 routes).
- Frontend production build: **PASS** (`npm run build`, 2026-08-07 17:55 IST).
- Minimal CI workflow: `.github/workflows/ci.yml` (backend unit + frontend build) — present; not yet observed on GitHub Actions runners.
- Live Auth: MCP `auth.users=3`, USR001/USR101/USR999 mapped.
- Password-grant JWT (Driver/Operator/Admin): **PASS**.
- `JwtVerifier` JWKS verify for those tokens: **PASS**; forged/malformed JWT → **401** (fixed 2026-08-07 17:55 IST).
- `GET /health/live`: **PASS**. `GET /health/ready`: **PASS** (`database_reachable=true`).
- `GET /api/v1/auth/me` with real JWTs: **PASS**.
- `GET /api/v1/driver/context` (Driver JWT): **PASS** after asyncpg `statement_cache_size=0`.
- `GET /api/v1/operations/dashboard-summary`: Operator facility **PASS**; Admin global **PASS**; Operator cross-facility **403 PASS**; Driver **403 PASS**.
- IDOR: Driver `SHP1017` **200**; Driver `SHP1002` **403**.
- Auth adversarial: missing/invalid/forged Bearer → **401**.
- CORS OPTIONS: `localhost:5173` and `127.0.0.1:5173` **PASS**.
- No scheduling mutation routes / no web `SERVICE_ROLE`: **PASS**.
- Browser exit-gate smoke (Playwright one-shot, 2026-08-07 17:55 IST): **PASS**
  - Admin `/ops/login` → `/ops` global RO + logout
  - Driver + Operator reconfirm
  - Wrong-portal redirects without elevation
  - Baseline a11y labels + `aria-live`
  - Screenshots: `tmp/poc-screenshots/05`–`10` (plus earlier `01`–`04`)

Required layers:

- Database parity, constraints, and RLS policy tests. Real two-client same-slot concurrency now has live proof; broader 10-driver/3-4-slot load testing remains.
- FastAPI unit/integration/API tests for auth, scope, validation, idempotency, and failures.
- Frontend component/type checks and accessibility states beyond baseline.
- Playwright E2E in CI for login-to-context and later ETA/allocation flows.
- AI evaluation for tool selection, clarification, authorization, dependency failure, and fabricated-data resistance.

Never report a check as passing unless it ran in the current relevant state.

Related: [[implementation]], [[database]], [[ai-system]].
