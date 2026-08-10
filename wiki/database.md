---
title: SetuHaul Database
type: topic
status: compiled
scope: database
last_verified: 2026-08-10
---

# Database

Supabase PostgreSQL is the source of truth. The baseline migration, seed, and SQL verification live under `supabase/`.

Rules:

- Preserve existing business tables unless an approved ADR and additive migration require change.
- Apply migrations; never patch production schema manually.
- RLS, privileges, constraints, transaction boundaries, and concurrency behavior require explicit tests.
- Load the Supabase and Postgres best-practice skills before database changes.
- Redis and Memory MCP are not database substitutes.

## Allocation constraints

The baseline keeps PostgreSQL as the final allocation authority through partial unique indexes:

- `ux_active_appointment_per_slot` prevents more than one active `PENDING_CONFIRMATION`, `CONFIRMED`, or `IN_PROGRESS` appointment per slot.
- `ux_current_active_appointment_per_shipment` prevents more than one current active appointment per shipment.

As of 2026-08-10 20:35 IST, `backend/app/scheduling/allocation.py` translates residual `request_slot` races detected by those indexes into `SLOT_CONFLICT_REFRESH_REQUIRED` with refreshed options and zero appointment writes. `backend/tests/integration/test_live_scheduling_concurrency.py` proves two independent live Supabase sessions competing for the same temporary slot yield exactly one winner and one conflict refresh, then cleans all temporary rows. No schema or RLS change was made; broader load proof and remaining lifecycle transitions are still required before the Sprint 3 exit gate can close.

## Live catalog inspection (2026-08-10 20:23 IST)

Direct read-only asyncpg inspection reached Supabase PostgreSQL 17.6. Public schema contains 23 tables and 4 views; all public tables report RLS enabled and no `pg_policies` rows were present in this inspection. The FastAPI server therefore continues to rely on server-side JWT/RBAC checks plus backend-only database access for application authorization unless/until RLS policies are added and tested.

Seeded table counts:

| Table | Rows |
|---|---:|
| api_logs | 3 |
| appointment_slots | 106 |
| appointments | 22 |
| audit_logs | 9 |
| carriers | 4 |
| chat_messages | 22 |
| chat_threads | 12 |
| dock_status_events | 3 |
| docks | 9 |
| driver_exceptions | 12 |
| drivers | 15 |
| eta_updates | 14 |
| facilities | 2 |
| facility_checkins | 5 |
| facility_contacts | 5 |
| facility_rules | 6 |
| idempotency_requests | 2 |
| operational_messages | 6 |
| roles | 8 |
| shipments | 21 |
| users | 10 |
| vehicle_types | 5 |
| vehicles | 15 |

Public views: `v_current_facility_queue`, `v_inbound_operational_state`, `v_latest_eta`, and `v_slot_availability`.

Scheduling seed distribution:

- Shipments: 11 `IN_TRANSIT`, 3 `ASSIGNED`, 3 `WAITING`, 2 `CANCELLED`, 1 `COMPLETED`, 1 `IN_DOCK`.
- Priorities: 9 `NORMAL`, 6 `HIGH`, 4 `LOW`, 2 `CRITICAL`.
- Appointment states: 11 current `CONFIRMED`, 2 current `PENDING_CONFIRMATION`, 1 current `IN_PROGRESS`, 1 current `COMPLETED`, plus historical cancelled/no-show rows.
- Slot inventory: Gurugram has 27 open slots; Jaipur has 72 open and 7 blocked slots.
- Docks: Gurugram has 3 active docks; Jaipur has 6 active docks including standard, reefer, and heavy types.

Sprint 3-critical indexes are live: `ux_active_appointment_per_slot`, `ux_current_active_appointment_per_shipment`, `ix_slots_facility_time`, `ix_shipments_destination_status`, and idempotency indexes. No writes or migration changes were made during the inspection.

## Supabase MCP diagnosis (2026-08-07 ~15:55 IST)

`.cursor/mcp.json` declares a remote server key named `supabase` (project_ref `kujffzgqjmqphkmrbawy`; no secrets in this file). Cursor exposes that server to agents as **`project-0-Setuhaul-supabase`**, not bare `supabase`.

**Why earlier agents failed to call it:**

1. Called `GetMcpTools(server="supabase")` — wrong id → "server not found".
2. In some earlier sessions the server was not yet loaded/approved in the agent catalog (only `cursor-ide-browser` + `user-memory` appeared), so `mcp_auth` could not run.
3. Once loaded, `serverStatus` is `ready` (auth already satisfied for this session); live tools work.

**Live proof this turn** (`project-0-Setuhaul-supabase` / `execute_sql` + `list_migrations`):

| Table | Rows |
|---|---:|
| roles | 8 |
| users | 10 |
| drivers | 15 |
| facilities | 2 |
| shipments | 21 |
| eta_updates | 12 |
| appointments | 20 |
| appointment_slots | 106 |
| docks | 9 |
| facility_rules | 6 |
| driver_exceptions | 10 |
| audit_logs | 4 |

Migrations applied: `setuhaul_baseline`, `add_users_auth_user_id`.

POC app users (re-verified 2026-08-07 ~16:25 IST):

| user_id | email | role | auth_user_id mapped? |
|---|---|---|---|
| USR001 | ravi.kumar@setuhaul.com | DRIVER | yes |
| USR101 | priya.mehta@setuhaul.com | OPERATIONS_EXECUTIVE | yes |
| USR999 | admin@setuhaul.com | ADMIN | yes |

- `public.users.auth_user_id` exists (uuid, nullable) with unique partial index `users_auth_user_id_uidx`; **3** POC rows mapped.
- `auth.users` total: **3** with matching email identities. Passwords OOB in gitignored `.env.local`. Anon keys populated locally via MCP; `DATABASE_URL` still empty → HTTP `/auth/me` blocked (`DB_UNAVAILABLE`).

Evidence: live MCP SQL 2026-08-07; `supabase/migrations/20260807100550_add_users_auth_user_id.sql`; `docs/DATABASE.md`.

Related: [[architecture]], [[testing]], [[contradictions]], [[handoff]], [[skills-and-mcp]].
