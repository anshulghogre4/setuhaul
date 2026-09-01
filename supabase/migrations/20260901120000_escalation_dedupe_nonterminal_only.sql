-- Scope escalation_queue's dedupe uniqueness to NON-TERMINAL rows only (GitHub issue #96).
--
-- Design citation: SOLUTION_DESIGN.md section 7.4 line 1134 -- "OPEN -> ACKNOWLEDGED ->
-- IN_PROGRESS -> RESOLVED (plus CANCELLED)"; section 7.5.5's `resolve_escalation` /
-- `cancel_escalation` rows (the only two tools that write an end state);
-- ARCHITECTURE/REQUIREMENTS.md FR-OPS-006 -- "Resolve vs Cancel -- **two terminal states**, two
-- driver consequences, each requiring a reason code" -- and FR-OPS-001 (the triage lifecycle).
-- The terminal set is therefore exactly {RESOLVED, CANCELLED}, and nothing else: the live CHECK
-- constraint (20260823100000_e24_escalation_vocabulary.sql:49-52) permits only
-- OPEN / ACKNOWLEDGED / IN_PROGRESS / RESOLVED / CANCELLED -- there is no DISMISSED, ARCHIVED or
-- CLOSED value in this table at all. Cross-checked against the two places application code already
-- encodes the same split: escalation_service.STEPPER_POSITIONS (RESOLVED and CANCELLED both map to
-- stepper position 3) and `get_exception_queue`'s own
-- `WHERE escalation_status NOT IN ('RESOLVED','CANCELLED')` (escalation_service.py:278).
--
-- Backup: NOT taken by this file. See the apply plan at the foot of this migration.
--
-- APPLIED TO PRODUCTION: 2026-09-01 ~13:40 IST, owner-run via deploy/apply_96_dedupe_migration.py
-- (agent classifier gates direct DDL). Output: SET/BEGIN/CREATE INDEX/COMMENT/DO/COMMIT, then all
-- four read-only verifications PASS (new partial index present with correct predicate; old global
-- UNIQUE gone; no full-table unique dedupe_key index remains; zero live duplicates). Table backup
-- beforehand: C:/Users/ANSHUL/setuhaul-db-backups/pre_esc_dedupe_20260901_122115.dump (11,676 B).
--
-- =============================================================================================
-- The defect
-- =============================================================================================
--
-- `escalate_exception` dedupes on `dedupe_key = '<shipment>:<calendar-day>:<type>'` with
-- `ON CONFLICT (dedupe_key) DO UPDATE`, and that UPDATE never resets `escalation_status`
-- (escalation_service.py:151-156, pre-#96). Because
-- `dedupe_key text NOT NULL UNIQUE` (20260812010000_sprint3_lifecycle_escalation.sql:69) is a
-- *global* uniqueness rule, the conflict fires against the row whatever state it is in -- so once
-- a coordinator resolves or cancels today's case, the driver's next genuinely new problem of the
-- same type on the same day silently attaches to that dead row and returns it. No coordinator ever
-- sees it again: `get_escalation_queue` filters terminal rows out by design.
--
-- Found 2026-09-01 by E6.2's Playwright race suites 3 and 4 (issue #43), which each passed alone
-- and failed in sequence. Those suites work around it by rotating the nine escalation types per
-- run; the product has no such workaround.
--
-- =============================================================================================
-- The fix, and the option that was NOT taken
-- =============================================================================================
--
-- Option (a) -- have the conflict UPDATE reset a terminal row back to OPEN -- was rejected by the
-- owner. It re-opens closed history in place: `resolved_at`, `resolved_by_user_id` and
-- `resolution_note` would either be silently cleared or left describing a resolution that no
-- longer applies to the row's current contents, and the audit trail of "this case was resolved at
-- 14:02 by Priya" would be destroyed by an unrelated later event.
--
-- Option (b), implemented here -- dedupe only against non-terminal rows. Behaviour split:
--
--   * prior row still live (OPEN / ACKNOWLEDGED / IN_PROGRESS)  -> unchanged from today. The
--     partial index covers it, the conflict fires, payload/severity/policy/recommendation are
--     refreshed and the SAME row is returned. Exactly one live case per key is still guaranteed by
--     the database, not by application logic.
--   * prior row terminal (RESOLVED / CANCELLED)                 -> the partial index does not
--     cover it, no conflict is detected, and a NEW OPEN row is inserted. The terminal row is not
--     touched at all -- status, dedupe_key, resolved_at and resolution_note all keep their values.
--
-- The consequence worth stating plainly: `dedupe_key` stops being globally unique on this table.
-- After a resolve-then-re-escalate, two rows legitimately share one key -- one terminal, one live.
-- Any future read that assumes "one row per dedupe_key" must add the status predicate. Verified by
-- grep 2026-09-01 that no such read exists today (the only SELECTs on escalation_queue filter by
-- escalation_id, shipment_id or facility_id, never by dedupe_key).
--
-- =============================================================================================
-- Every ON CONFLICT (dedupe_key) in the codebase has to change with this -- not just the one
-- =============================================================================================
--
-- PostgreSQL infers the arbiter index from the conflict target, and "index_predicate: used to
-- allow inference of partial unique indexes" (postgresql.org/docs/current/sql-insert.html,
-- ON CONFLICT Clause, checked 2026-09-01 against PostgreSQL 18, the version the proof cluster
-- runs). A bare `ON CONFLICT (dedupe_key)` can no longer be inferred once the only unique index on
-- that column is partial: it fails at runtime with 42P10, "there is no unique or exclusion
-- constraint matching the ON CONFLICT specification". There are three writers, and all three are
-- accounted for:
--
--   1. backend/app/services/escalation_service.py  `escalate_exception`      -> predicate added
--   2. backend/app/services/planner_service.py     `_open_capacity_cascade`  -> predicate added
--   3. backend/app/scheduling/expiry.py            PENDING_EXPIRED_UNACTIONED -> predicate added
--
-- (2) and (3) key on a dock event id and an appointment id respectively rather than on a calendar
-- day, so a terminal-row collision is far rarer for them -- but the inference failure would have
-- been immediate and total, so they are not optional.
--
-- 20260823060000_d1_correctness_bedrock.sql:238,252 also uses `ON CONFLICT (dedupe_key)
-- DO NOTHING`. It is deliberately NOT edited: it is an already-applied historical migration, and
-- in a replay it runs strictly before this file, while the full unique index still exists.
--
-- =============================================================================================

