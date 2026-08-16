# SetuHaul Supabase Migration and Seeding Guide

## Purpose

This is the authoritative runbook for moving the supplied SetuHaul classroom database into the hosted Supabase project and managing future database changes safely.

Target project:

- Project URL: `https://kujffzgqjmqphkmrbawy.supabase.co`
- Project reference: `kujffzgqjmqphkmrbawy`
- Target database: Supabase PostgreSQL

The baseline migration and seed are complete. This document now serves both as the deployment record and the operating procedure for every future schema change.

### Current hosted status

Verified through the project-scoped Supabase MCP on 2026-08-06:

- MCP target: `https://kujffzgqjmqphkmrbawy.supabase.co`
- Remote migration: `20260805204004_setuhaul_baseline`
- Public tables: 22, all with RLS enabled
- Views: 4
- Seed rows: exactly 300
- Remote parity suite: passed
- Appointment partial-uniqueness tests: passed
- Auth integration: intentionally deferred
- `anon` and `authenticated`: no application-table grants or RLS policies yet

The Security Advisor reports informational `rls_enabled_no_policy` notices. This is the intended deny-by-default state while Auth is deferred. The Performance Advisor reports missing foreign-key index and unused-index suggestions. Those suggestions were recorded but not applied because the baseline had to remain structurally identical to the supplied source. Evaluate them in separate, reviewed migrations after real query patterns exist.

Local tooling used for validation:

- Supabase CLI `2.109.0`
- Docker CLI/engine `29.6.2`, used only for the disposable local Supabase PostgreSQL stack
- Node.js `22.18.0` and npm `10.7.0`

Docker is not part of the production runtime and is unrelated to Redis. Upstash remains the managed Redis service.

## Source material found in this repository

The database package currently contains:

- `docs/database_docs/setuhaul_schema_and_seed.sql`: 77 KB combined SQLite schema and seed script.
- `docs/database_docs/setuhaul_database_guide.md`: data model, row counts, constraints, views, edge cases, and starter queries.
- `docs/database_docs/setuhaul_data_dictionary.csv`: field-level reference.
- `docs/database_docs/setuhaul_er_diagram_core.png`: core ER diagram.

The `.db` file named by the database guide is not present in the repository. Therefore, the combined SQL file is the available source of truth unless a newer database export is supplied.

The SQL defines 22 tables: 18 operational/conversation tables plus `roles`, `users`, `audit_logs`, and `api_logs`. It also defines four views and several indexes, including partial unique indexes protecting active appointment allocation.

The ER diagram is a required migration validation source, not optional artwork. The PostgreSQL baseline must be checked against the diagram for entities, primary keys, foreign keys, relationship direction, and cardinality. If the diagram, SQL, data dictionary, and database guide disagree, stop and document the conflict before applying a migration. Executable SQL does not silently override the intended domain model.

## Recommended migration strategy

Use the Supabase CLI and versioned PostgreSQL migrations. Do not paste the combined SQLite script directly into the production SQL Editor, and do not make the hosted dashboard the primary place where schema changes are authored.

The repository now contains:

```text
supabase/
  config.toml
  migrations/
    20260805201923_setuhaul_baseline.sql
    <future timestamp>_<change>.sql
  seed.sql
  tests/
    database/
      parity.sql
      appointment_constraints.sql
  tools/
    build_postgres_baseline.py
  README.md
```

This gives us reproducible local, staging, and production databases. Future `ALTER TABLE`, index, function, policy, and view changes must be added as new migration files. An already-applied migration must never be edited to represent a later change.

## Why the supplied SQL needs conversion

The current file was produced for SQLite and is not a safe PostgreSQL migration as-is:

