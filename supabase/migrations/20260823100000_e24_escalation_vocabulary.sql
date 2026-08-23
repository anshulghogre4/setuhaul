-- E2.4 (issue #24, M2): escalation-reason vocabulary reconciliation. Live enum diverged from
-- SOLUTION_DESIGN.md section 7.4's canonical set almost completely (only WAREHOUSE_REPLY_CONFLICT
-- overlapped before this migration). Backup taken before this migration: pg_dump to local
-- scratchpad, 2026-08-23 (not committed).
--
-- Design citation: SOLUTION_DESIGN.md section 7.4 (nine canonical reasons, OPEN/ACKNOWLEDGED/
-- IN_PROGRESS/RESOLVED/CANCELLED status lifecycle).
--
-- Live-usage audit done before writing this file (read-only queries, not assumed):
--   NO_SLOT: 2 rows (1 OPEN, 1 RESOLVED) -- section 7.4 names this NO_FEASIBLE_SLOT. A real rename,
--     not a drop: both rows are migrated, not orphaned, and the three code call sites that write
--     "NO_SLOT" are fixed in the same change (backend/app/assistant/tools.py:141,476,
--     backend/app/services/escalation_service.py:153).
--   CONTRADICTORY, APPROVAL_REQUIRED, REGULATED, EMERGENCY: 0 live rows, and confirmed via
--     repo-wide grep to appear only in the ESCALATION_TYPES set definition itself, never written
--     by any tool or service call -- dead declared values, safe to drop with no data migration.
--   REQUIRES_TIME_RESOLUTION (41 rows), REQUIRES_DOCK_REASSIGNMENT (116 rows),
--     PENDING_EXPIRED_UNACTIONED (E1.5), WAREHOUSE_REPLY_CONFLICT: not section 7.4's operational
--     vocabulary (the first two are D12's backfill worklist, D9's expiry is the third) -- kept as-is,
--     not touched by this migration.

BEGIN;

-- 1. Drop the old constraint first -- the rename below needs to write a value ('NO_FEASIBLE_SLOT')
-- the *old* constraint does not yet allow, so the constraint must not be active while it runs.
ALTER TABLE public.escalation_queue DROP CONSTRAINT IF EXISTS escalation_queue_escalation_type_check;

-- 2. Rename the two live NO_SLOT rows now that nothing blocks the new value.
UPDATE public.escalation_queue
SET escalation_type = 'NO_FEASIBLE_SLOT'
WHERE escalation_type = 'NO_SLOT';

-- 3. Rebuild escalation_type: drop the four dead values and NO_SLOT (renamed above), add the
-- seven canonical reasons not yet present. Keep WAREHOUSE_REPLY_CONFLICT (already canonical) and
-- the D12/D9 worklist categories (not section 7.4's vocabulary, but real and in use).
ALTER TABLE public.escalation_queue ADD CONSTRAINT escalation_queue_escalation_type_check
  CHECK (escalation_type = ANY (ARRAY[
    'NO_FEASIBLE_SLOT', 'PENDING_EXPIRED_UNACTIONED', 'AMBIGUOUS_SHIPMENT', 'LOW_CONFIDENCE_ETA',
    'WAREHOUSE_REPLY_CONFLICT', 'NOTIFICATION_FAILED', 'NOTIFICATION_UNROUTABLE',
    'SAFETY_OR_REGULATED', 'CAPACITY_EVENT_CASCADE',
    'REQUIRES_TIME_RESOLUTION', 'REQUIRES_DOCK_REASSIGNMENT'
  ]));

-- 4. escalation_status: section 7.4's lifecycle is OPEN -> ACKNOWLEDGED -> IN_PROGRESS -> RESOLVED
-- (plus CANCELLED). ACKNOWLEDGED was missing entirely -- added here as vocabulary; wiring the
-- actual acknowledge-transition logic (an owner being assigned) is application code, not this
-- migration's job, and is not claimed as done by adding the value.
ALTER TABLE public.escalation_queue DROP CONSTRAINT IF EXISTS escalation_queue_escalation_status_check;
ALTER TABLE public.escalation_queue ADD CONSTRAINT escalation_queue_escalation_status_check
  CHECK (escalation_status = ANY (ARRAY[
    'OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'CANCELLED'
  ]));

COMMIT;
