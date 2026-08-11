---
title: SetuHaul Database
type: topic
status: compiled
scope: database
last_verified: 2026-08-12
---

# Database

Supabase PostgreSQL is the source of truth. The baseline migration, seed, and SQL verification live under `supabase/`.

Rules:

- Preserve existing business tables unless an approved ADR and additive migration require change.
- Apply migrations; never patch production schema manually.
- RLS, privileges, constraints, transaction boundaries, and concurrency behavior require explicit tests.
- Load the Supabase and Postgres best-practice skills before database changes.
- Redis is not a database substitute.

## Sprint 3 lifecycle + escalation (2026-08-12)

Migration `supabase/migrations/20260812010000_sprint3_lifecycle_escalation.sql` (applied live):

- Widens `appointments.appointment_status` to include `EXPIRED`.
- Widens `audit_logs.action_type` for `RESCHEDULE_APPOINTMENT`, `REJECT_APPOINTMENT`, `EXPIRE_APPOINTMENT`.
- Adds backend-only `escalation_queue` (RLS on; revoke anon/authenticated; grant service_role/postgres) with unique `dedupe_key` for idempotent NOSLOT/human escalations.

## Driver facility contacts column fix (2026-08-11 22:35 IST)

`facility_contacts.contact_role` is the authoritative column name (baseline migration + `docs/database_docs/setuhaul_data_dictionary.csv`). `backend/app/services/driver_reads.py` `get_facility_details` incorrectly selected `role_title`; corrected to `contact_role`. Live MCP SQL for `FAC-JAI-01` returns three contacts. Browser Driver chat then invoked `get_facility_details` without SQL failure.

Seed naming drift for demo login: `public.users` `USR001` full_name `Ravi Kumar` maps to `drivers.DRV001` whose `driver_name` is `Rajesh Kumar`. Auth/profile uses users; driver context rail prefers `drivers.driver_name`.

## Allocation constraints

The baseline keeps PostgreSQL as the final allocation authority through partial unique indexes:

- `ux_active_appointment_per_slot` prevents more than one active `PENDING_CONFIRMATION`, `CONFIRMED`, or `IN_PROGRESS` appointment per slot.
- `ux_current_active_appointment_per_shipment` prevents more than one current active appointment per shipment.

As of 2026-08-10 20:35 IST, `backend/app/scheduling/allocation.py` translates residual `request_slot` races detected by those indexes into `SLOT_CONFLICT_REFRESH_REQUIRED` with refreshed options and zero appointment writes. `backend/tests/integration/test_live_scheduling_concurrency.py` proves two independent live Supabase sessions competing for the same temporary slot yield exactly one winner and one conflict refresh, then cleans all temporary rows.

On 2026-08-11, cancel/confirm lifecycle services were added without a schema or RLS change. Cancellation moves an active appointment to `CANCELLED` and sets `is_current=0`, so it immediately leaves both partial-index predicates and releases the slot/current-shipment claim. Confirmation changes only `PENDING_CONFIRMATION` to `CONFIRMED`, retaining the same active claim. Both transitions lock the exact appointment, write idempotency and audit records, and commit atomically. The baseline audit action check already supports `CANCEL_APPOINTMENT`; confirmation is recorded as allowed action `UPDATE` with the precise transition/reference in audit JSON.

## Sprint 3 lifecycle and escalation migration (2026-08-12)

`supabase/migrations/20260812010000_sprint3_lifecycle_escalation.sql` widens the baseline appointment lifecycle check to include `EXPIRED` and widens the constrained audit action set for `RESCHEDULE_APPOINTMENT`, `REJECT_APPOINTMENT`, and `EXPIRE_APPOINTMENT`. It locates the baseline auto-named checks through `pg_constraint` before replacing them.

The migration adds `public.escalation_queue`, an RLS-enabled, backend-only durable queue keyed by a daily shipment/type `dedupe_key`, with shipment/facility/driver FKs, typed escalation/status checks, payload JSON text, policy/recommendation metadata, and a facility/status/created index. It has not been applied or parity-tested against live Supabase in this turn.

