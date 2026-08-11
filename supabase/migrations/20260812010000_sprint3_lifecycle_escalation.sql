-- Sprint 3 lifecycle completion and durable human escalation queue.
-- Additive except for widening existing CHECK constraints.

DO $$
DECLARE
  constraint_name text;
BEGIN
  -- The baseline used an auto-generated name; locate it by its definition so
  -- this migration remains safe when the baseline was restored elsewhere.
  FOR constraint_name IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'public.appointments'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%appointment_status%'
  LOOP
    EXECUTE format('ALTER TABLE public.appointments DROP CONSTRAINT %I', constraint_name);
  END LOOP;
END $$;

ALTER TABLE public.appointments
  ADD CONSTRAINT appointments_appointment_status_check
  CHECK (appointment_status IN (
    'PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS', 'COMPLETED',
    'CANCELLED', 'NO_SHOW', 'REJECTED', 'EXPIRED'
  ));

-- Audit actions are constrained in the frozen baseline, so lifecycle evidence
-- requires the corresponding additive widening.
DO $$
DECLARE
  constraint_name text;
BEGIN
  FOR constraint_name IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'public.audit_logs'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%action_type%'
  LOOP
    EXECUTE format('ALTER TABLE public.audit_logs DROP CONSTRAINT %I', constraint_name);
  END LOOP;
END $$;

ALTER TABLE public.audit_logs
  ADD CONSTRAINT audit_logs_action_type_check
  CHECK (action_type IN (
    'LOGIN', 'LOGOUT', 'VIEW', 'CREATE', 'UPDATE', 'DELETE',
    'BOOK_APPOINTMENT', 'CANCEL_APPOINTMENT', 'UPDATE_ETA', 'SEND_MESSAGE',
    'RESCHEDULE_APPOINTMENT', 'REJECT_APPOINTMENT', 'EXPIRE_APPOINTMENT'
  ));

CREATE TABLE IF NOT EXISTS public.escalation_queue (
  escalation_id text PRIMARY KEY,
  shipment_id text NOT NULL REFERENCES public.shipments(shipment_id),
  facility_id text NOT NULL REFERENCES public.facilities(facility_id),
  driver_id text NULL REFERENCES public.drivers(driver_id),
  escalation_type text NOT NULL CHECK (escalation_type IN (
    'NO_SLOT', 'CONTRADICTORY', 'APPROVAL_REQUIRED', 'REGULATED',
    'EMERGENCY', 'WAREHOUSE_REPLY_CONFLICT'
  )),
  escalation_status text NOT NULL DEFAULT 'OPEN' CHECK (escalation_status IN (
    'OPEN', 'IN_PROGRESS', 'RESOLVED', 'CANCELLED'
  )),
  severity_code text NOT NULL DEFAULT 'HIGH',
  policy_version text,
  recommendation_id text NULL,
  payload_json text NOT NULL,
  dedupe_key text NOT NULL UNIQUE,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  resolved_at text NULL,
  resolved_by_user_id text NULL
);

CREATE INDEX IF NOT EXISTS escalation_queue_facility_status_created_idx
  ON public.escalation_queue (facility_id, escalation_status, created_at);

ALTER TABLE public.escalation_queue ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.escalation_queue FROM anon, authenticated;
GRANT ALL ON TABLE public.escalation_queue TO postgres, service_role;
