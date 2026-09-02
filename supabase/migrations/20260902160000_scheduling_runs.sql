-- scheduling_runs -- the D5 reviewable artifact the facility sequencer produces (GitHub issue #49),
-- plus the one notification event a re-sequenced promise needs (issues #49/#54).
--
-- Design citation: SOLUTION_DESIGN.md D5 ("Sequencer proposes; a planner applies -- no automatic
-- re-promising. Sequencer output is a reviewable artifact (`scheduling_runs`), never a silent
-- write"); D3 ("Per-driver ranking + facility sequencer ... Requires fixed-work and plan-stability
-- modelling"); section 5 Stage 4 ("Persist every run in `scheduling_runs` (input snapshot,
-- proposal, objective values, explanation) so a proposal can be reviewed and replayed");
-- section 5.1 in full -- the run scope ("one facility, rolling horizon of 4 hours or to
-- `close_time`, whichever is sooner"), the objective (including `P_churn`), the debounce rule
-- ("allow **at most one active run per facility** (serialised)"), the diff
-- ("unchanged / moved / newly placed / unplaceable"), the two apply rules ("all-or-nothing per
-- run", "snapshot-guarded, exactly like option sets"), and the cascade path ("capacity incident ->
-- one run scoped to the affected docks and window -> one proposal -> planner applies ->
-- notifications batch out"); section 7.5.3's three-tool table; section 7.5.5's
-- `request_sequencer_proposal` row ("the `escalation_id` attached to the resulting
-- `scheduling_run_id`, rather than a parallel tool -- the incident and the run stay linkable");
-- D7 / section 5 Stage 2 (the weights the objective shares with the per-driver ranker).
-- Requirements: ARCHITECTURE/REQUIREMENTS.md FR-SYS-016 (facility sequencer with
-- proposal-and-approve), FR-SYS-019 (capacity-incident batching), FR-OPS-004 (triage a capacity
-- incident -- request a proposal, planner applies), FR-PLN-009 (review and apply, all-or-nothing),
-- FR-SYS-042 (`scheduling_runs` named as one of the three observability layers -- "every promise
-- reconstructable"), NFR-007 (determinism -- same snapshot + policy version -> byte-identical
-- sequencer proposal).
--
-- Backup: NOT taken by this file. See the apply plan at the foot of this migration.
--
-- NOT YET APPLIED TO ANY DATABASE as of this file's authoring (2026-09-02). Apply plan at the foot.
-- The proof suite (`docs/scripts/run_proof_suite.py`) replays this file into a throwaway cluster,
-- so "it runs" is proven there before anyone points psql at production.
--
-- =============================================================================================
-- 1. Why a table at all, and why the run is stored rather than recomputed
-- =============================================================================================
--
-- D5 is the whole reason: "the sequencer proposes and a planner applies". A proposal that only
-- existed in a response body would make the planner's Apply a *second* computation -- and the
-- second one would run against different data, so the planner would apply something they never
-- reviewed. Storing the run makes Apply a replay of a decision, not a re-decision.
--
-- Section 5 Stage 4 names the four things a stored run must carry -- input snapshot, proposal,
-- objective values, explanation -- and section 8's "how the business trusts the allocation" is what
-- makes it non-negotiable: section 7.5.3's `get_scheduling_run` is specified as "replayable a month
-- later". All four are columns below rather than one blob, so a query can ask "which runs moved a
-- promise" without parsing prose.
--
-- =============================================================================================
-- 2. `scheduling_runs_active_per_facility_uidx` -- section 5.1's debounce, expressed as a constraint
-- =============================================================================================
--
-- Section 5.1: "20-35 messages inside 30 minutes would otherwise fire ~30 runs, each proposing to
-- move the previous one's promises. Coalesce triggers in a 30-60 s window, and allow **at most one
-- active run per facility** (serialised). Without this, plan stability is theoretical."
--
-- The second half is a database invariant here, not application bookkeeping -- section 7.5.3 gives
-- it a return value (`RUN_ALREADY_ACTIVE`), and a value the application computes by SELECT-then-
-- INSERT is a race, not a rule. A **partial** unique index over `status = 'PROPOSED'` is the shape
-- (supabase-postgres-best-practices/query-partial-indexes; the same pattern
-- 20260901120000_escalation_dedupe_nonterminal_only.sql used for `escalation_queue`): applied and
-- superseded runs are history and must not block the next proposal, so they sit outside the
-- predicate and the index stays the size of the live set rather than the size of the log.
--
-- THE RULE THIS IMPOSES ON EVERY WRITER, exactly as #96's did: PostgreSQL infers the arbiter index
-- from the conflict target, and "index_predicate: used to allow inference of partial unique
-- indexes" (postgresql.org/docs/current/sql-insert.html, ON CONFLICT Clause -- re-checked
-- 2026-09-02 against PostgreSQL 18, the version the proof cluster runs). A bare
-- `ON CONFLICT (facility_id)` cannot be inferred against a partial index and fails at runtime with
-- 42P10. `backend/app/repositories/scheduling_runs.py::insert_proposed_run` repeats the predicate.
--
-- The half of the debounce this does NOT implement, stated rather than implied: the 30-60 s
-- **trigger-coalescing window**. Section 5.1's recompute triggers (ETA update, gate check-in,
-- unload complete, cancellation, dock status event, new exception, pending expiry) have no
-- automatic producer anywhere in this system -- every run today is asked for by a human, through
-- `propose_facility_schedule` or section 7.5.5's `request_sequencer_proposal`. Coalescing zero
-- automatic triggers would be machinery with nothing to coalesce. When a trigger producer lands,
-- this index is what keeps it honest and the window is what keeps it cheap.
--
-- =============================================================================================
-- 3. The status lifecycle, and why it has exactly three values
-- =============================================================================================
--
--   PROPOSED    -- computed, stored, awaiting a planner (D5's "reviewable artifact").
--   APPLIED     -- `apply_schedule_proposal` committed it, all-or-nothing (section 5.1).
--   SUPERSEDED  -- the proposal is dead and must not block the facility. Three producers, all real:
--                  (a) its horizon has passed, so every placement in it is in the past -- flipped
--                      lazily by the next `propose_facility_schedule`;
--                  (b) an apply found `SNAPSHOT_DRIFT` (section 7.5.3: "-> re-run required");
--                  (c) an apply found `PARTIALLY_INFEASIBLE` (section 7.5.3: "refuses entirely").
--
-- (a) is the same constraint-versus-clock asymmetry `backend/app/scheduling/occupancy.py` documents
-- at length for lapsed D2 holds: a partial index predicate cannot contain a time term, because a
-- constraint is evaluated against rows and not against a clock. So an expired proposal goes on
-- refusing the next run until *something writes to it* -- and the fix is the same one #97 used,
-- flip the dead rows inside the transaction that needs them gone, rather than teaching the index
-- to know what time it is.
--
-- There is deliberately NO `DISCARDED` value, even though
-- `UI-UX/03-planner-dock-board/flows-and-states.md` Flow 9 step 5 says a planner "applies (or
-- rejects)" a proposal. Section 7.5.3's catalog defines three tools and none of them is a reject,
-- so a `DISCARDED` value would have no producer -- which is precisely the defect issue #69 was
-- filed about, in schema form. Recorded as a named gap on #49 instead. (a) above is what stops an
-- unapplied proposal blocking a facility indefinitely, so the practical need is met.
--
-- =============================================================================================
-- 4. `escalation_id` -- issue #54's linkage, and why it is a column rather than a payload key
-- =============================================================================================
--
-- Section 7.5.5's `request_sequencer_proposal` row: the tool delegates to
-- `propose_facility_schedule` "with `trigger_reason = 'CAPACITY_INCIDENT'` and the `escalation_id`
-- attached to the resulting `scheduling_run_id`, rather than a parallel tool -- the incident and
-- the run stay linkable". A real column with a real foreign key is what makes "linkable" a
-- guarantee: `escalation_queue.payload_json` is `text` on this schema, so a link stored there
-- could name an escalation that never existed and nothing would notice.
--
-- `scheduling_runs_incident_link` below then makes the two fields agree in one direction: an
-- `escalation_id` may only appear on a `CAPACITY_INCIDENT` run. A planner-requested run that
-- carried an incident id would be claiming a provenance it does not have.

BEGIN;

-- ---------------------------------------------------------------------------------------------
-- 5. The table
-- ---------------------------------------------------------------------------------------------
--
-- `CREATE TABLE IF NOT EXISTS` (not a DO block) matches 20260902093000 and 20260825211500 and is
-- genuinely idempotent for a whole-table create. Types follow
-- supabase-postgres-best-practices/schema-data-types: `text` not varchar(n), `timestamptz` not
-- `timestamp`. The three payload columns are `jsonb` for the same reason the outbox's
-- `payload_json` is -- a new table with no SQLite heritage to preserve, and jsonb validates what it
-- is handed where `text` does not. Unlike the outbox's, these ARE read back
-- (`get_scheduling_run` and the apply both re-read the proposal), which is a second reason not to
-- store them as text: `->>` on a text column is not a thing, so a future "which runs moved
-- SHP1013" query would have to parse in Python.
CREATE TABLE IF NOT EXISTS public.scheduling_runs (
  scheduling_run_id   text PRIMARY KEY,

  -- Section 5.1 "Run scope": one facility. Never a set, never global -- the objective's
  -- no-overlap and eligibility terms are only meaningful within one facility's dock set.
  facility_id         text NOT NULL REFERENCES public.facilities(facility_id),

  -- Only values with a real producer, per section 3's reasoning above:
  --   CAPACITY_INCIDENT  section 7.5.5's `request_sequencer_proposal` (issue #54) -- the ops
  --                      delegate, and the only reason that may carry an `escalation_id`.
  --   PLANNER_REQUESTED  03-planner-dock-board/flows-and-states.md Flow 9's "self-triggered"
  --                      origin -- "a small 'Request re-sequence' action on the Board tab that
  --                      calls `propose_facility_schedule` with
  --                      `trigger_reason='PLANNER_REQUESTED'`", named verbatim there.
  -- Section 5.1's seven event-driven recompute triggers (ETA update, gate check-in, unload
  -- complete, cancellation, dock status event, new exception, pending expiry) are deliberately
  -- absent: none of them has a producer, and an enumerated value nothing can write is a promise
  -- the schema cannot keep.
  trigger_reason      text NOT NULL CHECK (trigger_reason IN (
                        'CAPACITY_INCIDENT',
                        'PLANNER_REQUESTED'
                      )),

  -- The verified identity that asked for the run -- never a client-supplied field (M15). Section 8
  -- / FR-SYS-014: "who, what, when, which policy version".
  requested_by_user_id text NOT NULL REFERENCES public.users(user_id),

  -- Issue #54's link. NULL for a planner-requested run; see `scheduling_runs_incident_link`.
  escalation_id       text REFERENCES public.escalation_queue(escalation_id),

  status              text NOT NULL DEFAULT 'PROPOSED'
                      CHECK (status IN ('PROPOSED', 'APPLIED', 'SUPERSEDED')),

  -- Section 5.1's run scope, STORED rather than recomputed at apply time. This is load-bearing for
  -- the snapshot guard: the digest is computed over the job set inside this window, so if the
  -- window moved with the wall clock between propose and apply, every apply would report
  -- `SNAPSHOT_DRIFT` merely because time passed. `backend/app/scheduling/snapshot.py`'s module
  -- docstring states the same rule for the per-appointment digest ("Deliberately absent: TTL
  -- remaining, ETA, and anything else that moves on a wall clock ... The guard means *the capacity
  -- you looked at changed*, not *time passed*"). Freezing the horizon is how that rule survives
  -- being applied to a whole facility.
  horizon_start       timestamptz NOT NULL,
  horizon_end         timestamptz NOT NULL,
  -- Which of section 5.1's two bounds actually closed the window -- 'ROLLING_WINDOW' (the 4 hours)
  -- or 'FACILITY_CLOSE' (the `close_time` clamp). Same two values, from the same helper,
  -- `services/planner_service.py::_board_horizon_end`, that the planner's own dock board reports;
  -- the board and the proposal must not disagree about where the axis ends.
  horizon_end_reason  text NOT NULL,

  -- D7 / section 5 Stage 2: "Version the weights ... and stamp the version onto every decision."
  -- Section 5.1 repeats it for this table specifically: "`P_churn` lives in `policy_versions`
  -- alongside the Stage-2 weights (D7) and is stamped on every run."
  policy_version      text NOT NULL,

  -- Section 5.1's staleness guard: "the proposal carries a `snapshot_hash`; on apply, revalidate
  -- and re-run on drift. Same staleness discipline as section 7.1 -- one mechanism, used
  -- consistently." Produced by `scheduling/snapshot.py::batch_snapshot_hash` over the per-row
  -- digests `bulk_confirm` already uses, so it is literally the same mechanism and not a
  -- look-alike.
  snapshot_hash       text NOT NULL,

  -- Section 5 Stage 4's four artifacts.
  input_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,   -- the section 5.1 job set + parameters
  proposal_json       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- the diff: unchanged/moved/new/unplaceable
  objective_json      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- every term, incl. churn_count + fairness
  explanation         text NOT NULL DEFAULT '',             -- section 5.1's own "Effect: ..." line

  created_at          timestamptz NOT NULL DEFAULT now(),

  applied_at          timestamptz,
  applied_by_user_id  text REFERENCES public.users(user_id),
  -- How many `notification_outbox` rows the apply enqueued. Section 5.1's cascade path ends
  -- "notifications batch out", and section 7.5.3 has `apply_schedule_proposal` return a
  -- "notification batch id" -- that id IS this run's id (one apply, one batch), so it is not
  -- stored a second time under another name. The count is stored, because "the apply said it
  -- notified 4 drivers" is a fact worth being able to check against the outbox a month later.
  notifications_enqueued integer CHECK (notifications_enqueued IS NULL OR notifications_enqueued >= 0),

  superseded_at       timestamptz,
  -- Which of section 3's three producers retired the run: 'HORIZON_PASSED', 'SNAPSHOT_DRIFT' or
  -- 'PARTIALLY_INFEASIBLE'. Not a CHECK: these are application vocabulary rather than a lifecycle
  -- the database has to defend, and a fourth reason arriving with a fourth producer should not
  -- need a migration to be recordable. (Contrast `status` above, which every read branches on.)
  superseded_reason   text
);

-- ---------------------------------------------------------------------------------------------
-- 6. Indexes
-- ---------------------------------------------------------------------------------------------

-- Section 5.1's serialisation rule itself. See header section 2 for why it is partial and for the
-- 42P10 rule it imposes on every writer.
CREATE UNIQUE INDEX IF NOT EXISTS scheduling_runs_active_per_facility_uidx
  ON public.scheduling_runs (facility_id)
  WHERE status = 'PROPOSED';

COMMENT ON INDEX public.scheduling_runs_active_per_facility_uidx IS
  'Issue #49. SOLUTION_DESIGN.md section 5.1: "allow at most one active run per facility '
  '(serialised)" -- section 7.5.3 surfaces the refusal as RUN_ALREADY_ACTIVE. Partial, so applied '
  'and superseded history never blocks the next proposal. Every INSERT ... ON CONFLICT '
  '(facility_id) against this table MUST repeat this predicate as an index_predicate or PostgreSQL '
  'cannot infer this index (SQLSTATE 42P10).';

-- "The last few runs at this facility", which is every human question about this table and the
-- read `03-planner-dock-board`'s Board tab makes to decide whether its [ Review proposal (N) ]
-- button is live. DESC on created_at because every such read is newest-first
-- (supabase-postgres-best-practices/query-composite-indexes: order the index the way the query
-- sorts).
CREATE INDEX IF NOT EXISTS ix_scheduling_runs_facility_created
  ON public.scheduling_runs (facility_id, created_at DESC);

-- The issue #54 join, in the direction it is actually travelled: "which run did this incident
-- produce". Partial because the column is NULL on every planner-requested run, so the index stays
-- the size of the incident-triggered subset (supabase-postgres-best-practices/
-- schema-foreign-key-indexes recommends indexing FK columns; query-partial-indexes is why this one
-- carries a predicate).
CREATE INDEX IF NOT EXISTS ix_scheduling_runs_escalation
  ON public.scheduling_runs (escalation_id)
  WHERE escalation_id IS NOT NULL;

-- Deliberately NOT indexed, stated so it reads as a decision rather than an oversight:
-- `requested_by_user_id` and `applied_by_user_id`. Same reasoning the outbox migration recorded for
-- its three FKs -- neither is ON DELETE CASCADE (a deleted user must fail the delete and be looked
-- at, not silently take the decision history with it), and no read in `backend/app/` starts from
-- either column. Two unused indexes on every insert, on a table this product will fill at single
-- figures of rows per day, is cost with no buyer.

COMMENT ON TABLE public.scheduling_runs IS
  'SOLUTION_DESIGN.md D5 / section 5 Stage 4 / section 7.5.3 (issue #49). The facility sequencer''s '
  'reviewable artifact: one row per proposal, written by propose_facility_schedule, read by '
  'get_scheduling_run, consumed by apply_schedule_proposal. The sequencer NEVER writes capacity '
  'directly -- every placement in proposal_json reaches dock_occupancy through the same '
  'allocation.py primitives confirm/counter_offer use, inside one transaction, all-or-nothing.';

COMMENT ON COLUMN public.scheduling_runs.snapshot_hash IS
  'scheduling/snapshot.py::batch_snapshot_hash over the per-appointment digests of the run''s own '
  'job set, keyed by appointment_id (and by shipment:<id> for a job with no active appointment, so '
  'that a job gaining or losing one is itself drift). Recomputed over the STORED horizon at apply '
  'time -- never over a fresh one, or the passage of time would read as drift.';

COMMENT ON COLUMN public.scheduling_runs.objective_json IS
  'Section 5.1''s objective, term by term: lateness_cost, waiting_cost, fallback_dock_cost, '
  'churn_cost (P_churn x promises moved -- D7), fairness_cost (w_fairness x carrier concentration, '
  'the term issue #69 built), total_cost, and the churn_count / promises_moved the D7 trade-off is '
  'monitored by.';

-- ---------------------------------------------------------------------------------------------
-- 7. Table constraints PostgreSQL has no IF NOT EXISTS for
-- ---------------------------------------------------------------------------------------------
--
-- Every one below is a two-or-more-column invariant, so none can ride on a column definition.
-- PostgreSQL has no `ADD CONSTRAINT IF NOT EXISTS` at all
-- (supabase-postgres-best-practices/schema-constraints), so the catalog-checked DO block is the
-- idempotent form -- the same shape 20260901120000 and 20260902093000 both used.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.scheduling_runs'::regclass
      AND conname = 'scheduling_runs_horizon_order'
  ) THEN
    -- A zero-width or inverted horizon is not a run scope, it is a bug that would produce an
    -- empty job set and a confident "Unchanged 0 · Moved 0" proposal.
    ALTER TABLE public.scheduling_runs
      ADD CONSTRAINT scheduling_runs_horizon_order
      CHECK (horizon_end > horizon_start);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.scheduling_runs'::regclass
      AND conname = 'scheduling_runs_applied_shape'
  ) THEN
    -- APPLIED, applied_at and applied_by_user_id are one fact recorded three times; this refuses
    -- to let them disagree. Written as two equalities between booleans so it covers both
    -- directions -- an APPLIED row with no stamp, and a stamp on a row that never applied.
    ALTER TABLE public.scheduling_runs
      ADD CONSTRAINT scheduling_runs_applied_shape
      CHECK (
        (status = 'APPLIED') = (applied_at IS NOT NULL)
        AND (applied_at IS NOT NULL) = (applied_by_user_id IS NOT NULL)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.scheduling_runs'::regclass
      AND conname = 'scheduling_runs_superseded_shape'
  ) THEN
    ALTER TABLE public.scheduling_runs
      ADD CONSTRAINT scheduling_runs_superseded_shape
      CHECK ((status = 'SUPERSEDED') = (superseded_at IS NOT NULL));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.scheduling_runs'::regclass
      AND conname = 'scheduling_runs_incident_link'
  ) THEN
    -- Section 7.5.5: the escalation link exists so "the incident and the run stay linkable". A
    -- planner-requested run carrying an incident id would be claiming a provenance it does not
    -- have; the reverse direction is deliberately NOT constrained, because a CAPACITY_INCIDENT run
    -- whose escalation was later deleted must not become unwritable.
    ALTER TABLE public.scheduling_runs
      ADD CONSTRAINT scheduling_runs_incident_link
      CHECK (escalation_id IS NULL OR trigger_reason = 'CAPACITY_INCIDENT');
  END IF;
END $$;

-- ---------------------------------------------------------------------------------------------
-- 8. RLS lockdown
-- ---------------------------------------------------------------------------------------------
--
-- Three statements, verbatim the baseline's own pattern (20260805201923:614-641) and the one
-- 20260902093000 had to retro-fit onto E3.5's two tables. Supabase's "Securing your API" guide,
-- re-fetched 2026-09-02 for this migration rather than carried over from #94's reading: *"On
-- existing projects, tables created in `public` receive SELECT, INSERT, UPDATE, and DELETE
-- privileges for `anon`, `authenticated`, and `service_role` by default"* and *"A table isn't
-- reachable through the Data API unless you have granted a role privileges on it."* So a new
-- `public` table without these three lines is readable through PostgREST by any signed-in user --
-- and this one carries every facility's forward schedule, its policy weights and its objective
-- values, which is a strictly larger disclosure than the notification feed #94 found exposed.
--
-- No POLICY is created, deliberately, for the reason 20260902093000 states: this backend connects
-- as the owner/service role over a direct Postgres connection and never through PostgREST as
-- anon/authenticated (M15 -- identity and scope are derived server-side in
-- `app/core/execution_context.py`), so a policy would be dead code. RLS-enabled-with-no-policy plus
-- the revoke is deny-by-default, matching every baseline table.
ALTER TABLE public.scheduling_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.scheduling_runs FROM anon, authenticated;
GRANT ALL ON TABLE public.scheduling_runs TO service_role;

-- ---------------------------------------------------------------------------------------------
-- 9. One new notification event: APPOINTMENT_RESEQUENCED
-- ---------------------------------------------------------------------------------------------
--
-- Section 5.1's cascade path ends "planner applies -> notifications batch out", and its own diff
-- example distinguishes a moved promise that was already communicated ("SHP1009 D4 19:15 -> 19:45
-- *(communicated -- driver will be notified)*") from one that was not. The outbox catalog
-- 20260902093000 shipped has no event for that: its eleven values cover confirm, reject, cancel,
-- expiry, hold lapse, withdrawal, counter-offer and the four escalation transitions, and every one
-- of them would be a lie here --
--
--   * APPOINTMENT_CONFIRMED's dedupe key is `<event>:<appointment_id>:<recipient>`, which the
--     original confirmation already consumed, so the move would be silently suppressed by
--     `notification_outbox_dedupe_key_uidx`. Exactly the failure mode #96 recorded, in a new place.
--   * COUNTER_OFFER's body says "Nothing is held yet", which is false after an apply: the interval
--     has been re-claimed in `dock_occupancy` inside the applying transaction.
--   * OPTION_WITHDRAWN claims a dock went out of service, which is one cause of a re-sequence and
--     not the fact being reported.
--
-- So the honest move is a twelfth value rather than a borrowed eleventh.
-- `backend/app/services/notification_outbox.py` gains the matching `EVENT_CATALOG` entry in the
-- same change; `tests/unit/test_notification_outbox.py` parses BOTH migrations and asserts the
-- effective CHECK equals the Python catalog exactly, so the two cannot drift.
--
-- DROP then ADD under the same constraint name, rather than a new name: the name
-- `notification_outbox_event_type_check` is what PostgreSQL auto-generated for the inline column
-- CHECK, and `tests/proof/test_part3b_notification_outbox.py` asserts the table's six CHECK names
-- exactly. Re-adding under the same name keeps that assertion true and keeps a re-run idempotent.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notification_outbox'::regclass
      AND conname = 'notification_outbox_event_type_check'
  ) THEN
    ALTER TABLE public.notification_outbox
      DROP CONSTRAINT notification_outbox_event_type_check;
  END IF;

  ALTER TABLE public.notification_outbox
    ADD CONSTRAINT notification_outbox_event_type_check
    CHECK (event_type IN (
      'APPOINTMENT_CONFIRMED',
      'APPOINTMENT_REJECTED',
      'APPOINTMENT_CANCELLED',
      'APPOINTMENT_RESEQUENCED',
      'PENDING_EXPIRED',
      'HOLD_LAPSED',
      'OPTION_WITHDRAWN',
      'COUNTER_OFFER',
      'THREAD_TAKEN_OVER',
      'ESCALATION_OPENED',
      'ESCALATION_RESOLVED',
      'ESCALATION_CANCELLED'
    ));
END $$;

COMMIT;

-- ---------------------------------------------------------------------------------------------
-- Rollback
-- ---------------------------------------------------------------------------------------------
-- Clean, like 20260902093000's and unlike 20260901120000's -- this migration only adds. Two halves,
-- and they are separable:
--
-- (a) The table (safe -- it holds only rows this migration's own code created; no existing table's
--     data depends on it, and nothing else references it):
--
--   BEGIN;
--     DROP TABLE IF EXISTS public.scheduling_runs;  -- indexes/constraints/comments go with it
--   COMMIT;
--
--   Revert alongside the application code, or `propose_facility_schedule` /
--   `apply_schedule_proposal` / `get_scheduling_run` raise 42P01 (undefined_table) on their next
--   call. Files to restore together:
--     backend/app/scheduling/sequencer.py                (delete outright -- new file)
--     backend/app/repositories/scheduling_runs.py        (delete outright -- new file)
--     backend/app/api/v1/routers/scheduling.py           (remove the four /scheduling/* routes)
--     backend/app/api/v1/routers/operations.py           (remove the sequencer-proposal route)
--     backend/app/services/ops_copilot.py                (restore the SEQUENCER_UNBUILT abstain)
--   Nothing in the driver, gate, carrier or admin paths touches this table, so nothing else moves.
--
--   Re-check after: one `confirm_request` still returns CONFIRMED, and
--   `GET /api/v1/planner/board` still renders.
--
-- (b) Step 9's event-type CHECK -- roll this back ONLY together with
--     `notification_outbox.APPOINTMENT_RESEQUENCED`, and only after checking no row uses it:
--
--   SELECT count(*) FROM public.notification_outbox WHERE event_type = 'APPOINTMENT_RESEQUENCED';
--   -- must be 0, or the DROP/ADD below fails on existing data (which is the correct outcome:
--   -- delete or re-key those rows deliberately rather than losing the constraint).
--
--   BEGIN;
--     ALTER TABLE public.notification_outbox DROP CONSTRAINT notification_outbox_event_type_check;
--     ALTER TABLE public.notification_outbox ADD CONSTRAINT notification_outbox_event_type_check
--       CHECK (event_type IN ('APPOINTMENT_CONFIRMED','APPOINTMENT_REJECTED',
--                             'APPOINTMENT_CANCELLED','PENDING_EXPIRED','HOLD_LAPSED',
--                             'OPTION_WITHDRAWN','COUNTER_OFFER','THREAD_TAKEN_OVER',
--                             'ESCALATION_OPENED','ESCALATION_RESOLVED','ESCALATION_CANCELLED'));
--   COMMIT;
--
-- ---------------------------------------------------------------------------------------------
-- Live apply plan (direct psql, NOT `supabase db push`)
-- ---------------------------------------------------------------------------------------------
-- `supabase db push` is not usable on this project: several migrations are untracked in
-- schema_migrations, so a push re-runs already-applied DDL (recorded in
-- 20260831132101_users_invite_lifecycle.sql's header, 2026-08-31; the same reason 20260901120000
-- and 20260902093000 were applied by hand). Apply directly:
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -c "SET lock_timeout='5s';" \
--     -f supabase/migrations/20260902160000_scheduling_runs.sql
--
-- The -c and the -f run in ONE session in the order given, so the SET is genuinely in force for the
-- file (psql reference page: "psql terminates after processing all the -c and -f options in
-- sequence"). Do NOT add -1/--single-transaction: the file carries its own BEGIN/COMMIT.
--
-- ORDERING: 20260902093000_notification_outbox.sql MUST be applied first -- step 9 alters the table
-- that file creates. Against a database where the outbox migration has not run, this file fails at
-- step 9 with 42P01 and the whole transaction rolls back cleanly, leaving nothing behind. Check
-- with `SELECT to_regclass('public.notification_outbox');` before running.
--
-- Take a backup first. This migration creates rather than alters, but step 9 touches an existing
-- table:
--
--   pg_dump "$DATABASE_URL" -t public.notification_outbox \
--     -Fc -f "$HOME/setuhaul-db-backups/pre_scheduling_runs_$(date +%Y%m%d_%H%M%S).dump"
--
-- Expected duration: milliseconds. An empty CREATE TABLE takes no meaningful lock. Step 9's
-- DROP/ADD CONSTRAINT takes ACCESS EXCLUSIVE on `notification_outbox` and revalidates every
-- existing row against the new CHECK -- a superset of the old one, so it cannot fail on data, and
-- the table holds tens of rows. The lock_timeout is belt-and-braces; a timeout aborts the whole
-- file cleanly (one transaction), so just re-run it.
--
-- Verification queries -- run all six AFTER the apply, expecting the stated answer:
--
--   -- 1. the table exists with its 20 columns
--   SELECT count(*) FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'scheduling_runs';          -- expect 20
--
--   -- 2. section 5.1's serialisation rule is a PARTIAL unique index (not a global one)
--   SELECT indexdef FROM pg_indexes
--    WHERE schemaname = 'public' AND indexname = 'scheduling_runs_active_per_facility_uidx';
--   -- expect: CREATE UNIQUE INDEX ... (facility_id) WHERE (status = 'PROPOSED'::text)
--
--   -- 3. all seven CHECKs landed -- three auto-named column ones plus step 7's four
--   SELECT conname FROM pg_constraint
--    WHERE conrelid = 'public.scheduling_runs'::regclass AND contype = 'c' ORDER BY 1;
--   -- expect exactly these seven:
--   --   scheduling_runs_applied_shape        scheduling_runs_horizon_order
--   --   scheduling_runs_incident_link        scheduling_runs_notifications_enqueued_check
--   --   scheduling_runs_status_check         scheduling_runs_superseded_shape
--   --   scheduling_runs_trigger_reason_check
--
--   -- 4. RLS is on and anon/authenticated hold nothing
--   SELECT relrowsecurity FROM pg_class
--    WHERE relnamespace = 'public'::regnamespace AND relname = 'scheduling_runs';  -- expect true
--   SELECT grantee, privilege_type FROM information_schema.role_table_grants
--    WHERE table_schema = 'public' AND table_name = 'scheduling_runs'
--      AND grantee IN ('anon','authenticated');                                  -- expect 0 rows
--
--   -- 5. the twelfth notification event is accepted
--   SELECT pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conrelid = 'public.notification_outbox'::regclass
--      AND conname = 'notification_outbox_event_type_check';
--   -- expect the list to contain 'APPOINTMENT_RESEQUENCED'
--
--   -- 6. the table starts empty (nothing backfilled -- see below)
--   SELECT count(*) FROM public.scheduling_runs;                                 -- expect 0
--
-- NO BACKFILL, deliberately and unavoidably. A scheduling run is a decision taken against a
-- snapshot of capacity that no longer exists; there is no historical input to recompute one from,
-- and manufacturing rows from today's schedule would fabricate proposals nobody ever reviewed --
-- which is the precise opposite of what D5 stores this table for. The log starts at the first real
-- proposal after this migration.