## Live POC Auth expansion (2026-08-10 22:11 IST)

Six additional real-name Supabase Auth users were created and mapped to `public.users.auth_user_id` without schema changes:

| user_id | email | role |
|---|---|---|
| USR002 | amit.singh@setuhaul.com | DRIVER |
| USR003 | vikas.sharma@setuhaul.com | DRIVER |
| USR107 | kavita.rao@setuhaul.com | OPERATIONS_EXECUTIVE |
| USR108 | arvind.nair@setuhaul.com | OPERATIONS_EXECUTIVE |
| USR997 | meera.iyer@setuhaul.com | ADMIN |
| USR998 | suresh.menon@setuhaul.com | ADMIN |

Drivers reused seeded app-user rows; Ops/Admin rows were inserted where missing. Supabase password-grant login returned `200` for each account, and each mapped app-user row has a non-null `auth_user_id`. Passwords are not recorded in checked-in docs.

## Full Auth inventory (2026-08-10 23:05 IST)

All 14 `public.users` rows now have Auth. Role-shared passwords stay in gitignored `.env` / `.env.local` only. The Auth create/reset script was removed from the repo.

| Bucket | Password env | user_id / email | seed role | portal |
|---|---|---|---|---|
| Driver | `SETUHAUL_POC_DRIVER_PASSWORD` | USR001 ravi.kumar | DRIVER | driver |
| Driver | same | USR002 amit.singh | DRIVER | driver |
| Driver | same | USR003 vikas.sharma | DRIVER | driver |
| Operations | `SETUHAUL_POC_OPERATOR_PASSWORD` | USR101 priya.mehta | OPERATIONS_EXECUTIVE | ops |
| Operations | same | USR107 kavita.rao | OPERATIONS_EXECUTIVE | ops |
| Operations | same | USR108 arvind.nair | OPERATIONS_EXECUTIVE | ops |
| Operations | same | USR102 rahul.verma | WAREHOUSE_PLANNER | ops |
| Operations | same | USR103 anjali.kapoor | OPERATIONS_MANAGER | ops |
| Operations | same | USR104 deepak.joshi | FACILITY_MANAGER | ops |
| Admin | `SETUHAUL_POC_ADMIN_PASSWORD` | USR999 admin | ADMIN | ops |
| Admin | same | USR997 meera.iyer | ADMIN | ops |
| Admin | same | USR998 suresh.menon | ADMIN | ops |
| Admin | same | USR105 sanjay.gupta | TRANSPORT_MANAGER | ops |
| Admin | same | USR106 neha.bansal | REGIONAL_OPERATIONS_HEAD | ops |

Proof: earlier 2026-08-10 inventory was `auth.users=14` all mapped. **2026-08-11 23:34 IST:** +12 Driver Auth users for demo contention (`USR201`–`USR212` / `DRV004`–`DRV015`), same shared Driver password, **no resets** of existing accounts. Live mapped Auth users ≈ **26**. Passwords remain only in gitignored `POC_TEAM_ACCOUNTS.local.md`.

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

POC app users (historical 2026-08-07 snapshot; superseded by [[#Full Auth inventory (2026-08-10 23:05 IST)]] above):

| user_id | email | role | auth_user_id mapped? |
|---|---|---|---|
| USR001 | ravi.kumar@setuhaul.com | DRIVER | yes |
| USR101 | priya.mehta@setuhaul.com | OPERATIONS_EXECUTIVE | yes |
| USR999 | admin@setuhaul.com | ADMIN | yes |

- `public.users.auth_user_id` exists (uuid, nullable) with unique partial index `users_auth_user_id_uidx`. Current live totals (2026-08-10 23:05 IST): **14** mapped, `auth.users=14`, unmapped=`0`.
- Passwords OOB in gitignored `.env` / `.env.local` only; Auth create/reset script removed from repo.

Evidence: live MCP SQL 2026-08-10; `supabase/migrations/20260807100550_add_users_auth_user_id.sql`; `docs/DATABASE.md`.

Related: [[architecture]], [[testing]], [[contradictions]], [[handoff]], [[skills-and-mcp]].
