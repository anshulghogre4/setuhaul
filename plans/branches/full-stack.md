# Full-stack branch

## Backend shape

```text
backend/app/
  api/v1/routers/
  core/ auth/ db/ middleware/ observability/
  modules/
    identity/ freight/ exceptions/ appointments/
    scheduling/ facilities/ reporting/ audit/
      domain/ application/ infrastructure/ schemas/
  ai/runtime/ ai/tools/ ai/prompts/
  worker/
tests/
  unit/ integration/ contract/ concurrency/ e2e/
```

## Frontend shape

```text
frontend/src/
  app/
  core/auth/ core/http/ core/guards/
  shared/ui/ shared/models/
  features/auth/{driver-login,ops-login,profile}/
  features/driver/{assistant,profile}/
  features/ops/{dashboard,exceptions,schedule,docks,constraints}/
  layouts/
```

Reuse Stitch markup/assets and design tokens. The documented React 19 stack wins unless the owner changes it through an ADR.

## First milestone

For the internal POC, team members enter through **two** login routes—`/driver/login` and `/ops/login`—that reuse one Supabase Auth implementation. FastAPI verifies the JWT and resolves the subject to trusted seeded role/scope. Operator and Admin share one ops dashboard shell; JWT decides facility vs global RO. Sprint 1 renders the Driver profile/context shell and the read-only Ops dashboard with observational reads; it intentionally contains no AI or business write. Sprint 2 adds driver chat plus one atomic ETA/exception flow and populates the ops dashboard from live reads. Out of POC: maps, GPS, user management, booking mutations.

## Initial API slice

- `GET /health/live`, `GET /health/ready`
- `GET /api/v1/auth/me`
- `GET /api/v1/driver/context`
- `GET /api/v1/shipments/{id}`
- `GET /api/v1/shipments/{id}/appointment/current`
- `GET /api/v1/operations/dashboard-summary`
- `GET /api/v1/operations/exceptions`
- `GET /api/v1/operations/appointment-schedule`
- `GET /api/v1/operations/dock-snapshot`
- `GET /api/v1/operations/facility-constraints`
- `POST /api/v1/shipments/{id}/eta-updates`
- `POST /api/v1/chat`, `GET /api/v1/chat/threads/{id}`

Use cursor pagination for large lists and `Idempotency-Key` on commands. Archive conversation history instead of hard-deleting audit-relevant records.

The POC does not mount shipment-feasible slot search, appointment request, reschedule, cancellation, or confirmation routes. Stored slots/docks/rules may be returned only through timestamped, facility-scoped operational read models.

## CI gates

Frontend lint/typecheck/test; backend lint/typecheck/unit/integration; local Supabase reset and SQL tests; concurrency suite; container build; dependency and secret scan; Playwright critical-path tests.