1. Tables are created in an order that references tables not yet created. PostgreSQL requires referenced tables to exist when foreign keys are defined.
2. Seed rows are also inserted before their referenced parent rows. PostgreSQL foreign keys would reject this order.
3. SQLite and PostgreSQL differ in default-expression and view syntax.
4. Table and seed order had to be changed without changing the model or values.
5. Views exposed through the Data API need an explicit security decision.
6. Tables created with raw SQL require explicit grants and Row Level Security configuration.
The completed baseline deliberately preserved the source table names, column names, logical `TEXT`/`INTEGER` representations, constraints, indexes, views, and values to avoid regression. It made only PostgreSQL-required compatibility changes, including foreign-key-safe ordering, PostgreSQL default syntax, `security_invoker` views, grants, and RLS enablement. Any future type modernization must be a separate migration with application compatibility tests.

## Proposed target design

### Schemas

Use `public` for application tables only if they need the Supabase Data API. Keep sensitive/internal-only database objects in a non-exposed schema such as `private` when practical.

For the first migration, preserving the existing table names and text business identifiers is safer than redesigning the model. IDs such as `SHP1001`, `DRV001`, and `FAC-JAI-01` are domain identifiers and should remain `text`.

### Authentication

Auth was intentionally deferred. The baseline therefore preserves `public.users`, including its supplied columns and seed rows, and does not create or link `auth.users` records. RLS remains deny-by-default for browser roles.

When Auth is introduced, create a new migration rather than editing the baseline. A likely design is an `auth_user_id uuid unique references auth.users(id)` column while retaining SetuHaul profile, role, driver, and facility fields in `public.users`. Password ownership must eventually move to Supabase Auth; do not expose or treat the legacy `password_hash` field as a Supabase credential.

### Data types

Current baseline mappings:

| SQLite representation | PostgreSQL target |
|---|---|
| Domain IDs in `TEXT` | `text` |
| Instant timestamps with `+05:30` | `text`, preserved for baseline parity |
| Facility `open_time` / `close_time` | `text`, preserved for baseline parity |
| `0` / `1` flags | `integer` plus source checks |
| Integer counts and minutes | `integer` |
| Weight values | `integer` unless future precision requires `numeric` |
| JSON payload text | `text`, preserved for baseline parity |
| Free-form notes/messages | `text` |

Do not silently change these types in application work. If typed timestamps, booleans, or `jsonb` become desirable, use a new expand-and-contract migration and verify every dependent query and view.

### Creation order

The baseline migration should create parent tables before dependent tables. A safe high-level order is:

1. `carriers`, `vehicle_types`, `facilities`, `roles`
2. `docks`, `drivers`, `facility_contacts`, `facility_rules`
3. `vehicles`
4. `shipments`
5. `appointment_slots`, `chat_threads`
6. `appointments`, `eta_updates`, `facility_checkins`, `dock_status_events`, `driver_exceptions`, `chat_messages`
7. `operational_messages`
8. `users`
9. `audit_logs`, `api_logs`
10. Indexes, views, grants, RLS policies, and validation functions

The seed files should follow the same dependency order.

### Scheduling integrity

Preserve and test both partial unique indexes:

- Only one current active appointment per slot.
- Only one current active appointment per shipment.

PostgreSQL must remain the final concurrency authority. A later migration may add an explicit slot-hold model, idempotency keys, or transactional booking function, but the initial port must not weaken the existing uniqueness guarantees.

### Row Level Security

Enable RLS explicitly on every table in an exposed schema. Start from deny-by-default and add policies only after the role-to-data-access matrix is approved.

Initial safety posture:

- `anon`: no operational table access.
- `authenticated`: only the rows/actions permitted for the signed-in role.
- Backend administrative access: secret key or controlled PostgreSQL connection only; never expose it to the browser.
- Views: `security_invoker = true` when they are intentionally exposed, or revoke access/place them in a private schema.

Do not create permissive placeholder policies merely to make the frontend work.

As of the 2026 Supabase Data API exposure change, new tables may not receive automatic `anon` or `authenticated` grants. Every exposed table must therefore have explicit, reviewed grants in migration code in addition to RLS. Tables used only through FastAPI should not be granted to public API roles merely for convenience.

## Connection choices

Use different connection mechanisms for different jobs:

| Use case | Recommended connection |
|---|---|
| Schema migrations, dumps, restoration, administrative scripts | Supabase CLI/direct PostgreSQL connection; use Supavisor session mode if the machine is IPv4-only |
| Persistent FastAPI/SQLAlchemy backend | Direct connection when IPv6 is available; otherwise Supavisor session mode |
| Serverless or short-lived workloads | Supavisor transaction mode; disable prepared statements if required by the driver |
| Browser/frontend | Supabase client/Data API with the publishable key and RLS |
| Privileged backend Data API operations | Supabase secret key, stored only in a backend secret manager |

The project URL is not a database connection string and is not sufficient for migrations.

Do not default to legacy `anon` and `service_role` keys. For new application work, prefer Supabase publishable and secret keys. The secret key bypasses RLS and must never be committed, pasted into documentation, exposed in frontend code, or sent in URLs.

## Legacy database decision

The preferred path is an offline conversion of the supplied SQL into clean PostgreSQL migrations and seeds. There is no need to connect the hosted Supabase project to a legacy SQLite database.

Use a legacy source connection only if:

- A newer source database exists outside this repository.
- The supplied SQL is incomplete.
- Row-count or data-parity checks reveal missing records.
- We need a one-time export to resolve compatibility issues.

If a legacy source is required, treat it as read-only and perform an export/import. Do not build permanent runtime synchronization unless that becomes a separate approved requirement.

## Baseline execution phases (completed)

### Phase 0: Confirm safety and ownership

Before any connection or write:

1. Confirm that project reference `kujffzgqjmqphkmrbawy` is the intended SetuHaul project.
2. Confirm whether it is empty, disposable development, staging, or production.
3. Inventory existing remote schemas/tables. If it is not empty, pull/dump the remote schema and take a backup before planning changes.
4. Choose either local Supabase validation with Docker or controlled validation against the empty hosted development project. Docker is recommended for isolation but is not required.
5. Confirm the Supabase region/network path and whether direct IPv6 connectivity is available.
6. Decide whether Auth is part of this release. For the baseline it was deferred.
7. Approve the initial RLS posture. For the baseline it was deny-by-default with no client policies.

### Phase 1: Initialize local Supabase workflow
The local workflow was initialized after approval:

```powershell
npx supabase init
```

The hosted deployment used the already authenticated, project-scoped Supabase MCP connection. CLI login/link credentials were not required for that deployment.

If the remote project already contains database objects, run `npx supabase db pull` before authoring the SetuHaul baseline and review the generated migration.

Do not pass passwords or tokens directly in commands that may be recorded in shell history. Prefer the CLI prompt, native credential storage, or temporary environment variables.

### Phase 2: Build PostgreSQL migrations and seeds

1. Split schema from data.
2. Reorder tables and inserts by foreign-key dependency.
3. Convert only the syntax required by PostgreSQL while preserving baseline logical types and constraints.
4. Preserve partial unique indexes.
5. Recreate views using PostgreSQL syntax and the chosen security model.
6. Add explicit grants and RLS enablement; defer policies until the access model exists.
7. Put only data insertion statements in `seed.sql`.
8. Preserve the source column order and values for the baseline.
9. Keep resumable deployment transport separate from the authoritative seed file.

Do not blindly transform the file with string replacements. Each table, constraint, and view must be reviewed.

### Phase 3: Validate locally

With Docker available:

```powershell
npx supabase start
npx supabase db reset --local
```

If Docker is intentionally not used, validate the migration SQL offline first, review it, and then apply it to the confirmed empty development project in controlled phases. After each phase, run verification queries and Supabase Security/Performance Advisors before continuing. Do not combine an untested schema conversion and the complete seed import into one irreversible remote step.

Validation must cover:

- All migrations apply from an empty database.
- All seed files load without disabling foreign keys.
- Table row counts match the database guide.
- Orphan foreign keys: zero.
- Both active-appointment uniqueness constraints reject conflicts.
- The four views return expected records.
- Timestamp ordering and `Asia/Kolkata` display behavior are correct.
- RLS denies unauthenticated access and permits only approved authenticated cases.
- A clean reset produces the same result every time.

### Phase 4: Review the hosted project

Before the baseline write, MCP `list_tables` and `list_migrations` confirmed an empty application schema and migration history. For future CLI deployments, use:

```powershell
npx supabase projects list
npx supabase db push --dry-run
```

Review the linked project, migration list, target schemas, destructive statements, grants, and seed behavior. Stop if the project reference is wrong or the dry run contains unexpected drops.

### Phase 5: Apply the baseline

The baseline schema was applied with MCP `apply_migration`, and the seed was loaded with MCP `execute_sql` in complete transactional statement batches. For future CLI deployments to an explicitly confirmed development/staging project:

```powershell
npx supabase db push
npx supabase db push --include-seed
```

Use `--include-seed` only when the hosted target is intended to contain this classroom/demo dataset. Do not seed production implicitly.

Never run `supabase db reset --linked` against a non-disposable project. It drops remote data and replays migrations.

### Phase 6: Post-migration verification

1. Query table and view row counts.
2. Run the starter queries from the database guide.
3. Test the duplicate appointment constraints.
4. Verify RLS as `anon`, an authenticated driver, an operations user, and an administrator.
5. Verify that the preserved legacy `public.users.password_hash` data remains inaccessible to browser roles and is not treated as Supabase Auth data.
6. Generate application types if useful.
7. Record the migration version and verification output.
8. Take or confirm a recoverable backup before application development begins.

## Baseline deployment record: 2026-08-06

The completed baseline was produced and deployed as follows:

1. Audited every database document: the SQLite schema/seed, database guide, data dictionary, and ER diagram.
2. Executed the SQLite source in memory and confirmed zero foreign-key violations.
3. Confirmed the expected baseline: 22 tables, 4 views, 15 source indexes, and 300 rows.
4. Created `supabase/` as the version-controlled database reference point.
5. Added a deterministic converter at `supabase/tools/build_postgres_baseline.py`. It validates the source and generates the PostgreSQL migration, seed, and parity assertions.
6. Generated `supabase/migrations/20260805201923_setuhaul_baseline.sql` and `supabase/seed.sql` without modifying the source database documents.
7. Started a disposable local Supabase PostgreSQL stack with Docker, ran a clean reset, and applied the migration plus seed.
8. Ran `supabase/tests/database/parity.sql` and `appointment_constraints.sql` locally. Both passed.
9. Rechecked the hosted project through MCP and confirmed it had no application tables or migrations before the first write.
10. Applied the schema through MCP `apply_migration`. Supabase recorded remote migration `20260805204004_setuhaul_baseline`.
11. Loaded the seed through MCP. Because the full file exceeded the shell-to-MCP transport boundary, it was replayed as complete SQL-statement batches. An interrupted prefix was resumed idempotently with `ON CONFLICT DO NOTHING`; no source values were changed.
12. Ran the complete remote parity and appointment-constraint suites. The final hosted state contains exactly 300 rows and matches all expected view counts.
13. Ran Supabase Security and Performance Advisors. No suggested schema optimizations were applied because they were outside the exact-parity baseline.

The local migration filename and MCP-generated remote version have different timestamps. Before using CLI `db push` for the first future deployment, reconcile this known mapping deliberately. Do not run `migration repair` blindly. Verify that the local baseline SQL matches the deployed schema, then either align the uncommitted local filename with the recorded remote version or use a reviewed migration-history repair. Record the chosen action in the changelog.

## Future schema changes from this repository

This project uses imperative, timestamped migrations. It does not currently use `supabase/schemas/` declarative files. Do not mix the two workflows casually.

### Non-negotiable rules

1. Never edit `20260805201923_setuhaul_baseline.sql` after it has been applied.
2. Every schema change gets a new file under `supabase/migrations/`.
3. Create migration filenames with `supabase migration new <snake_case_name>`; do not invent timestamps manually.
4. Author and review SQL in the repository before any hosted write.
5. Test the whole history from an empty local database, not only the newest statement.
6. Keep schema changes, data backfills, grants, RLS policies, tests, generated application types, and changelog notes in the same pull request when they belong to the same release.
7. Do not alter the remote database through the Dashboard Table Editor or SQL Editor. Emergency remote changes must be pulled into a migration and documented immediately.
8. Never run `supabase db reset --linked` against this hosted project unless it is explicitly classified as disposable and destructive approval has been given.

