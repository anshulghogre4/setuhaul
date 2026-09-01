-- notification_outbox -- the transactional outbox SOLUTION_DESIGN.md section 6.1 designs and
-- nothing ever migrated (GitHub issue #94).
--
-- Design citation: SOLUTION_DESIGN.md section 6.1's additions table -- `notification_outbox`,
-- "Transactional outbox so a booking and its notification cannot diverge; feeds
-- `operational_messages`"; section 3's module 10 ("Notification / Outbox -- warehouse email,
-- driver web push / in-app, delivery status (`operational_messages`) ... The outbox keeps a
-- pluggable channel adapter"); section 7.2's "outbound event -> notification outbox -> channel
-- adapter" path; section 7.5.8's `get_notifications` ("Module 10 (Notification/Outbox), a read
-- extension of the outbox it already tracks delivery through"); TECH-STACK/TECH_STACK.md section 6
-- ("The outbox row is written **in the same transaction** as the business change; delivery is a
-- separate, retryable step. Delivery status lands in `operational_messages`").
-- Requirements: ARCHITECTURE/REQUIREMENTS.md FR-SYS-008 (pending expiry "releases capacity,
-- notifies the driver, and raises an escalation"), FR-SYS-020 ("Outbound event notifications --
-- expiry, withdrawal, dock down"), FR-X-023 (the panel and the thing that generates into it are
-- two separate requirements), FR-OPS-006, NFR-009 / M9 ("duplicate `dedupe_key` -> 1 exception,
-- 1 booking attempt, 1 notification").
--
-- Backup: NOT taken by this file. See the apply plan at the foot of this migration.
--
-- NOT YET APPLIED TO PRODUCTION as of this file's authoring (2026-09-02). Apply plan at the foot.
--
-- =============================================================================================
-- The three-artifact reconciliation this migration settles (issue #94's actual question)
-- =============================================================================================
--
-- Issue #94's point was not "add the missing table". It was that THREE notification artifacts
-- exist and none of them connect, and migrating the outbox into the same disconnected state would
-- have been worse than leaving it out. The three, named:
--
--   1. `notification_outbox`  -- SOLUTION_DESIGN.md section 6.1. Designed, never migrated. This file.
--   2. `notifications` + `notification_preferences`
--                             -- 20260825211500_e35_notifications_and_search.sql. Built, and
--                                `backend/app/services/notification_service.py` reads them through
--                                `GET /api/v1/notifications`, but NOTHING has ever written a row.
--   3. `operational_messages` -- 20260805201923_setuhaul_baseline.sql:282. Built, 5 Layer-A seed
--                                rows, and zero readers or writers anywhere in `backend/app/`
--                                (found during #57; re-verified by grep 2026-09-02).
--
-- The decision, so each artifact has exactly one job and no two of them can disagree:
--
--   * `notification_outbox` is AUTHORITATIVE and is the ONLY notification artifact written inside
--     a business transaction. One row per (event, recipient). If the business write rolls back,
--     its notification rolls back with it -- which is the entire content of section 6.1's "a
--     booking and its notification cannot diverge".
--   * `notifications` is the IN_APP channel's DELIVERY RECORD and the user's READ MODEL. Written
--     only by the outbox drain, never by a business path. It keeps `is_read`/`read_at`, which this
--     table deliberately does not carry: delivering a notification and reading one are different
--     events with different owners, and one table holding both is how they drift.
--   * `operational_messages` is the EXTERNAL-channel (EMAIL) delivery record, exactly as
--     TECH_STACK.md section 6 states ("Delivery status lands in `operational_messages`"). Its
--     adapter is NOT implemented in v1 -- there is no SES client anywhere in `backend/` (grep,
--     2026-09-02) -- so `operational_message_id` below stays NULL and the column exists to name
--     the seam rather than to pretend the leg is built. Its 5 seed rows remain Layer-A demo data.
--
-- =============================================================================================
-- Why `dedupe_key` is GLOBALLY unique here, when #96 just removed exactly that from another table
-- =============================================================================================
--
-- 20260901120000_escalation_dedupe_nonterminal_only.sql narrowed `escalation_queue`'s global
-- unique `dedupe_key` to non-terminal rows, because a globally unique key on a LIFECYCLE table
-- resurrects closed cases. That lesson does not transfer, and the reason is worth stating rather
-- than leaving the two files looking contradictory:
--
--   * `escalation_queue`'s key is a DAY BUCKET (`<shipment>:<calendar-day>:<type>`). Two genuinely
--     different problems on one day legitimately share it, so uniqueness had to be scoped.
--   * this table's key is an EVENT INSTANCE (`<EVENT_TYPE>:<entity id>:<recipient>`, built by
--     `backend/app/services/notification_outbox.py::build_dedupe_key`). Two different events can
--     never collide on it, and the same event occurring twice IS the duplicate that NFR-009 says
--     must produce exactly one notification.
--
-- So the constraint that would have been wrong on a day bucket is precisely the one that makes
-- M9's "1 notification" a database guarantee here instead of application bookkeeping.
--
-- THE RULE THIS IMPOSES ON EVERY PRODUCER, and it is not optional: a dedupe key must identify the
-- EVENT, not the day. A producer that keys on a date bucket will silently suppress a real second
-- notification and the suppression will look like success (`ON CONFLICT DO NOTHING` returns no
-- error). `build_dedupe_key` is the single constructor for exactly this reason.
--
-- =============================================================================================
-- A defect found while writing this, and fixed here: E3.5's tables have no RLS at all
-- =============================================================================================
--
-- Every table in 20260805201923_setuhaul_baseline.sql:614-641 carries the same three lines --
-- enable RLS, revoke from anon/authenticated, grant to service_role. 20260825211500's
-- `notifications` and `notification_preferences` carry NONE of them, and no later migration adds
-- them (grep over supabase/migrations/, 2026-09-02: the only post-baseline RLS mentions are two
-- comments, in 20260823060000 and 20260831132101, neither of which touches these tables).
--
-- That is not cosmetic. Supabase's own "Securing your API" guide, fetched 2026-09-02: *"On
-- existing projects, tables created in `public` receive SELECT, INSERT, UPDATE, and DELETE
-- privileges for `anon`, `authenticated`, and `service_role` by default"* and *"These grants make
-- new objects reachable through the Data API, even when you don't intend to expose them."* With no
-- RLS and no revoke, `public.notifications` is readable through PostgREST by any holder of an
-- `authenticated` token -- i.e. every signed-in user can read every other user's notification
-- feed, defeating `notification_service.get_notifications`' own `user_id = ctx.user_id` scoping,
-- which only ever protected the FastAPI path. Fixed below for all three tables together, since
-- shipping the outbox with the correct lockdown while leaving its own read model exposed would be
-- the same defect with an extra table in it.
--
-- No POLICY is created, deliberately. This backend connects as the owner/service role over a
-- direct Postgres connection and never through PostgREST as `anon`/`authenticated` (M15: identity
-- and scope are derived server-side from a verified token, in `app/core/execution_context.py`),
-- so a policy would be dead code. RLS-enabled-with-no-policy plus the revoke is deny-by-default,
-- matching every baseline table.

BEGIN;

-- ---------------------------------------------------------------------------------------------
-- 1. The table
-- ---------------------------------------------------------------------------------------------
--
-- `CREATE TABLE IF NOT EXISTS` (not a DO block) matches the neighbouring 20260825211500 and
-- 20260823090000, and is genuinely idempotent for a whole-table create. The DO-block form is only
-- required for ALTER ... ADD CONSTRAINT, which PostgreSQL has no IF NOT EXISTS for
-- (supabase-postgres-best-practices, schema-constraints) -- see step 3, which does need it.
--
-- Types follow supabase-postgres-best-practices/schema-data-types: `text` not varchar(n),
-- `timestamptz` not timestamp. `payload_json` is `jsonb` rather than the `text` that
-- `escalation_queue.payload_json` uses -- this is a new table with no SQLite heritage to preserve,
-- jsonb validates what it is given where text does not, and it is WRITE-ONLY here (nothing in the
-- drain reads back into it), so the asyncpg str-vs-dict decoding question never arises.
CREATE TABLE IF NOT EXISTS public.notification_outbox (
  outbox_id              text PRIMARY KEY,

  -- The exactly-once key. See the header: EVENT INSTANCE, never a day bucket.
  dedupe_key             text NOT NULL,

  -- Enumerated in the database, not only in Python, for the same reason
  -- 20260823100000_e24_escalation_vocabulary.sql enumerates `escalation_type`: a typo in a producer
  -- must fail at the write, not become an unroutable row nobody notices. Every value below is a
  -- design-enumerated event, with its citation, and there are no others:
  --   APPOINTMENT_CONFIRMED  section 4 / line 1099 ("Confirm -> CONFIRMED, notify driver");
  --                          01-driver-chat/flows-and-states.md:283 "Planner confirmed"
  --   APPOINTMENT_REJECTED   section 7.5.1 `reject_request` ("REJECTED + released interval + driver
  --                          notification"); flows-and-states.md:284, HIGH priority
  --   APPOINTMENT_CANCELLED  section 4's lifecycle; section 7.5.1 `cancel_*`
  --   PENDING_EXPIRED        D9 / M8 / FR-SYS-008; voice-and-tone.md:115 `PENDING_EXPIRED`;
  --                          flows-and-states.md:282, HIGH priority
  --   HOLD_LAPSED            D2's 90s TTL; voice-and-tone.md:107 `HOLD_LAPSED`;
  --                          flows-and-states.md:281
  --   OPTION_WITHDRAWN       section 7.2 line 887 ("a dock going down mid-conversation");
  --                          FR-SYS-020; voice-and-tone.md:130 `OPTION_WITHDRAWN`;
  --                          flows-and-states.md:286, HIGH priority
  --   COUNTER_OFFER          section 7.5.1 `counter_offer`; flows-and-states.md:285
  --   THREAD_TAKEN_OVER      section 7.5.5 / FR-OPS-002 ("driver told on both transitions");
  --                          flows-and-states.md:287 "Human joined the thread"
  --   ESCALATION_OPENED      section 7.4; NFR-009/M9's "1 notification" for the THR001/THR009
  --                          duplicate replay -- this is the event that assertion counts
  --   ESCALATION_RESOLVED    FR-OPS-006 ("two terminal states, two driver consequences")
  --   ESCALATION_CANCELLED   FR-OPS-006, the other terminal state
  event_type             text NOT NULL CHECK (event_type IN (
                           'APPOINTMENT_CONFIRMED',
                           'APPOINTMENT_REJECTED',
                           'APPOINTMENT_CANCELLED',
                           'PENDING_EXPIRED',
                           'HOLD_LAPSED',
                           'OPTION_WITHDRAWN',
                           'COUNTER_OFFER',
                           'THREAD_TAKEN_OVER',
                           'ESCALATION_OPENED',
                           'ESCALATION_RESOLVED',
                           'ESCALATION_CANCELLED'
                         )),

  -- Byte-identical to 20260825211500's CHECK on `notifications.category` and
  -- `notification_preferences.category`. It has to be: the drain copies this value straight across
  -- into `notifications`, and section 7.5.8's preference model is grouped by exactly these three.
  category               text NOT NULL CHECK (category IN ('ESCALATION', 'APPOINTMENT', 'SYSTEM')),

  -- NULLABLE, and the CHECK below is why. Recipient resolution happens at ENQUEUE time, inside the
  -- business transaction -- section 7.4's own instruction for NOTIFICATION_UNROUTABLE: *"this fails
  -- **before** any send is attempted, so retrying is pointless ... Detect it when the outbox
  -- resolves recipients, not when a send fails."* A shipment whose driver has no `public.users` row
  -- must NOT abort the booking that triggered it, so the row is written with status UNROUTABLE and
  -- a null recipient instead of raising. Visible, countable, never silently dropped.
  recipient_user_id      text REFERENCES public.users(user_id),

  shipment_id            text REFERENCES public.shipments(shipment_id),
  related_entity_type    text,
  related_entity_id      text,

  -- Rendered from the templates in UI-UX/00-foundations/voice-and-tone.md by
  -- `notification_outbox.render_event`, never generated. voice-and-tone.md:8: "Sentences that
  -- declare operational state are templated." Stored rather than re-rendered at drain time so the
  -- notification says what was true when the event happened, not what is true a minute later.
  title                  text NOT NULL,
  body                   text NOT NULL,

  payload_json           jsonb NOT NULL DEFAULT '{}'::jsonb,

  -- PENDING -> DELIVERED is the happy path. UNROUTABLE is terminal-at-enqueue (no recipient).
  -- FAILED is terminal-after-retries. There is deliberately no RETRYING state: `attempts` carries
  -- that, and a state that only ever exists inside one transaction is not a state.
  status                 text NOT NULL DEFAULT 'PENDING'
                         CHECK (status IN ('PENDING', 'DELIVERED', 'UNROUTABLE', 'FAILED')),
  attempts               integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  last_error             text,

  created_at             timestamptz NOT NULL DEFAULT now(),
  delivered_at           timestamptz,

  -- What the drain actually produced, per channel. The IN_APP one is written in v1; the EMAIL one
  -- names TECH_STACK.md section 6's seam and stays NULL until an SES adapter exists.
  notification_id        text REFERENCES public.notifications(notification_id),
  operational_message_id text REFERENCES public.operational_messages(operational_message_id)
);

-- ---------------------------------------------------------------------------------------------
-- 2. Indexes
-- ---------------------------------------------------------------------------------------------

-- The exactly-once guarantee itself. NFR-009 / M9 / section 10.3 are asserted by THIS INDEX, not
-- by any Python: `enqueue_notification` uses `ON CONFLICT (dedupe_key) DO NOTHING`, so a replayed
-- producer writes nothing and the count stays at one even if the application logic is wrong.
CREATE UNIQUE INDEX IF NOT EXISTS notification_outbox_dedupe_key_uidx
  ON public.notification_outbox (dedupe_key);

-- The drain's claim query, and the only hot path this table has. Partial, per
-- supabase-postgres-best-practices/query-partial-indexes: rows spend their whole life after
-- delivery outside this predicate, so the index stays the size of the backlog rather than the size
-- of the history. `created_at` is the sort key because the drain claims oldest-first.
CREATE INDEX IF NOT EXISTS notification_outbox_pending_idx
  ON public.notification_outbox (created_at)
  WHERE status = 'PENDING';

-- Per-shipment lookup: the proof suite's "exactly one notification for this shipment" assertion,
-- and every human debugging question about a specific truck.
CREATE INDEX IF NOT EXISTS ix_notification_outbox_shipment
  ON public.notification_outbox (shipment_id);

-- Deliberately NOT indexed, stated so it reads as a decision rather than an oversight:
-- `recipient_user_id`, `notification_id` and `operational_message_id`.
-- supabase-postgres-best-practices/schema-foreign-key-indexes recommends indexing FK columns, and
-- its two stated reasons are JOIN speed and ON DELETE CASCADE table scans. Neither applies: none
-- of these FKs is CASCADE (a deleted user or notification must FAIL the delete and be looked at,
-- not silently take the outbox history with it), and no read starts from any of these columns --
-- the user-facing feed reads `public.notifications`, never this table. Three unused indexes on
-- every insert, on a table this product will fill at a few rows per hour, is cost with no buyer.

COMMENT ON TABLE public.notification_outbox IS
  'SOLUTION_DESIGN.md section 6.1 transactional outbox (issue #94). Written ONLY inside a business '
  'transaction, by notification_outbox.enqueue_notification; drained ONLY by '
  'notification_outbox.drain_outbox. AUTHORITATIVE: public.notifications is its IN_APP delivery '
  'record and read model, public.operational_messages its (unimplemented) EMAIL one. dedupe_key '
  'must identify an EVENT INSTANCE, never a calendar day -- see this migration''s header.';

COMMENT ON COLUMN public.notification_outbox.dedupe_key IS
  'Globally unique. NFR-009/M9''s "exactly 1 notification" is this constraint. Build it only with '
  'notification_outbox.build_dedupe_key.';

COMMENT ON COLUMN public.notification_outbox.recipient_user_id IS
  'NULL only when status = UNROUTABLE -- section 7.4''s NOTIFICATION_UNROUTABLE, detected when the '
  'outbox resolves recipients rather than when a send fails. An unresolvable recipient must never '
  'abort the business write that produced the event.';

-- ---------------------------------------------------------------------------------------------
-- 3. Table constraints that PostgreSQL has no IF NOT EXISTS for
-- ---------------------------------------------------------------------------------------------
--
-- These are two-column invariants, so they cannot ride on a column definition. PostgreSQL has no
-- `ADD CONSTRAINT IF NOT EXISTS` at all (supabase-postgres-best-practices/schema-constraints), so
-- the catalog-checked DO block is the idempotent form -- the same shape 20260901120000 used.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notification_outbox'::regclass
      AND conname = 'notification_outbox_recipient_required'
  ) THEN
    -- The only legitimate reason to have no recipient. Without this, a bug in recipient resolution
    -- becomes a silent null that the drain would skip forever.
    ALTER TABLE public.notification_outbox
      ADD CONSTRAINT notification_outbox_recipient_required
      CHECK (recipient_user_id IS NOT NULL OR status = 'UNROUTABLE');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.notification_outbox'::regclass
      AND conname = 'notification_outbox_delivered_shape'
  ) THEN
    -- DELIVERED and delivered_at are one fact recorded twice; this refuses to let them disagree.
    -- Equality between two booleans, so it covers both directions in one expression.
    ALTER TABLE public.notification_outbox
      ADD CONSTRAINT notification_outbox_delivered_shape
      CHECK ((status = 'DELIVERED') = (delivered_at IS NOT NULL));
  END IF;
END $$;

-- ---------------------------------------------------------------------------------------------
-- 4. RLS lockdown -- the new table AND E3.5's two, which never had any
-- ---------------------------------------------------------------------------------------------
--
-- See the header for the evidence and the Supabase citation. Three statements per table, verbatim
-- the baseline's own pattern (20260805201923:614-641). All three statements are individually
-- idempotent: ENABLE ROW LEVEL SECURITY on an already-enabled table is a no-op, and REVOKE/GRANT
-- are declarative.
--
-- `notification_preferences` is included even though it holds only three booleans per user: it is
-- keyed by `user_id`, so an exposed read still discloses which users exist and which have opened
-- the settings page, and an exposed WRITE would let any authenticated caller switch off another
-- user's notifications entirely.
ALTER TABLE public.notification_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.notification_outbox FROM anon, authenticated;
GRANT ALL ON TABLE public.notification_outbox TO service_role;

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.notifications FROM anon, authenticated;
GRANT ALL ON TABLE public.notifications TO service_role;

ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.notification_preferences FROM anon, authenticated;
GRANT ALL ON TABLE public.notification_preferences TO service_role;

COMMIT;

-- ---------------------------------------------------------------------------------------------
-- Rollback
-- ---------------------------------------------------------------------------------------------
-- Clean, unlike 20260901120000's -- this migration only adds. Two halves, and they are separable:
--
-- (a) The table (safe, drops only rows this migration's own code created):
--
--   BEGIN;
--     DROP TABLE IF EXISTS public.notification_outbox;   -- indexes/constraints/comments go with it
--   COMMIT;
--
--   Revert alongside the application code, or every producer patched into `allocation.py` /
--   `expiry.py` / `planner_service.py` / `escalation_service.py` raises 42P01 (undefined_table) on
--   its next write -- which, because `enqueue_notification` runs INSIDE the business transaction,
--   would take the booking down with it. Files to restore: the four producer call sites listed in
--   this migration's companion report, plus `backend/app/services/notification_outbox.py`,
--   `backend/app/services/notification_service.py`, and
--   `backend/app/api/v1/routers/internal.py`'s `/jobs/notification-drain` route.
--
--   Re-check after: `POST /internal/jobs/expiry-sweep` still completes a cycle, and one
--   `confirm_request` still returns CONFIRMED.
--
-- (b) The RLS lockdown in step 4 -- DO NOT roll this back with the table. It fixes a live exposure
--     (see the header) and is independent of the outbox. Only if it genuinely breaks something:
--
--   ALTER TABLE public.notifications DISABLE ROW LEVEL SECURITY;
--   GRANT ALL ON TABLE public.notifications TO anon, authenticated;   -- restores the exposure
--
--   Nothing in `backend/` connects as anon/authenticated, so this should have no effect on the
--   application either way; that is exactly why the lockdown is low-risk.
--
-- ---------------------------------------------------------------------------------------------
-- Live apply plan (direct psql, NOT `supabase db push`)
-- ---------------------------------------------------------------------------------------------
-- `supabase db push` is not usable on this project: several migrations are untracked in
-- schema_migrations, so a push re-runs already-applied DDL (recorded in
-- 20260831132101_users_invite_lifecycle.sql's header, 2026-08-31; the same reason
-- 20260901120000 was applied by hand). Apply directly:
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -c "SET lock_timeout='5s';" \
--     -f supabase/migrations/20260902093000_notification_outbox.sql
--
-- The -c and the -f run in ONE session in the order given, so the SET is genuinely in force for
-- the file (psql reference page: "psql terminates after processing all the -c and -f options in
-- sequence"). Do NOT add -1/--single-transaction: the file carries its own BEGIN/COMMIT.
--
-- Take a backup first. This migration creates rather than alters, so the blast radius is small,
-- but step 4 touches two existing tables:
--
--   pg_dump "$DATABASE_URL" -t public.notifications -t public.notification_preferences \
--     -Fc -f "$HOME/setuhaul-db-backups/pre_outbox_$(date +%Y%m%d_%H%M%S).dump"
--
-- Expected duration: milliseconds. An empty CREATE TABLE takes no meaningful lock; step 4's
-- ALTER ... ENABLE ROW LEVEL SECURITY takes ACCESS EXCLUSIVE on two tables that today have zero
-- rows and no readers. The lock_timeout is belt-and-braces. A timeout aborts the whole file
-- cleanly (one transaction) -- just re-run it.
--
-- Verification queries -- run all five AFTER the apply, expecting the stated answer:
--
--   -- 1. the table exists with its 18 columns
--   SELECT count(*) FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'notification_outbox';        -- expect 18
--
--   -- 2. dedupe_key is globally unique (this is NFR-009's guarantee)
--   SELECT indexdef FROM pg_indexes
--    WHERE schemaname = 'public' AND indexname = 'notification_outbox_dedupe_key_uidx';
--   -- expect: CREATE UNIQUE INDEX ... ON public.notification_outbox USING btree (dedupe_key)
--
--   -- 3. all six CHECKs landed -- four auto-named column enumerations plus step 3's two named
--   --    two-column invariants (measured on the proof cluster, 2026-09-02)
--   SELECT conname FROM pg_constraint
--    WHERE conrelid = 'public.notification_outbox'::regclass AND contype = 'c'
--      AND conname LIKE 'notification_outbox_%' ORDER BY 1;
--   -- expect exactly these six:
--   --   notification_outbox_attempts_check      notification_outbox_category_check
--   --   notification_outbox_delivered_shape     notification_outbox_event_type_check
--   --   notification_outbox_recipient_required  notification_outbox_status_check
--
--   -- 4. RLS is on for all three, and anon/authenticated hold nothing
--   SELECT relname, relrowsecurity FROM pg_class
--    WHERE relnamespace = 'public'::regnamespace
--      AND relname IN ('notification_outbox','notifications','notification_preferences');
--   -- expect relrowsecurity = true for all three
--   SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants
--    WHERE table_schema = 'public'
--      AND table_name IN ('notification_outbox','notifications','notification_preferences')
--      AND grantee IN ('anon','authenticated');                                   -- expect 0 rows
--
--   -- 5. the outbox starts empty (nothing backfilled -- see below)
--   SELECT count(*) FROM public.notification_outbox;                              -- expect 0
--
-- NO BACKFILL, deliberately. There is no honest way to reconstruct which notifications *should*
-- have been sent for the appointments already confirmed, rejected and expired in production: the
-- events are gone, only their end states remain, and manufacturing outbox rows from end states
-- would fabricate delivery history the system never had. The feed starts from the first event
-- after this migration and the gap is stated rather than papered over -- the same discipline
-- section 6.2's D12 worklist uses for the four overrunning appointments.