BEGIN;

-- 1. The new partial unique index, created BEFORE the old one is dropped so that a failure here
-- leaves the table exactly as it was. It cannot fail on existing data: a partial index over a
-- subset of rows is strictly weaker than the full unique index still in force at this point.
--
-- Not CONCURRENTLY: that cannot run inside a transaction block, and this table holds hundreds of
-- rows against a 5-concurrent-user product -- a plain build is sub-second and the atomicity of the
-- create/drop pair is worth more than the brief lock. See the apply plan for the lock_timeout.
--
-- `escalation_status` is NOT NULL (20260812010000:62), so NOT IN carries no three-valued-logic
-- trap here -- a NULL status could never satisfy the predicate and could never be indexed.
CREATE UNIQUE INDEX IF NOT EXISTS escalation_queue_dedupe_key_active_uidx
  ON public.escalation_queue (dedupe_key)
  WHERE escalation_status NOT IN ('RESOLVED', 'CANCELLED');

COMMENT ON INDEX public.escalation_queue_dedupe_key_active_uidx IS
  'Issue #96. At most one NON-TERMINAL escalation per dedupe_key. Terminal rows (RESOLVED, '
  'CANCELLED -- FR-OPS-006''s two end states) are deliberately outside the predicate so a new '
  'same-day, same-type problem opens a fresh case instead of resurrecting a closed one. Every '
  'INSERT ... ON CONFLICT (dedupe_key) against this table MUST repeat this predicate as an '
  'index_predicate or PostgreSQL cannot infer this index (SQLSTATE 42P10).';

-- 2. Drop the old global uniqueness. The constraint was created inline as
-- `dedupe_key text NOT NULL UNIQUE` (20260812010000_sprint3_lifecycle_escalation.sql:69), which
-- PostgreSQL auto-names `escalation_queue_dedupe_key_key` -- but this is resolved from the
-- catalogs rather than by that literal name, for two reasons: the live database cannot be queried
-- from here to confirm the name, and an inline UNIQUE could equally have been materialised as a
-- bare unique index by some later hand-edit. Both shapes are handled.
--
-- PostgreSQL has no `ALTER TABLE ... DROP CONSTRAINT IF EXISTS <predicate>` and no
-- `ADD CONSTRAINT IF NOT EXISTS` at all (supabase-postgres-best-practices, schema-constraints), so
-- an explicit catalog-driven DO block is the idempotent form. Re-running this migration is a
-- no-op: the loops simply find nothing.
DO $$
DECLARE
  dedupe_attnum smallint;
  target_name   text;
