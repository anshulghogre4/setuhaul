# SetuHaul Supabase Database

This directory is the version-controlled reference point for the SetuHaul Supabase PostgreSQL database.

## Baseline source

The authoritative source snapshot is:

`docs/database_docs/setuhaul_schema_and_seed.sql`

The baseline preserves its 22 tables, columns, logical data types, primary and foreign keys, checks, unique constraints, 15 explicit indexes, 4 views, and seed rows. Authentication integration is intentionally deferred; `public.users` remains the application table defined by the source snapshot and is not linked to `auth.users` yet.

The schema must also agree with:

- `docs/database_docs/setuhaul_er_diagram_core.png`
- `docs/database_docs/setuhaul_data_dictionary.csv`
- `docs/database_docs/setuhaul_database_guide.md`

## Files

- `migrations/*_setuhaul_baseline.sql`: PostgreSQL/Supabase baseline schema.
- `seed.sql`: complete dependency-ordered seed snapshot.
- `tests/database/parity.sql`: row-count and view regression checks.
- `tests/database/appointment_constraints.sql`: active-appointment uniqueness regression checks.
- `tools/build_postgres_baseline.py`: deterministic converter and source validator.
- `config.toml`: local Supabase configuration.
- `SUPABASE_MIGRATION_GUIDE.md`: full deployment and future-change runbook.

## Hosted baseline status

The baseline was deployed to Supabase project `kujffzgqjmqphkmrbawy` on 2026-08-06 through the project-scoped Supabase MCP connection.

- Remote migration: `20260805204004_setuhaul_baseline`
- Public tables: 22, all with RLS enabled
- Seed rows: 300
- Views: 4, with parity checks passing
- Auth integration: intentionally deferred

The remote migration timestamp is Supabase-generated; the repository migration remains the authoritative reviewed SQL. The seed was replayed idempotently after an interrupted transport attempt, and the complete remote parity and appointment-constraint test suites passed afterward.

### What was done

1. Audited the source SQL, database guide, data dictionary, and ER diagram.
2. Executed and validated the SQLite source with zero foreign-key violations.
3. Confirmed the expected 22 tables, 4 views, 15 source indexes, and 300 rows.
4. Generated a PostgreSQL-compatible migration and dependency-ordered seed without changing the source files or logical data model.
5. Enabled RLS on all public tables, revoked browser-role access, and made views `security_invoker`.
6. Rebuilt the database locally through Docker and ran the parity and appointment-constraint suites.
7. Confirmed the hosted project was empty, then applied the schema with MCP `apply_migration`.
8. Loaded the exact seed through complete transactional SQL-statement batches. The resumable transport used `ON CONFLICT DO NOTHING` after an interruption; the authoritative `seed.sql` values were not changed.
9. Re-ran all parity checks remotely and confirmed exactly 300 rows.
10. Ran the Supabase Security and Performance Advisors. Suggested optimizations were not added to the frozen baseline.

The local baseline filename is `20260805201923_setuhaul_baseline.sql`, while MCP recorded remote version `20260805204004_setuhaul_baseline`. Reconcile this known mapping before the first CLI `db push`; never use `migration repair` without first comparing the actual schema and migration history.

## Regenerate

```powershell
python supabase/tools/build_postgres_baseline.py `
  --migration supabase/migrations/<existing-baseline-file>.sql
