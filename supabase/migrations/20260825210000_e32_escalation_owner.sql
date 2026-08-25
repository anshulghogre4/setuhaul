-- E3.2 (issue #26, M3): the ops-console escalation-ownership column.
--
-- Design citation: SOLUTION_DESIGN.md section 7.5.5 -- get_escalation_queue's `owner?`
-- (mine|unowned|all) filter, acknowledge_escalation ("owner set to caller"), reassign_escalation.
-- The issue's own audit noted this plainly: "No `owner` column exists to write to -- schema work,
-- not just tool work." Confirmed live 2026-08-25: `escalation_queue` has no such column.
--
-- Additive and safe: one nullable column, no backfill needed (every existing row is legitimately
-- unowned -- nothing before this migration ever claimed an escalation). No data migration, no
-- default value, no NOT NULL. Backup taken and verified (2.36 MB) before this ran.

BEGIN;

ALTER TABLE public.escalation_queue
  ADD COLUMN IF NOT EXISTS owner_user_id text REFERENCES public.users(user_id);

CREATE INDEX IF NOT EXISTS idx_escalation_queue_owner_user_id
  ON public.escalation_queue (owner_user_id);

COMMIT;
