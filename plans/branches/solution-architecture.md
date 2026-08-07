# Solution architecture branch

## Position

Use a modular FastAPI monolith plus one worker. Organize it by domain modules and ports/adapters so scheduling or integrations can be extracted later without paying microservice overhead now.

## Key boundaries

- Browser -> FastAPI is a trust boundary.
- FastAPI derives identity and data scope from verified Supabase JWTs. The internal POC prefers shared Driver + Ops accounts (seeded Operator facility-scoped and/or Admin global RO may both exist). **Two entry UIs** (`/driver/login`, `/ops/login`); Operator and Admin share one ops dashboard shell. The verified mapping—not the chosen entry—sets role and scope; individual accounts replace shared credentials before production. IDs supplied by clients are never trusted as ownership evidence.
- AI tools -> application use cases is a policy boundary.
- Application services -> repositories is the transaction boundary.
- PostgreSQL -> Redis/Gemini/external messaging is the authoritative/non-authoritative boundary.
- Appointment/capacity queries -> scheduling commands is a capability boundary. Sprint 1-2 may display timestamped schedule/dock/rule facts but cannot mount feasibility, booking, rescheduling, cancellation, or confirmation commands.

## Reliability stance

- Shallow synchronous request paths for user-facing commands.
- Transactional outbox and worker for external notifications.
- Exponential backoff only for safe/idempotent operations.
- Per-dependency timeouts and graceful degradation.
- Separate liveness and readiness; database readiness is required for business operations, Gemini readiness is not.

## Ownership

Until the team grows, use shared ownership with CODEOWNERS for `backend/app/modules/scheduling`, auth/security, and database migrations. Scheduling and identity changes require review from the architecture owner; AI prompts cannot change business policy.

## Architecture success indicators

- Lead time for a vertical slice.
- Deployment frequency and rollback time.
- Booking conflict and stale-option recovery rates.
- p95 latency/error rates and mean time to recover.
- Number of business policies duplicated outside their owning module: target zero.