BEGIN
  SELECT a.attnum INTO STRICT dedupe_attnum
  FROM pg_attribute a
  WHERE a.attrelid = 'public.escalation_queue'::regclass
    AND a.attname = 'dedupe_key'
    AND NOT a.attisdropped;

  -- 2a. The constraint case (what 20260812010000's inline UNIQUE actually produced). Matched on
  -- "a UNIQUE constraint whose key columns are exactly {dedupe_key}", never on a name.
  FOR target_name IN
    SELECT c.conname
    FROM pg_constraint c
    WHERE c.conrelid = 'public.escalation_queue'::regclass
      AND c.contype = 'u'
      AND c.conkey = ARRAY[dedupe_attnum]
  LOOP
    RAISE NOTICE 'issue #96: dropping global unique constraint %', target_name;
    EXECUTE format('ALTER TABLE public.escalation_queue DROP CONSTRAINT %I', target_name);
  END LOOP;

  -- 2b. The bare-index case. Only non-partial (indpred IS NULL) single-column unique indexes on
  -- dedupe_key that no constraint owns -- which by construction excludes the index created in
  -- step 1, whose indpred is exactly the terminal-status predicate.
  FOR target_name IN
    SELECT ic.relname
    FROM pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    WHERE i.indrelid = 'public.escalation_queue'::regclass
      AND i.indisunique
      AND i.indpred IS NULL
      AND i.indnkeyatts = 1
      AND i.indkey[0] = dedupe_attnum
      AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
  LOOP
    RAISE NOTICE 'issue #96: dropping global unique index %', target_name;
    EXECUTE format('DROP INDEX public.%I', target_name);
  END LOOP;
END $$;

COMMIT;

-- ---------------------------------------------------------------------------------------------
-- Rollback -- read the caveat, it is not a clean reverse
-- ---------------------------------------------------------------------------------------------
-- BEGIN;
--   ALTER TABLE public.escalation_queue
--     ADD CONSTRAINT escalation_queue_dedupe_key_key UNIQUE (dedupe_key);
--   DROP INDEX IF EXISTS public.escalation_queue_dedupe_key_active_uidx;
-- COMMIT;
--
-- **That ADD CONSTRAINT will FAIL the moment this change has done its job.** As soon as one
-- shipment is escalated, resolved, and escalated again on the same day with the same type, two
-- rows share a dedupe_key and restoring global uniqueness raises
-- `could not create unique index ... Key (dedupe_key)=(...) is duplicated`. The data has to be
-- consolidated first -- and there is no safe automatic consolidation, because the whole point of
-- the second row is that it is a DIFFERENT incident from the first. Find them with:
--
--   SELECT dedupe_key, count(*), array_agg(escalation_id ORDER BY created_at)
--   FROM public.escalation_queue GROUP BY dedupe_key HAVING count(*) > 1;
--
-- and decide per key, with the owner, whether to re-key the newer rows (e.g. append a sequence
-- suffix) or accept losing them. Do not script it blind.
--
-- Revert alongside the DDL, or the rollback is worse than the defect -- all three writers regain a
-- bare `ON CONFLICT (dedupe_key)` and would otherwise raise 42P10 against a table that no longer
-- has any matching index:
--   backend/app/services/escalation_service.py  (escalate_exception's index_predicate)
--   backend/app/services/planner_service.py     (_open_capacity_cascade's index_predicate)
--   backend/app/scheduling/expiry.py            (the PENDING_EXPIRED_UNACTIONED insert)
--
-- Re-check after a rollback: `escalate_exception` on any shipment still returns a row rather than
-- raising 42P10, and the expiry sweeper still completes a pass.
--
-- ---------------------------------------------------------------------------------------------
-- Live apply plan (direct psql, NOT `supabase db push`)
-- ---------------------------------------------------------------------------------------------
-- `supabase db push` is not usable on this project: several migrations are untracked in
-- schema_migrations, so a push re-runs already-applied DDL (recorded in
-- 20260831132101_users_invite_lifecycle.sql's header, 2026-08-31). Apply directly:
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -c "SET lock_timeout='5s';" \
--     -f supabase/migrations/20260901120000_escalation_dedupe_nonterminal_only.sql
--
-- The -c and the -f run in ONE session, in the order given -- so the SET really is in force for
-- the file ("This option can be repeated and combined in any order with the -f option ... psql
-- terminates after processing all the -c and -f options in sequence", psql reference page,
-- checked 2026-09-01). Do NOT add -1/--single-transaction: the file already carries its own
-- BEGIN/COMMIT, and wrapping the SET into that same transaction would make it revert on the
-- rollback path it exists to protect.
--
-- Expected duration: well under a second (an index build over hundreds of rows plus two catalog
-- lookups). The lock_timeout matters more than the duration does: step 2a takes an ACCESS
-- EXCLUSIVE lock on public.escalation_queue, so a long-running reader would otherwise queue every
-- subsequent query behind it. A lock_timeout abort is safe -- the whole file is one transaction
-- and rolls back cleanly; just re-run it.
