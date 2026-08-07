---
title: SetuHaul Testing and Evidence
type: topic
status: compiled
scope: testing
last_verified: 2026-08-07
---

# Testing

Current executable evidence:

- Database tests under `supabase/tests/database/` (present; not executed this session).
- Backend unit tests: **4 passed** (2026-08-07 17:55 IST, `pytest tests/unit`).
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

- Database parity, constraints, RLS, and concurrency tests.
- FastAPI unit/integration/API tests for auth, scope, validation, idempotency, and failures.
- Frontend component/type checks and accessibility states beyond baseline.
- Playwright E2E in CI for login-to-context and later ETA/allocation flows.
- AI evaluation for tool selection, clarification, authorization, dependency failure, and fabricated-data resistance.

Never report a check as passing unless it ran in the current relevant state.

Related: [[implementation]], [[database]], [[ai-system]].
