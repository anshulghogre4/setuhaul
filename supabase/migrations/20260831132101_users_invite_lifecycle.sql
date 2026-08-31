-- Give public.users a real lifecycle model (GitHub issues #73 and #81, one change).
--
-- Design citation: SOLUTION_DESIGN.md section 7.5.7 (`invite_user` / `deactivate_user` /
-- `remove_user` -- "reversible, distinct from remove_user");
-- UI-UX/06-admin-console/screens.md section 2 (the Users table's Status column and its fourth row,
-- "-- | amit.d@... | Ops | Gurugram | (quarter-circle) Invited | Resend | Revoke");
-- UI-UX/06-admin-console/flows-and-states.md Flow 1 step 4 ("`INVITED` -> row appears in the list
-- with a pending-invitation badge") and Flow 3/Flow 4 (Deactivate is reversible; Remove is not);
-- UI-UX/06-admin-console/edge-cases.md #8 ("`list_users` only returns active/inactive/pending
-- accounts by default -- a genuinely removed user does not reappear in search").
-- FR-ADM-001 .. FR-ADM-005 (user/role administration), FR-ADM-009 (audit).
--
-- Backup: NOT taken by this file; taken separately before the apply (see below).
-- **APPLIED TO PRODUCTION 2026-08-31 19:1x IST** by direct psql with SET lock_timeout='5s'
-- (not `supabase db push` -- 7 of 13 migrations are untracked in schema_migrations, so a push
-- would re-run already-applied DDL). pg_dump backup of public.users (28 rows) taken first:
-- C:/Users/ANSHUL/setuhaul-db-backups/pre_invite_backup_20260831_191056.dump. Verified after:
-- all three columns present as timestamptz NULL, CHECK constraint present, 0 rows backfilled
-- (deliberate -- see the no-backfill argument below), and the exact deps.py identity SELECT
-- that previously errored (column u.invited_at does not exist) now returns rows.
-- Applying it is the owner's call. It is additive-only (three nullable columns plus one CHECK on
-- a table whose existing rows all satisfy it vacuously), so a pg_dump of public.users before
-- applying is proportionate but not strictly required; the rollback is three DROP COLUMNs.
--
-- Independent of 20260829134929_d2_held_state_dock_occupancy.sql, which is also written but not
-- yet applied: that one touches public.appointments and public.dock_occupancy, this one touches
-- only public.users. Neither reads the other's columns, so they may be applied in either order.
--
-- =============================================================================================
-- Why local columns rather than reading Supabase Auth (the fork #73 named, owner-decided)
-- =============================================================================================
--
-- #73 offered two shapes: (a) local columns, or (b) join GoTrue's admin user list on
-- `auth_user_id` inside `list_users` and read `invited_at IS NOT NULL AND confirmed_at IS NULL`.
-- (b) was rejected for two concrete reasons, not a preference:
--
--   1. It puts a synchronous external HTTP call on the Users tab's *main read*. Every other tool
--      in section 7.5.7 answers from Postgres alone; `list_users` is the one read this console
--      cannot render without.
--   2. `remove_user` DELETEs the Supabase Auth identity outright
--      (`admin_user_service._delete_auth_user`). A removed user therefore has no Auth record at
--      all, so under (b) their status is not "removed", it is *unknown* -- which is exactly the
--      distinction issue #81 exists to restore.
--
-- (a) also closes #81 for free, which (b) structurally cannot. #81's own text says so.
--
-- =============================================================================================
-- The load-bearing question is not the schema, it is what writes invite_accepted_at
-- =============================================================================================
--
-- `users.last_login_ts` (baseline, 20260805201923) is the cautionary tale, and it is in this exact
-- table: it is READ in two places (`account_service.py`, `admin_user_service.list_users`) and
-- WRITTEN nowhere in the application -- only `supabase/seed.sql` sets it. That is why the current
-- "pending" proxy (`last_login_ts IS NULL`) reports every post-seed user as pending forever.
--
-- `invite_accepted_at` is written by `app/core/deps.py::get_execution_context`, the FastAPI
-- dependency every authenticated request in this backend resolves before any router body runs.
-- It is not a site a caller can forget: a route either has an ExecutionContext (so this ran) or is
-- unauthenticated. And a verified JWT whose `sub` equals a user's `auth_user_id` cannot exist
-- until GoTrue itself has accepted that user's invite token and issued a session -- so "we saw a
-- valid token for this subject" IS the acceptance signal, observed rather than reported.
--
-- The write is conditional on `invited_at IS NOT NULL AND invite_accepted_at IS NULL`, both of
-- which the identity SELECT already reads on the same row, so the steady-state cost is exactly
-- zero extra statements. It fires at most once per invited user, ever.
--
-- =============================================================================================

BEGIN;

-- 1. The three lifecycle stamps. timestamptz, not the TEXT the frozen baseline used for
-- `last_login_ts`/`created_at`: every column added since 20260823090000 (user_scopes.created_at)
-- has been timestamptz, and the Supabase Postgres best-practices rule "Time: use timestamptz, not
-- timestamp" applies a fortiori against text. Nullable with no default -- a NULL here is a real
-- fact ("this never happened"), which is precisely what each state below is derived from.
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS invited_at         timestamptz,
  ADD COLUMN IF NOT EXISTS invite_accepted_at timestamptz,
  ADD COLUMN IF NOT EXISTS removed_at         timestamptz;

COMMENT ON COLUMN public.users.invited_at IS
  'Set by admin_user_service.invite_user when the Supabase Auth invite is sent. NULL for every '
  'seeded/pre-existing account, which is correct: those were never invited through this console, '
  'so they are ACTIVE, not pending.';

COMMENT ON COLUMN public.users.invite_accepted_at IS
  'Set by core/deps.py::get_execution_context on the first authenticated request this user ever '
  'makes -- the only point in this system guaranteed to observe acceptance. Never written by an '
  'admin tool. See this migration''s header for why that site and not a client-reported one.';

COMMENT ON COLUMN public.users.removed_at IS
  'Set by admin_user_service.remove_user (and revoke_invite). This is the discriminator issue #81 '
  'asked for: remove_user and deactivate_user both land on is_active = 0, so is_active alone '
  'cannot tell a reversible deactivation from a permanent removal. NULL means "not removed", '
  'including for every row that predates this migration -- see step 3.';

-- 2. Acceptance implies invitation. Pins the one invariant the write site depends on: because
-- get_execution_context only stamps when `invited_at IS NOT NULL`, a row can never carry an
-- accept stamp without an invite stamp. If a future change ever stamps unconditionally, this
-- constraint fails loudly at that write rather than silently producing an un-deriveable state.
--
-- PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS (supabase-postgres-best-practices,
-- schema-constraints), so the existence check is explicit.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'users_accept_implies_invite_chk'
      AND conrelid = 'public.users'::regclass
  ) THEN
    ALTER TABLE public.users
      ADD CONSTRAINT users_accept_implies_invite_chk
      CHECK (invite_accepted_at IS NULL OR invited_at IS NOT NULL);
  END IF;
END $$;

-- 3. **No backfill, deliberately -- read this before adding one later.**
--
-- `invited_at`: left NULL for every existing row. Those accounts were seeded or created before
-- this console existed; stamping them would make the entire pre-existing user list render as
-- "Invited, awaiting acceptance", which is the exact failure mode of the `last_login_ts` proxy
-- this migration exists to retire.
--
-- `removed_at`: left NULL for every existing row, including rows already at `is_active = 0`.
-- Those rows are genuinely ambiguous -- that ambiguity IS issue #81, and it is not retroactively
-- resolvable from the users table (audit_logs carries a 'DELETE'/'users' row per removal, but
-- reconstructing state from an audit trail inside a schema migration would be inventing data
-- this project's own rules forbid). Existing inactive users therefore read as DEACTIVATED, the
-- safer of the two wrong answers: a removed user shown as deactivated is visible and correctable
-- by an admin, whereas a deactivated user shown as removed silently disappears from the console.
--
-- If the owner later wants those rows classified, the correct move is a one-off reconciliation
-- script driven by audit_logs, reviewed as its own change -- not a guess inside this file.

-- 4. **No index, deliberately.** `list_users` gains `WHERE u.removed_at IS NULL` and already
-- carries `LIMIT 200`, so a partial index on that predicate would be the textbook shape --
-- but public.users holds tens of rows against a 5-concurrent-user product, where a sequential
-- scan is strictly faster than an index probe and the index is pure write-side and storage cost.
-- Stated rather than omitted so a later reader knows it was considered, not overlooked. Revisit
-- if this table ever passes a few thousand rows.

COMMIT;

-- ---------------------------------------------------------------------------------------------
-- Rollback
-- ---------------------------------------------------------------------------------------------
-- BEGIN;
--   ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_accept_implies_invite_chk;
--   ALTER TABLE public.users
--     DROP COLUMN IF EXISTS invited_at,
--     DROP COLUMN IF EXISTS invite_accepted_at,
--     DROP COLUMN IF EXISTS removed_at;
-- COMMIT;
--
-- Revert alongside it: backend/app/services/admin_user_service.py (lifecycle derivation,
-- invited_at/removed_at writes, resend_invite/revoke_invite), backend/app/core/deps.py (the
-- accept stamp in get_execution_context), backend/app/api/v1/routers/admin.py (the two new
-- routes and the include_removed query parameter). Re-check afterwards: `GET /api/v1/admin/users`
-- still returns rows, and any authenticated request still resolves an ExecutionContext.
--
-- Note on RLS, checked and deliberately not changed here: public.users does not have row-level
-- security enabled (only public.idempotency_requests and public.escalation_queue do). This
-- backend reaches Postgres over DATABASE_URL with a direct connection, not PostgREST, and
-- enabling RLS on the identity table is a materially riskier change than three nullable columns.
-- Flagged for the owner as a separate question, not folded into this migration.
