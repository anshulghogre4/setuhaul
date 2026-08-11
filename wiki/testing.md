---
title: SetuHaul Testing and Evidence
type: topic
status: compiled
scope: testing
last_verified: 2026-08-11
---

# Testing

Current executable evidence:

- Database tests under `supabase/tests/database/` (present; not executed this session).
- Live Supabase catalog/seed inspection: **PASS** (2026-08-10 20:23 IST, direct read-only asyncpg). Verified PostgreSQL 17.6, `auth.users=3`, public schema 23 tables + 4 views, seeded operational counts, RLS enabled flags, and Sprint 3 scheduling guard indexes. No data or schema writes were made.
- Live same-slot concurrency proof: **PASS** (2026-08-10 20:35 IST, `SETUHAUL_RUN_LIVE_DB_TESTS=1` with `DATABASE_URL`, `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\integration\test_live_scheduling_concurrency.py -q` from `backend/`). Two independent async sessions requested the same temporary live Supabase slot; exactly one won, one received conflict refresh, audit/idempotency evidence existed, and post-run cleanup found zero `CODX` rows.
- Backend tests: **50 passed, 1 live integration skipped by default** (2026-08-11 23:25 IST, `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests -q` from `backend/`). Focused scheduling allocation tests passed 10/10 and cover Driver cancellation and ops confirmation happy-path writes/commit plus Driver tool registration. The suite also retains scheduling constraints, deterministic feasibility/ranking, allocation race mapping, Redis memory, and LLM factory coverage.
- Sprint 3 lifecycle/stale/escalation focused unit suite: **PASS** (2026-08-12 00:00 IST): `python -m pytest tests/unit/test_scheduling_allocation.py tests/unit/test_scheduling_feasibility.py tests/unit/test_escalation_service.py tests/unit/test_redis_memory.py -q` → **29 passed**. It covers recommendation hashing, EXPIRED status mapping, strict lifecycle/escalation command validation, Redis stale markers, and Driver reschedule/escalation tool registration. `python -m compileall app` also passed.
- Backend env smoke: **PASS** (2026-08-10 23:24 IST). `Settings()` from both repo root and `backend/` resolved gitignored env without printing secrets and reported Gemini provider/model plus `ready_llm=True` and `ready_upstash=True`.
- FastAPI OpenAPI smoke: **PASS** (2026-08-11 23:25 IST); both shipment-scoped appointment `/cancel` and `/confirm` paths are mounted.
- Frontend lint/build: **PASS** (`npm run lint`, `npm run build`, 2026-08-12 00:00 IST).
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
- Historical Sprint 1 no-scheduling-route proof remains valid only for that gate; Sprint 3 now intentionally mounts request/cancel/confirm scheduling routes. No web `SERVICE_ROLE` exposure was introduced.
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
