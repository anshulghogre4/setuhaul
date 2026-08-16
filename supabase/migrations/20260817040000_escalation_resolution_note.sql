-- Additive: persist the free-text remark an Ops/Admin user enters when
-- resolving an escalation, so the driver-facing get_exception_status tool
-- can surface it. Previously accepted by the API and silently discarded.

ALTER TABLE public.escalation_queue
  ADD COLUMN IF NOT EXISTS resolution_note text NULL;

ALTER TABLE public.driver_exceptions
  ADD COLUMN IF NOT EXISTS resolution_note text NULL;
