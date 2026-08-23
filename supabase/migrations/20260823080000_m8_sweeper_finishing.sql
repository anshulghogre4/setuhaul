-- M8 finishing touches (issue #20, E1.5): the escalate leg and the sweeper's service account.
-- Backup taken before this migration: pg_dump to local scratchpad, 2026-08-23 (not committed).
--
-- Design citation: SOLUTION_DESIGN.md section 7.4 (PENDING_EXPIRED_UNACTIONED), D12/D15
-- pattern already used for the escalation_queue reuse decision (E1.2).

BEGIN;

-- 1. M8's "escalates" leg: a pending appointment the sweeper expired without any planner
-- action is itself an escalation-worthy event, not just a status change. Same table, same
-- reasoning as E1.2's REQUIRES_TIME_RESOLUTION/REQUIRES_DOCK_REASSIGNMENT reuse.
ALTER TABLE public.escalation_queue DROP CONSTRAINT IF EXISTS escalation_queue_escalation_type_check;
ALTER TABLE public.escalation_queue ADD CONSTRAINT escalation_queue_escalation_type_check
  CHECK (escalation_type = ANY (ARRAY[
    'NO_SLOT','CONTRADICTORY','APPROVAL_REQUIRED','REGULATED','EMERGENCY','WAREHOUSE_REPLY_CONFLICT',
    'REQUIRES_TIME_RESOLUTION','REQUIRES_DOCK_REASSIGNMENT','PENDING_EXPIRED_UNACTIONED'
  ]));

-- 2. Sweeper service account. audit_logs.user_id is NOT NULL REFERENCES users(user_id), and
-- attributing sweeper actions to a real ADMIN user would misrepresent who did what in the
-- audit trail. password_hash is set to an inert, unusable marker (never a valid bcrypt hash,
-- never checked against because this account has no Supabase auth_user_id mapping and is
-- never used for interactive login) rather than left NULL, which the column disallows.
INSERT INTO public.users (
  user_id, role_id, full_name, email, password_hash, is_active, created_at
) VALUES (
  'USR-SYSTEM-SWEEPER',
  'ROL008',
  'System - Expiry Sweeper',
  'system.sweeper@setuhaul.internal',
  'DISABLED_SERVICE_ACCOUNT_NO_LOGIN',
  1,
  CURRENT_TIMESTAMP::text
)
ON CONFLICT (user_id) DO NOTHING;

COMMIT;