```

The converter refuses to generate output if the SQLite source develops foreign-key violations or its known row/view counts change.

## Local verification

```powershell
supabase start
supabase db reset --local
```

Then run `tests/database/parity.sql` against the local database.

```powershell
supabase db query --local --file supabase/tests/database/parity.sql
supabase db query --local --file supabase/tests/database/appointment_constraints.sql
```

## Change policy

Never edit an applied migration. Create a new migration for every later schema change:

```powershell
supabase migration new <descriptive_change_name>
```

Validate locally, review the remote dry run, and then apply it to the linked project. The hosted database must not become the only copy of a change.

## Future migration workflow

This repository uses imperative migrations. It does not currently use `supabase/schemas/` declarative schemas.

For every table, column, index, view, function, grant, or RLS change:

1. Load the Supabase and Supabase PostgreSQL best-practices skills.
2. Inspect existing migrations, tests, database docs, ER relationships, and remote migration state.
3. Create the file with `supabase migration new <snake_case_name>`; never invent a timestamp manually.
4. Write the SQL in that new file. Never edit an applied migration.
5. Add or update regression tests and the database changelog.
6. Run a clean local reset and all database tests.
7. Run Security and Performance Advisors and review the findings.
8. Review the exact diff and remote dry run.
9. Apply through one deployment lane only.
10. Verify the hosted migration, schema, data compatibility, tests, and advisors; then mark the changelog entry deployed.

### Preferred CLI deployment lane

After the baseline timestamp mapping is reconciled:

```powershell
supabase login
supabase link --project-ref kujffzgqjmqphkmrbawy
supabase migration list
supabase db push --dry-run
supabase db push
supabase migration list
```

Stop if the dry run contains an unexpected drop, grant, policy, seed action, or migration-history difference. Only one person or CI job should deploy at a time.

### MCP deployment lane

When using the authenticated project-scoped MCP connection:

1. Create and locally test the migration file first.
2. Run MCP `list_tables` and `list_migrations` as a remote preflight.
3. Apply the exact reviewed DDL with MCP `apply_migration`.
4. Do not use MCP `execute_sql` for committed DDL because it bypasses migration history. Reserve it for read-only verification, tests, or separately reviewed data changes.
5. Run `list_migrations`, `list_tables`, `get_advisors`, and targeted regression queries afterward.
6. Record the MCP-generated remote version in the changelog.

If MCP assigns a timestamp different from a new, not-yet-committed local migration, rename the local file to the returned remote version and rerun the clean local reset before committing. If the file is already shared, stop and create a reviewed reconciliation plan. Do not alternate MCP and CLI deployment lanes without checking migration history.

## Adding or altering columns

### Add an optional column

```powershell
supabase migration new add_tracking_reference_to_shipments
```

In the generated migration:

```sql
alter table public.shipments
add column tracking_reference text;
```

Keep it nullable initially so existing rows and older application versions remain compatible. Let the migration fail if the column unexpectedly exists; this exposes drift instead of hiding it.

### Add a required column

Use expand-and-contract:

1. Add the column as nullable.
2. Deploy code that writes the new field while tolerating old rows.
3. Backfill existing rows in controlled batches.
4. Verify no nulls remain.
5. Add and validate a check constraint.
6. Set `not null` in a later migration.

Keep transactions short and use an appropriate `lock_timeout` for changes on active tables.

### Change a type, rename, or remove a column

Run a preflight query proving all values can be converted. For small compatible changes, use an explicit `USING` expression. For risky changes, add a new typed column, dual-write, backfill, switch reads, and remove the old column in a later release.

Do not directly rename a field consumed by older application versions. Do not drop a column in the same deployment that introduces its replacement. Dropping data requires explicit approval, a recovery plan, and an appropriate backup.

Update every dependent view, index, constraint, function, generated application type, and regression test in the correct migration.

## Coding-agent request template

```text
Use the Supabase and Supabase PostgreSQL best-practices skills. Inspect the
current migrations, database tests, data dictionary, ER diagram, and remote
migration list. Create a new migration in code for <change>. Do not edit an
applied migration. Validate it with a clean local reset, add regression tests,
run the advisors, and update the database changelog. Show the migration and
dry-run result before applying it remotely.
```

The skills supply the workflow and database safety rules; MCP supplies authenticated project access. Neither replaces migration code, tests, review, or the changelog.

## Database changelog

Migration files are the executable history and Git is the review history. Create `supabase/CHANGELOG.md` when the next migration is opened, copy the baseline record from the migration guide into it, and append one entry per migration.

Each entry must include:

- Date, title, and deployment status.
- Local migration filename and remote migration version.
- Tables, columns, views, indexes, grants, or policies changed.
- Backfill procedure and before/after row counts.
- Application compatibility and rollout order.
- RLS/grant changes and advisor findings.
- Tests and verification results.
- Rollback, restore, or forward-fix procedure.
- Reviewer and issue/pull-request reference.

Never put secrets or personal production data in the changelog. Never rewrite a deployed migration; correct it with a new migration and linked changelog entry.

## Security posture

The baseline enables RLS but defines no frontend policies because authentication is deferred. `anon` and `authenticated` receive no table access. The backend may later use a controlled PostgreSQL connection or a server-side Supabase secret after authorization rules are designed.

The informational `rls_enabled_no_policy` Advisor notices are therefore expected. Do not add permissive placeholder policies merely to remove the notices. When Auth is introduced, add the Auth mapping, grants, RLS policies, and tests through new migrations.

## Full guide and official references

- Project runbook: `supabase/SUPABASE_MIGRATION_GUIDE.md`
- Supabase local workflow: https://supabase.com/docs/guides/local-development/cli-workflows
- Database migrations: https://supabase.com/docs/guides/deployment/database-migrations
- MCP setup: https://supabase.com/docs/guides/getting-started/mcp
- Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security
