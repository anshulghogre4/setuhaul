# SetuHaul database changelog

Migration files are the executable technical history; this file is the human-readable deployment record. See `SUPABASE_MIGRATION_GUIDE.md` for the workflow and non-negotiable rules. Append one entry per deployed migration.

## 2026-08-06 - SetuHaul baseline

- Status: production
- Local migration: `supabase/migrations/20260805201923_setuhaul_baseline.sql`
- Remote migration: `20260805204004_setuhaul_baseline`
- Objects changed: 22 tables, 4 views, source constraints/indexes, grants, and RLS enablement
- Data/backfill: 300 supplied demonstration rows loaded without value changes
- Compatibility: source table/column names and logical data representations preserved
- Security: all 22 public tables have RLS; no `anon`/`authenticated` policies while Auth is deferred
- Validation: local reset, local/remote parity, view counts, foreign keys, and appointment uniqueness passed
- Rollback/forward fix: recreate a fresh environment from the repository migration and seed; do not remotely reset a non-disposable project
- Notes: MCP assigned a different remote timestamp than the local filename; CLI `db push` migration history is not yet reconciled to this mapping. Moved here from `SUPABASE_MIGRATION_GUIDE.md` per that guide's own instruction.

## 2026-08-17 - Escalation resolution note

- Status: production
- Local migration: `supabase/migrations/20260817040000_escalation_resolution_note.sql`
- Remote migration: applied via direct PostgreSQL connection (Supavisor pooler), not through `supabase db push`/MCP `apply_migration` — Supabase CLI was installed but not linked/authenticated in this environment (`supabase login`/`supabase link` not run). This is a sanctioned connection method per the guide's connection table ("Schema migrations ... Supabase CLI/direct PostgreSQL connection"), but it means **Supabase's own migration-history tracking does not know about this migration**, compounding the existing unreconciled baseline drift. Before the next CLI `db push`, reconcile local migration history (`supabase migration list` vs. what's actually applied) for both this and the baseline mapping.
- Author/reviewer: Claude Code (applied), pending human review
- Objects changed: added nullable `resolution_note text` column to `public.escalation_queue` and `public.driver_exceptions`
- Data/backfill: none; existing rows get `NULL`
- Compatibility: fully additive/backward-compatible — old application code ignores the new column; new code (`backend/app/services/escalation_service.py`, `backend/app/services/driver_reads.py`) reads/writes it
- Security: no RLS/grant changes; both tables already had RLS enabled with no `anon`/`authenticated` policies (unchanged deny-by-default posture)
- Validation: applied via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in a transaction; verified live via `information_schema.columns` (both columns present, `text`, nullable) and unaffected row counts (`escalation_queue=2`, `driver_exceptions=262`, matching pre-migration counts). Local backend unit suite (84 passed, 3 skipped) covers the application-side read/write.
- Rollback/forward fix: reversible — `ALTER TABLE public.escalation_queue DROP COLUMN resolution_note;` / same for `driver_exceptions`; no data would be lost beyond the note text itself since it was never populated before this change.
- Notes: fixes a gap where the Ops "Mark Resolved" remark was accepted by `POST /operations/escalations/{id}/resolve` but silently discarded (no column existed). Applied ahead of the ECS `setuhaul-api` and AgentCore Runtime redeploys so the code paths that depend on this column don't error when those redeploys land; see root `CHANGELOG.md` 2026-08-17 for the paired application-code fix (also includes an unrelated AgentCore event-loop fix from the same session).