### Standard change workflow

From the repository root:

```powershell
supabase migration new add_tracking_reference_to_shipments
```

Edit the generated SQL file, add or update tests, and then validate:

```powershell
supabase start
supabase db reset --local
supabase db query --local --file supabase/tests/database/parity.sql
supabase db query --local --file supabase/tests/database/<new_test>.sql
```

Also run the Security and Performance Advisors. Review informational findings rather than automatically applying every suggestion. After validation, inspect `git diff`, update the changelog entry, and deploy through exactly one of the following lanes.

### Preferred deployment lane: Supabase CLI

Use this after the baseline migration-history mapping has been reconciled:

```powershell
supabase login
supabase link --project-ref kujffzgqjmqphkmrbawy
supabase migration list
supabase db push --dry-run
supabase db push
supabase migration list
```

The dry run must show only the reviewed migration. Stop on unexpected drops, grants, policies, or history drift. Only one team member or CI deployment job should push at a time.

### MCP deployment lane

MCP is appropriate when the project-scoped Supabase connection is authenticated and CLI credentials are unavailable. The code-first rule still applies:

1. Use the Supabase and Supabase PostgreSQL best-practices skills before authoring SQL.
2. Create a local migration file with `supabase migration new <name>`.
3. Write and locally validate the migration.
4. Use MCP `list_tables` and `list_migrations` for the remote preflight.
5. Use MCP `apply_migration` with the exact reviewed migration contents for DDL. Do not use `execute_sql` for a committed schema change because it bypasses migration history.
6. Use MCP `execute_sql` only for read-only verification, tests, or separately reviewed data manipulation.
7. Run MCP `list_migrations`, `list_tables`, `get_advisors`, and targeted verification queries after deployment.
8. Record the MCP-generated remote migration version beside the local migration filename.

MCP generates the remote migration timestamp. If it differs from the new local filename, rename the not-yet-committed local file to the returned remote version and rerun the local reset before committing. If the file was already shared or committed, do not rewrite team history; stop and reconcile with `supabase migration list` and a reviewed `migration repair` plan.

Do not alternate CLI and MCP deployment lanes without checking migration history first.

### Suggested coding-agent request

For a future change, give the agent a scoped request like this:

```text
Use the Supabase and Supabase PostgreSQL best-practices skills. Inspect the
current migrations, database tests, data dictionary, ER diagram, and remote
migration list. Create a new migration in code to add <change>. Do not edit an
applied migration. Validate with a clean local reset, add regression tests,
run the advisors, and update the database changelog. Show me the migration and
dry-run result before applying it remotely.
```

After review and explicit deployment approval:

```text
Apply only the reviewed pending migration to project
kujffzgqjmqphkmrbawy using the selected CLI or MCP deployment lane. Verify the
remote schema, migration version, advisors, and regression tests, then update
the changelog with the deployed version and results.
```

The skills provide the workflow and safety rules; MCP provides authenticated project access. Neither replaces the migration file, tests, code review, or changelog.

## Column-change recipes

These are patterns, not copy-paste authorization. Replace names and types only after checking the data dictionary, ER relationships, application code, views, indexes, RLS, and existing data.

### Add an optional column

Create a migration, then use a nullable column so existing rows and old application versions remain valid:

```sql
alter table public.shipments
add column tracking_reference text;
```

Migration history guarantees that this statement runs once; failing loudly on an unexpected existing column is safer than hiding schema drift. Add a test that checks the column type, nullability, and representative reads/writes. Add an index only if a real query filters, joins, or sorts on the field often enough to justify it.

### Add a required column safely

Do not immediately add a volatile default and `not null` to a large active table. Use expand-and-contract:

1. Migration A adds the column as nullable.
2. Deploy application code that can work with both states and writes the new value.
3. Backfill existing rows in controlled batches.
4. Verify that no nulls remain.
5. Migration B adds and validates the constraint, then makes the column required.

Example finalization:

