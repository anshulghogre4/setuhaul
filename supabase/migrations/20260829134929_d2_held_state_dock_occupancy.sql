-- D2: give the HELD promise-state somewhere to live (GitHub issue #53), plus #64's
-- appointments.expires_at so a planner can buy time on a request without corrupting booked_at.
--
-- Design citation: SOLUTION_DESIGN.md section 0.8 ("D1 in concrete terms" / "D2 in concrete
-- terms") is the authoritative shape for every column below; section 4 (the promise lifecycle);
-- section 7.1 (`request_slot`'s two-phase contract and the missing `confirm_held_slot`);
-- section 7.5.1 (`hold_for_information`); D2, D9, M5, M6.
--
-- Backup: NOT taken by this file. This migration has NOT been applied to any database. Applying
-- it is the owner's call (issue #53 is risk:high on the D1 capacity-correctness path); take a
-- pg_dump of public.dock_occupancy and public.appointments first, as E1.1 and E1.5 both did.
--
-- ============================================================================================
-- The one thing to read before touching this file
-- ============================================================================================
--
-- Step 5 drops and recreates the D1 exclusion constraint. That is the mechanism preventing
-- double-booking, so it deserves the paragraph:
--
--   * It is dropped and recreated **inside one transaction**. `ALTER TABLE ... DROP CONSTRAINT`
--     takes ACCESS EXCLUSIVE on the table (PostgreSQL "ALTER TABLE": "An ACCESS EXCLUSIVE lock is
--     acquired unless explicitly noted"), and DDL in PostgreSQL is transactional, so no other
--     transaction can observe -- let alone insert into -- the window between the drop and the add.
--     There is no moment at which the interval is unprotected.
--   * The recreated constraint is **explicitly named** `dock_occupancy_dock_id_window_excl`, the
--     same name it has today. This is load-bearing, not cosmetic: `allocation.py:40` hardcodes
--     that string, and `allocation_unique_constraint_name()` matches on it to turn an
--     ExclusionViolationError into a user-facing `SLOT_CONFLICT_REFRESH_REQUIRED`. If the name
--     drifted, every genuine capacity race would stop being translated and would surface to a
--     driver as a raw 500 instead of "someone took that one, here are fresh options".
--   * It gains section 0.8's `WHERE (state IN (...))` predicate, which makes it a *partial*
--     exclusion constraint (PostgreSQL "CREATE TABLE": "The predicate allows you to specify an
--     exclusion constraint on a subset of the table; internally this creates a partial index").
--
-- **This predicate is not a weakening, and here is the proof rather than the assertion.** Today a
-- released claim is DELETEd (`allocation._release_dock_occupancy`), so a non-active claim already
-- constrains nothing. After step 3's backfill every existing row carries a state drawn from
-- PENDING_CONFIRMATION / CONFIRMED / IN_PROGRESS -- the only three statuses the E1.1 backfill
-- inserted for -- so the predicate is TRUE for 100% of rows that exist, and the constraint's
-- effect on current data is identical before and after. What the predicate *buys* is the ability
-- for the M8 sweeper to transition a lapsed hold to 'EXPIRED' in place rather than deleting it
-- (D2: "a sweeper transitions stale rows to EXPIRED"), which is how the hold leaves an audit
-- trail instead of vanishing.
--
-- `_release_dock_occupancy` is deliberately left DELETE-ing, unchanged, by this change. The
-- cancel/reject/expire release paths keep exactly the semantics they have today.
--
-- ============================================================================================
-- Two deliberate divergences from section 0.8's literal DDL, both stated rather than smuggled
-- ============================================================================================
--
-- 1. `policy_version` is nullable here; section 0.8 writes it `NOT NULL`. Making it NOT NULL
--    would require backfilling a policy version onto 613 rows that were allocated before the
--    policy registry existed -- i.e. inventing operational data, which AGENTS.md forbids. New
--    HELD rows populate it; historical rows honestly say "unknown". Tighten to NOT NULL later if
--    and when every live row has a real one.
-- 2. `appointments_appointment_status_check` is **not** extended with 'HELD'. Section 4 states
--    the rule this migration follows: "Modelled as a dock_occupancy row in state HELD with
--    expires_at (D2) -- not as a separate hold table... **Held != booked: no appointments row
--    exists yet.**" A hold is a dock_occupancy row and nothing else; `confirm_held_slot` is what
--    creates the appointment (section 7.1: "takes the hold id, revalidates inside the
--    transaction, and produces PENDING_CONFIRMATION"). Adding 'HELD' to that CHECK would create a
--    value no code path can produce, and would invite a future path to write HELD appointment
--    rows that every active-status enumeration in the system silently ignores --
--    `v_slot_availability`, `v_inbound_operational_state`,
--    `ux_current_active_appointment_per_shipment`, `ACTIVE_APPOINTMENT_STATUSES`,
--    `_active_appointment_for_slot`, `_current_active_appointment_for_shipment` and
--    `planner_service` all enumerate PENDING_CONFIRMATION/CONFIRMED/IN_PROGRESS by hand.

BEGIN;

-- --------------------------------------------------------------------------------------------
-- 1. The D2 columns, exactly the shape section 0.8 specifies.
--    All four are plain ADD COLUMN with no volatile default, so none of them rewrites the table
--    (PostgreSQL "ALTER TABLE" Notes: a non-volatile DEFAULT is stored in the table's metadata,
--    "making the ALTER TABLE very fast even on large tables"). `state` is added nullable here on
--    purpose -- it gets a real backfilled value in step 3 before NOT NULL is asserted in step 4,
--    rather than a blanket DEFAULT that would label a CONFIRMED row 'PENDING_CONFIRMATION'.
-- --------------------------------------------------------------------------------------------
ALTER TABLE public.dock_occupancy
  ADD COLUMN IF NOT EXISTS shipment_id    text,
  ADD COLUMN IF NOT EXISTS state          text,
  ADD COLUMN IF NOT EXISTS expires_at     timestamptz,
  ADD COLUMN IF NOT EXISTS policy_version text;

COMMENT ON COLUMN public.dock_occupancy.state IS
  'D2 promise state of this capacity claim. HELD rows are soft, TTL-bounded holds with no '
  'appointments row yet (SOLUTION_DESIGN.md section 4). Only the four states named in the '
  'dock_occupancy_dock_id_window_excl predicate actually consume capacity.';
COMMENT ON COLUMN public.dock_occupancy.expires_at IS
  'D2 hold deadline; NULL for every state except HELD. Reads must filter '
  'state = ''HELD'' AND expires_at > now() -- section 0.8: "Never depend on the sweeper for '
  'correctness -- only for hygiene."';
COMMENT ON COLUMN public.dock_occupancy.shipment_id IS
  'Which shipment holds this interval. NOT NULL because a HELD row has no appointment_id to '
  'derive it from, and M15 scope for confirm_held_slot is derived from this column server-side.';

-- --------------------------------------------------------------------------------------------
-- 2. A hold has no appointment yet, so appointment_id has to become nullable.
--    Section 0.8 writes it `appointment_id text REFERENCES appointments(appointment_id)` -- no
--    NOT NULL -- for exactly this reason. DROP NOT NULL needs no table scan (PostgreSQL
--    "ALTER TABLE"), and the FK itself is untouched: a non-NULL value is still checked.
-- --------------------------------------------------------------------------------------------
ALTER TABLE public.dock_occupancy
  ALTER COLUMN appointment_id DROP NOT NULL;

-- --------------------------------------------------------------------------------------------
-- 3. Backfill the two columns that have a knowable historical answer, from the appointment each
--    existing claim already points at. Nothing is invented: `state` is copied from the
--    appointment's own status, `shipment_id` from the appointment's own shipment. Rows whose
--    appointment has since left the active set cannot be left NULL (step 4 asserts NOT NULL), so
--    they are labelled from whatever status the appointment actually carries -- which is the
--    truthful answer, and which also drops them out of the step 5 predicate, exactly as a
--    DELETE-based release would have.
-- --------------------------------------------------------------------------------------------
UPDATE public.dock_occupancy o
SET shipment_id = a.shipment_id,
    state       = a.appointment_status
FROM public.appointments a
WHERE a.appointment_id = o.appointment_id
  AND (o.shipment_id IS NULL OR o.state IS NULL);

-- --------------------------------------------------------------------------------------------
-- 4. Now that every row has a real value, assert the invariants.
--    Idempotent constraint creation via DO blocks, because PostgreSQL has no
--    `ADD CONSTRAINT IF NOT EXISTS` (supabase-postgres-best-practices, "Add Constraints Safely
--    in Migrations" -- `alter table ... add constraint if not exists` is a syntax error, 42601).
-- --------------------------------------------------------------------------------------------
ALTER TABLE public.dock_occupancy
  ALTER COLUMN shipment_id SET NOT NULL,
  ALTER COLUMN state       SET NOT NULL,
  ALTER COLUMN state       SET DEFAULT 'PENDING_CONFIRMATION';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'dock_occupancy_shipment_id_fkey'
      AND conrelid = 'public.dock_occupancy'::regclass
  ) THEN
    ALTER TABLE public.dock_occupancy
      ADD CONSTRAINT dock_occupancy_shipment_id_fkey
      FOREIGN KEY (shipment_id) REFERENCES public.shipments(shipment_id);
  END IF;
END $$;

-- The nine states of section 0.8's CHECK, verbatim.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'dock_occupancy_state_check'
      AND conrelid = 'public.dock_occupancy'::regclass
  ) THEN
    ALTER TABLE public.dock_occupancy
      ADD CONSTRAINT dock_occupancy_state_check
      CHECK (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS',
                       'COMPLETED','CANCELLED','EXPIRED','NO_SHOW','REJECTED'));
  END IF;
END $$;

-- The two halves of "a hold is a hold": a HELD row must have a deadline and must not yet have an
-- appointment; nothing else may carry a deadline. Without this, an expires_at quietly set on a
-- CONFIRMED row would be swept as if it were a lapsed hold, releasing confirmed capacity.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'dock_occupancy_held_shape_check'
      AND conrelid = 'public.dock_occupancy'::regclass
  ) THEN
    ALTER TABLE public.dock_occupancy
      ADD CONSTRAINT dock_occupancy_held_shape_check
      CHECK (
        (state =  'HELD' AND expires_at IS NOT NULL AND appointment_id IS NULL)
        OR
        (state <> 'HELD' AND expires_at IS NULL)
      );
  END IF;
END $$;

-- --------------------------------------------------------------------------------------------
-- 5. The D1 exclusion constraint, recreated with section 0.8's predicate and its existing name.
--    Read the header block above before changing anything here.
-- --------------------------------------------------------------------------------------------
ALTER TABLE public.dock_occupancy
  DROP CONSTRAINT IF EXISTS dock_occupancy_dock_id_window_excl;

ALTER TABLE public.dock_occupancy
  ADD CONSTRAINT dock_occupancy_dock_id_window_excl
  EXCLUDE USING gist (dock_id WITH =, "window" WITH &&)
  WHERE (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS'));

-- --------------------------------------------------------------------------------------------
-- 6. Indexes.
--    `ix_dock_occupancy_shipment`: Postgres does not index FK columns automatically
--    (supabase-postgres-best-practices, "Index Foreign Key Columns"), and confirm_held_slot's
--    M15 scope check reads a hold by shipment.
--    `ix_dock_occupancy_held_expiry`: partial, because the sweeper's scan filters on exactly this
--    predicate and holds are a vanishing fraction of the table -- the 5-20x smaller index of
--    "Use Partial Indexes for Filtered Queries". Deliberately NOT a covering index: at this
--    system's scale (a handful of live holds at any instant) that would be ceremony.
-- --------------------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_dock_occupancy_shipment
  ON public.dock_occupancy (shipment_id);

CREATE INDEX IF NOT EXISTS ix_dock_occupancy_held_expiry
  ON public.dock_occupancy (expires_at)
  WHERE state = 'HELD';

-- --------------------------------------------------------------------------------------------
-- 7. Issue #64 / section 7.5.1's `hold_for_information`: "Pauses the D9 clock exactly once per
--    request; a second call returns HOLD_ALREADY_USED."
--
--    `expiry.py:77-81` recorded why this could not be built: appointments has no deadline column,
--    and faking one by touching `booked_at` would corrupt the request's own history. This is that
--    column. The D9 deadline stays *derived* (`booked_at + ttl`) for every ordinary request;
--    `expires_at` is an override, set only by an extension.
--
--    Note the shape carries its own once-only guard: `expires_at IS NOT NULL` **is** the
--    HOLD_ALREADY_USED marker. No separate boolean, no counter -- the extension either happened
--    or it didn't, and the column that records the new deadline is the same column that proves
--    it was used.
--
--    The tool itself is NOT implemented by this change (see #64). The sweeper is taught to honour
--    the column now regardless, so that the first writer of it inherits correct expiry behaviour
--    instead of a trap.
-- --------------------------------------------------------------------------------------------
ALTER TABLE public.appointments
  ADD COLUMN IF NOT EXISTS expires_at timestamptz;

COMMENT ON COLUMN public.appointments.expires_at IS
  'D9 deadline override for section 7.5.1 hold_for_information. NULL means the ordinary derived '
  'deadline (booked_at + PENDING_CONFIRMATION_TTL_MINUTES) applies. Non-NULL both carries the '
  'new deadline and marks the one permitted extension as spent (HOLD_ALREADY_USED).';

-- --------------------------------------------------------------------------------------------
-- 8. M14's audit vocabulary has to admit the three transitions this feature introduces.
--
--    Found the hard way, and worth recording as the reason this step exists: `audit_logs` carries
--    `audit_logs_action_type_check`, a CHECK admitting thirteen values, none of them hold-related.
--    Every `create_hold` would therefore have failed at COMMIT with a CheckViolationError -- a 500
--    on the very first hold a driver took. No unit test could have caught it (they mock the
--    session, so no constraint is ever evaluated); it surfaced only on running the integration
--    suite against a real PostgreSQL built from this repo's own migration chain.
--
--    Extending the existing constraint rather than dropping it, and by the same drop-and-recreate
--    idiom `escalation_queue`'s vocabulary already uses twice (E1.2's D12 reasons,
--    20260823080000's PENDING_EXPIRED_UNACTIONED) -- one vocabulary mechanism in this schema, not
--    two. The thirteen existing values are reproduced verbatim; only three are added.
--
--    `entity_name` is deliberately NOT constrained anywhere (checked: no CHECK on that column), so
--    the new 'dock_occupancy' entity rows need no change here.
-- --------------------------------------------------------------------------------------------
ALTER TABLE public.audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_type_check;
ALTER TABLE public.audit_logs ADD CONSTRAINT audit_logs_action_type_check
  CHECK (action_type = ANY (ARRAY[
    'LOGIN','LOGOUT','VIEW','CREATE','UPDATE','DELETE',
    'BOOK_APPOINTMENT','CANCEL_APPOINTMENT','UPDATE_ETA','SEND_MESSAGE',
    'RESCHEDULE_APPOINTMENT','REJECT_APPOINTMENT','EXPIRE_APPOINTMENT',
    -- D2's hold lifecycle (issue #53): taken, committed, lapsed.
    'CREATE_HOLD','CONFIRM_HELD_SLOT','EXPIRE_HOLD'
  ]));

COMMIT;
