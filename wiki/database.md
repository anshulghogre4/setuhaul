---
title: SetuHaul Database
type: topic
status: compiled
scope: database
last_verified: 2026-08-07
---

# Database

Supabase PostgreSQL is the source of truth. The baseline migration, seed, and SQL verification live under `supabase/`.

Rules:

- Preserve existing business tables unless an approved ADR and additive migration require change.
- Apply migrations; never patch production schema manually.
- RLS, privileges, constraints, transaction boundaries, and concurrency behavior require explicit tests.
- Load the Supabase and Postgres best-practice skills before database changes.
- Redis and Memory MCP are not database substitutes.

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
