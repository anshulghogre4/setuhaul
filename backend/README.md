# SetuHaul Backend

Sprint 1 FastAPI walking skeleton: JWT → `ExecutionContext`, scoped read APIs, health probes.

## Run

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill secrets locally
uvicorn app.main:app --reload --port 8000
```

## Auth mapping

1. Apply migration `supabase/migrations/20260807100550_add_users_auth_user_id.sql` (already applied on hosted project via MCP).
2. Create/link POC Auth users with `docs/scripts/create_poc_auth_users.py` using service-role + private passwords in env (never commit).

## Endpoints (Sprint 1)

- `GET /health/live`, `GET /health/ready`
- `GET /api/v1/auth/me`
- `GET /api/v1/driver/context`
- `GET /api/v1/shipments/{id}`, `GET /api/v1/shipments/{id}/appointment/current`
- `GET /api/v1/operations/dashboard-summary|exceptions|appointment-schedule|dock-snapshot|facility-constraints`

No chat / ChatOpenAI invoke and no scheduling mutations in Sprint 1.