```sql
alter table public.shipments
add constraint shipments_tracking_reference_present
check (tracking_reference is not null) not valid;

alter table public.shipments
validate constraint shipments_tracking_reference_present;

alter table public.shipments
alter column tracking_reference set not null;

alter table public.shipments
drop constraint shipments_tracking_reference_present;
```

Keep transactions short and set a sensible `lock_timeout` for migrations that may wait on active traffic.

### Change a column type

First prove every current value can be converted:

```sql
select shipment_id, existing_column
from public.shipments
where existing_column is not null
  and existing_column !~ '<expected-format>';
```

For a small, compatible table, a reviewed migration may use an explicit conversion:

```sql
alter table public.shipments
alter column existing_column type timestamptz
using existing_column::timestamptz;
```

For a risky or heavily used column, prefer a new typed column, dual-write application code, a batched backfill, read cutover, and removal of the old column in a later release. Recreate or update dependent views, indexes, constraints, functions, generated types, and tests in the correct migration.

### Rename or remove a column

A direct rename breaks old application versions. Prefer:

1. Add the new column.
2. Dual-read/dual-write temporarily.
3. Backfill and validate.
4. Switch all consumers.
5. Remove the old column in a later migration after backup and explicit approval.

Dropping a column is destructive and must never be bundled into the same deployment that introduces its replacement.

### Add constraints and foreign keys

PostgreSQL does not support `ADD CONSTRAINT IF NOT EXISTS`. Check `pg_constraint` in a `DO` block when idempotency is required. Add a covering index for foreign-key columns when the access pattern or cascade behavior needs it. Validate constraints against existing data before making them authoritative.

## Database changelog policy

Migration files are the executable technical history; Git is the immutable review history. Maintain a human-readable database section in this guide or create `supabase/CHANGELOG.md` when the next migration is opened. From that point, append one entry per deployed migration in the same pull request.

Use this template:

```markdown
## YYYY-MM-DD — Short change title

- Status: proposed | local-verified | staging | production
- Local migration: `supabase/migrations/<timestamp>_<name>.sql`
- Remote migration: `<version>_<name>` or `not deployed`
- Author/reviewer: <names>
- Objects changed: <tables, columns, views, indexes, policies>
- Data/backfill: <none or exact procedure and counts>
- Compatibility: <application versions and rollout order>
- Security: <RLS, grants, advisor findings>
- Validation: <tests, counts, queries, advisor results>
- Rollback/forward fix: <safe recovery procedure>
- Notes: <decisions, follow-up work, issue/PR link>
```

Changelog rules:

- Add the entry when the migration is authored and update its status after each environment.
- Never store passwords, tokens, keys, connection strings, or production personal data.
- Never rewrite an old deployed migration to match a changelog description. Correct mistakes with a new migration and a linked changelog entry.
- Record local-to-remote migration version mappings whenever MCP assigns the remote timestamp.
- Record row counts before and after backfills and retain the verification SQL in `supabase/tests/database/` when reusable.
- A rollback note does not mean every change is safely reversible. For destructive or lossy changes, document backup/restore requirements and prefer a forward-fix migration.

### Current changelog entry

