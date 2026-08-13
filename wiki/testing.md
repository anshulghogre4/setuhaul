---
title: SetuHaul Testing and Evidence
type: topic
status: compiled
scope: testing
last_verified: 2026-08-14
---

# Testing

Current executable evidence:

- Sprint 4 Step 9 BFF → AgentCore: **PASS** (2026-08-14 02:52 IST). Express `setuhaul-api` one revision, ARN set, task role `setuhaul-bff-task-role`. `docs/scripts/smoke_hosted_step9.py` exit 0: Ravi grant **200**; `/auth/me` `USR001`/`DRIVER`/`DRV001`; `POST /chat/message` **200** tool `get_driver_operational_context`. `agentcore.cmd logs --since 15m` shows Runtime OTEL `gen_ai_agent` at 21:20 UTC. LangSmith project `setuhaul-agentcore` has `setuhaul.chat` + `get_driver_operational_context` success 21:20 UTC. Vercel not rebuilt. Locust not run. Residual OTEL exporter credential recursion in Runtime logs.
- Sprint 4 Step 8 AgentCore Runtime: **PASS** (2026-08-14 02:28 IST). `agentcore.cmd deploy` stack `AgentCore-SetuHaulAgent-default`; status READY `SetuHaulAgent_SetuHaulAgent-18B4pX4XF1`. `agentcore.cmd invoke --prompt-file docs/scripts/agentcore_invoke_ravi.json` session `setuhaul-dev-session-000000000000000002` returned a real assistant reply (not the execution_context error): tool `list_active_shipments`, `ux=answered`, `source=postgresql`, shipments `SHP-D16-RACE-A` / `SHP-D16-RAVI` / `SHP1017`. Focused units **2 passed** (`test_agentcore_unwraps_cli_prompt_file_json`, `test_agentcore_ssm_map_is_names_only`). `agentcore dev --logs` not run. Hosted BFF ARN still blank (in-process chat).
- Sprint 4 Step 7 hosted Vercel + BFF: **PASS** (2026-08-14 01:51 IST). Production `https://setuhaul-roan.vercel.app` from `main` `91cb6bb` (PR #5) READY. `/driver/login` and `/ops/login` **200**. Ravi password-grant **200**; BFF `/api/v1/auth/me` **200** `USR001`/`DRIVER`/`DRV001`; `POST /api/v1/chat/message` **200** `success=true` tool `get_driver_operational_context`. CORS ACAO `https://setuhaul-roan.vercel.app`. Earlier 01:40 inspect of pre-merge `677c218` (login 404) is superseded.
- Sprint 4 Step 7 Vercel `main` deploy inspect: **superseded** (2026-08-14 01:40 IST). Pre-merge `677c218` had login 404s; fixed by PR #5 + `vercel.json`.
- Sprint 4 Step 6 public DNS recheck: **PASS for internet / Vercel** (2026-08-14 01:04 IST). 8.8.8.8 and 1.1.1.1 resolve `se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws`; `/health/live` **200**. Laptop default resolver still NXDOMAIN after flush.
- Sprint 4 Step 6 hosted BFF: **PASS** (2026-08-14 01:00 IST). App Runner probe `SubscriptionRequiredException`. ECS Express Mode `setuhaul-api`; ALB target healthy; `GET /health/live` **200** at `https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws` (via ALB IP + Host because laptop `on.aws` DNS lagged). ARN blank.
- Sprint 4 Step 5 ECR push: **PASS** (2026-08-14 00:45 IST). `aws ecr describe-images --repository-name setuhaul-api` tag `latest` digest `sha256:250201c7605d5257fc66bb0daaf7e64f6fa1be77018a1d2adb149ceafbd6af2f` (local `setuhaul-api:step1` / `:latest`).
- Sprint 4 Step 4 AWS identity + SSM: **PASS** (2026-08-14 00:28 IST). `aws sts get-caller-identity` owner root `us-east-1`. `get-parameters-by-path /setuhaul` returned 8 names (no `--with-decryption`). `database-url` put as pooler `:6543`. CDK bootstrap already present. Helper: `docs/scripts/put_hosting_ssm.py`.
- Sprint 4 Step 3 local Docker: **PASS** (2026-08-14 00:20 IST). `docker run` `setuhaul-api:step1` as `setuhaul-step3` `-p 18000:8000`, ARN blank, env from gitignored `.env`/`.env.local` (not logged). `GET http://127.0.0.1:18000/health/live` **200**; Docker health **healthy**. Ravi grant **200**; container `/api/v1/auth/me` **200** `USR001`/`DRIVER`/`DRV001`; `/api/v1/driver/context` **200** `SHP-D16-RACE-A`; `POST /api/v1/chat/message` **200** `ux=answered` `list_active_shipments`. Container stopped after smoke.
- Sprint 4 Step 2 browser Driver chat: **PASS** (2026-08-14 00:16 IST). Owner login on `http://localhost:5173/driver` as Ravi `USR001`/`DRV001`. UI composer “Do I have a current appointment?”; assistant: no active appointment; uvicorn `POST /api/v1/chat/message` **200**.
- Sprint 4 Step 2 local smoke: **PASS** (2026-08-14 00:12 IST). ARN blank. Ravi grant **200**; `GET /health/live` **200**; `GET /api/v1/auth/me` **200** `USR001`/`DRIVER`/`DRV001`; `GET /api/v1/driver/context` **200** `SHP-D16-RACE-A`; `POST /api/v1/chat/message` **200** `ux=answered` `list_active_shipments`; Vite `http://localhost:5173/` **200**. Password from gitignored `POC_TEAM_ACCOUNTS.local.md` (not logged). Interactive browser password fill not used. Units not re-run.
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
