-- E3.5 (issue #29, M3): shared/cross-cutting tools -- notification storage and search.
--
-- Design citation: SOLUTION_DESIGN.md section 7.5.8. get_notifications/mark_notifications_read
-- are described as "Module 10 (Notification/Outbox), a read extension of the outbox it already
-- tracks delivery through" -- confirmed live 2026-08-25 that no such table exists anywhere
-- (`information_schema.tables` has nothing matching notif/outbox). Module 10 itself is unbuilt,
-- the same class of gap E3.2 found for the Sequencer (section 7.5.3) -- except here the read/
-- preference tools are still fully buildable without a producer: a user can set preferences and
-- read a correctly-empty feed today. No producer is wired by this migration or by E3.5's tools;
-- that is separate, cross-cutting scope (every write path that should notify someone), tracked
-- honestly as a known gap rather than silently assumed away.
--
-- `category` values are `Source: assumption, untested` -- section 7.5.8 specifies a "grouped-
-- category model, not per-event granularity" but never names the groups. ESCALATION/APPOINTMENT/
-- SYSTEM mirror the three kinds of event this system's own domain actually produces (escalation
-- lifecycle, appointment lifecycle, everything else) -- the same honesty class the design doc
-- itself already uses for section 7.5.5's resolve/cancel reason_code enum.
--
-- pg_trgm backs `search_records`'s fuzzy matching (section 7.5.8's own decision: Postgres FTS +
-- pg_trgm, not a dedicated search engine). Not installed before this migration -- confirmed live.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS public.notifications (
  notification_id text PRIMARY KEY,
  user_id text NOT NULL REFERENCES public.users(user_id),
  category text NOT NULL CHECK (category IN ('ESCALATION', 'APPOINTMENT', 'SYSTEM')),
  title text NOT NULL,
  body text NOT NULL,
  related_entity_type text,
  related_entity_id text,
  is_read integer NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
  created_at timestamptz NOT NULL DEFAULT now(),
  read_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_feed
  ON public.notifications (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.notification_preferences (
  user_id text NOT NULL REFERENCES public.users(user_id),
  category text NOT NULL CHECK (category IN ('ESCALATION', 'APPOINTMENT', 'SYSTEM')),
  channel_web_push integer NOT NULL DEFAULT 1 CHECK (channel_web_push IN (0, 1)),
  channel_email integer NOT NULL DEFAULT 1 CHECK (channel_email IN (0, 1)),
  digest_mode integer NOT NULL DEFAULT 0 CHECK (digest_mode IN (0, 1)),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, category)
);

-- search_records's two most-searched free-text columns. Trigram indexes are a performance
-- decision, not a correctness one, at this data volume (~1,000 shipments) -- added because the
-- design already decided on pg_trgm, so paying for the index now is nearly free.
CREATE INDEX IF NOT EXISTS idx_shipments_order_reference_trgm
  ON public.shipments USING gin (order_reference gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_drivers_driver_name_trgm
  ON public.drivers USING gin (driver_name gin_trgm_ops);

COMMIT;