New deployed-migration entries now go in `supabase/CHANGELOG.md` (created 2026-08-17 per this section's own instruction), not here. The baseline entry below is retained for history.

#### 2026-08-06 - SetuHaul baseline

- Status: hosted baseline deployed and verified
- Local migration: `supabase/migrations/20260805201923_setuhaul_baseline.sql`
- Remote migration: `20260805204004_setuhaul_baseline`
- Objects changed: 22 tables, 4 views, source constraints/indexes, grants, and RLS enablement
- Data/backfill: 300 supplied demonstration rows loaded without value changes
- Compatibility: source table/column names and logical data representations preserved
- Security: all 22 public tables have RLS; no `anon`/`authenticated` policies while Auth is deferred
- Validation: local reset, local/remote parity, view counts, foreign keys, and appointment uniqueness passed
- Recovery: recreate a fresh environment from the repository migration and seed; do not remotely reset a non-disposable project
- Notes: MCP assigned a different remote timestamp; reconcile the known local/remote mapping before the first CLI push

## Information required for future integrations and deployments

Do not send secrets in repository files or commit them. Before the next hosted schema deployment or application integration, confirm:

1. Confirmation that project ref `kujffzgqjmqphkmrbawy` is correct.
2. The environment classification: development, staging, or production.
3. Permission to perform read-only inventory and backup/dump operations before risky changes.
4. A Supabase personal access token for CLI authentication, preferably supplied through `supabase login` or `SUPABASE_ACCESS_TOKEN`, not pasted into source files.
5. The project database password for CLI linking/migrations, preferably entered at the prompt or through a temporary `SUPABASE_DB_PASSWORD` environment variable.
6. Docker availability for the required local reset and migration verification.
7. Whether any newer legacy database/export supersedes the checked-in baseline.
8. The desired Auth mapping and whether real Auth accounts should now be created.
9. The driver/operations/admin RLS access matrix before any browser grants are added.

An API key is not sufficient for schema migrations. Application API keys will be needed later for frontend/backend integration, but migration access should use the CLI/database credentials described above.

## Upstash Redis relationship

Upstash Redis and Supabase PostgreSQL are separate managed services. They do not need a direct infrastructure link.

The FastAPI/LangChain backend will connect to both:

```text
Frontend
   |
   v
FastAPI / LangChain
   |-- Supabase Auth and PostgreSQL: durable identities and business data
   `-- Upstash Redis: cache, sessions, short-lived conversation state, rate limits, and distributed coordination where appropriate
```

Supabase remains the durable source of truth. Upstash data must be reconstructable or safely expirable. Redis must never be the final authority for appointment uniqueness; PostgreSQL constraints and transactions remain authoritative.

No local Redis container is required. The application will use Upstash credentials through backend environment variables or a secret manager. A direct Supabase-to-Upstash integration is only needed if a future event-driven workflow explicitly requires database events to publish to Redis; it is not required for database creation or seeding.

## Secret-handling rules

- Never commit `.env` files containing credentials.
- Never place access tokens, database passwords, secret keys, or connection strings in Markdown.
- Prefer interactive login or the platform's secret/credential storage.
- Use a publishable key in frontend code.
- Use a secret key only in trusted backend infrastructure.
- Rotate any credential that is accidentally exposed.
- Redact credentials from logs and screenshots.

## Official Supabase references

- Local development and schema migrations: https://supabase.com/docs/guides/local-development/overview
- CLI workflow: https://supabase.com/docs/guides/local-development/cli-workflows
- Database migrations: https://supabase.com/docs/guides/deployment/database-migrations
- Supabase CLI: https://supabase.com/docs/guides/local-development/cli/getting-started
- Supabase MCP: https://supabase.com/docs/guides/getting-started/mcp
- Supabase agent skills: https://supabase.com/docs/guides/getting-started/ai-skills
- Database seeding: https://supabase.com/docs/guides/local-development/seeding-your-database
- Database connections and poolers: https://supabase.com/docs/guides/database/connecting-to-postgres
- Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security
- API keys: https://supabase.com/docs/guides/getting-started/api-keys
- Migrating to publishable/secret keys: https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys
- PostgreSQL migration guidance: https://supabase.com/docs/guides/platform/migrating-to-supabase/postgres

## Immediate next step

The baseline deployment is complete for project `kujffzgqjmqphkmrbawy`.

- Remote migration: `20260805204004_setuhaul_baseline`
- Schema: 22 public tables, 4 views, and the source indexes/constraints
- Seed: exactly 300 rows; all repository parity assertions pass remotely
- Security: RLS is enabled on all 22 tables; no client policies exist because Auth is deferred

Before the first future CLI push, reconcile the documented local/remote baseline timestamp mapping. The next application phase is to define backend secret storage and design the Auth/RLS access matrix before granting `anon` or `authenticated` access. Any schema change must start as a new timestamped migration in `supabase/migrations`; do not edit the applied baseline. When that change is opened, create `supabase/CHANGELOG.md` from the template above and move/copy the current baseline entry into it.
