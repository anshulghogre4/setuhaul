-- D1 correctness bedrock: btree_gist extension, TEXT->timestamptz across six tables,
-- dock_occupancy with a GiST EXCLUDE constraint as the real concurrency-safety mechanism,
-- backfill with conflicts routed to escalation_queue (D12 worklist) rather than silently
-- resolved or aborting the whole backfill.
--
-- Design citation: SOLUTION_DESIGN.md section 9.3, D1, D12, D14, D15, D16.
-- Backup taken before this migration: pg_dump to local scratchpad, 2026-08-23 (not committed,
-- not part of this repo).
--
-- Re-measured at execution time (2026-08-23), vs. the design doc's 2026-08-19 figures:
--   active appointments: 655 (matches)
--   weight violations (REQUIRES_DOCK_REASSIGNMENT candidates): 116 (matches)
--   true-interval overlaps (REQUIRES_TIME_RESOLUTION candidates): 50 pairs (design doc said 85 --
--     genuine drift over four days of live data; this migration uses the re-measured figure)
--
-- Worklist mechanism decision: reusing the existing escalation_queue table (extending its
-- escalation_type check constraint) rather than a new table -- same RLS/backend-only pattern,
-- same planner-facing consumption path already built in Sprint 3 for NO_SLOT/human cases.
-- D12 names the two worklist categories but does not name a table; this is the concrete choice.

BEGIN;

-- 1. btree_gist: required for a GiST exclusion constraint mixing an equality column (dock_id)
--    with a range-overlap column (window).
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- 2. Drop views that depend on columns being converted below. Postgres refuses ALTER COLUMN
--    TYPE while a view depends on the column. Recreated verbatim (step 4), in dependency order
--    (v_inbound_operational_state and v_current_facility_queue both depend on v_latest_eta).
DROP VIEW IF EXISTS public.v_inbound_operational_state;
DROP VIEW IF EXISTS public.v_current_facility_queue;
DROP VIEW IF EXISTS public.v_latest_eta;
DROP VIEW IF EXISTS public.v_slot_availability;

-- 3. TEXT -> timestamptz across all six tables named in SOLUTION_DESIGN.md section 9.3.
--    Values are ISO-8601 with a +05:30 offset and parse directly -- a type change, not a
--    reformat. Confirmed no functions or RLS policies reference these columns (checked
--    pg_proc/pg_policies directly before writing this migration); only the four views above.
ALTER TABLE public.appointment_slots
  ALTER COLUMN slot_start_ts TYPE timestamptz USING slot_start_ts::timestamptz,
  ALTER COLUMN slot_end_ts TYPE timestamptz USING slot_end_ts::timestamptz,
  ALTER COLUMN created_at TYPE timestamptz USING created_at::timestamptz;

ALTER TABLE public.appointments
  ALTER COLUMN booked_at TYPE timestamptz USING booked_at::timestamptz,
  ALTER COLUMN confirmed_at TYPE timestamptz USING confirmed_at::timestamptz,
  ALTER COLUMN cancelled_at TYPE timestamptz USING cancelled_at::timestamptz,
  ALTER COLUMN updated_at TYPE timestamptz USING updated_at::timestamptz;

ALTER TABLE public.shipments
  ALTER COLUMN planned_departure_ts TYPE timestamptz USING planned_departure_ts::timestamptz,
  ALTER COLUMN actual_departure_ts TYPE timestamptz USING actual_departure_ts::timestamptz,
  ALTER COLUMN original_eta_ts TYPE timestamptz USING original_eta_ts::timestamptz,
  ALTER COLUMN latest_eta_ts TYPE timestamptz USING latest_eta_ts::timestamptz,
  ALTER COLUMN created_at TYPE timestamptz USING created_at::timestamptz,
  ALTER COLUMN updated_at TYPE timestamptz USING updated_at::timestamptz;

ALTER TABLE public.dock_status_events
  ALTER COLUMN event_start_ts TYPE timestamptz USING event_start_ts::timestamptz,
  ALTER COLUMN event_end_ts TYPE timestamptz USING event_end_ts::timestamptz;

ALTER TABLE public.eta_updates
  ALTER COLUMN declared_eta_ts TYPE timestamptz USING declared_eta_ts::timestamptz,
  ALTER COLUMN created_at TYPE timestamptz USING created_at::timestamptz;

ALTER TABLE public.facility_checkins
  ALTER COLUMN gate_in_ts TYPE timestamptz USING gate_in_ts::timestamptz,
  ALTER COLUMN gate_out_ts TYPE timestamptz USING gate_out_ts::timestamptz,
  ALTER COLUMN dock_in_ts TYPE timestamptz USING dock_in_ts::timestamptz,
  ALTER COLUMN unload_start_ts TYPE timestamptz USING unload_start_ts::timestamptz,
  ALTER COLUMN unload_end_ts TYPE timestamptz USING unload_end_ts::timestamptz,
  ALTER COLUMN yard_queue_enter_ts TYPE timestamptz USING yard_queue_enter_ts::timestamptz,
  ALTER COLUMN updated_at TYPE timestamptz USING updated_at::timestamptz;

-- 4. Recreate the four views verbatim (pg_get_viewdef output read directly from the live DB
--    before dropping anything, reformatted for readability -- behavior unchanged; the
--    underlying columns are now real timestamptz instead of text with an implicit cast).
CREATE VIEW public.v_latest_eta AS
 WITH ranked AS (
         SELECT e.eta_update_id,
            e.shipment_id,
            e.source_type,
            e.reported_by_driver_id,
            e.declared_eta_ts,
            e.confidence_code,
            e.delay_reason_code,
            e.note,
            e.created_at,
            row_number() OVER (PARTITION BY e.shipment_id ORDER BY e.created_at DESC, e.eta_update_id DESC) AS rn
           FROM eta_updates e
        )
 SELECT s.shipment_id,
    s.original_eta_ts,
    COALESCE(r.declared_eta_ts, s.latest_eta_ts, s.original_eta_ts) AS effective_eta_ts,
    COALESCE(r.source_type, 'ORIGINAL_PLAN'::text) AS eta_source,
    COALESCE(r.confidence_code, 'HIGH'::text) AS eta_confidence,
    r.delay_reason_code,
    r.note AS eta_note,
    r.created_at AS eta_updated_at
   FROM shipments s
     LEFT JOIN ranked r ON r.shipment_id = s.shipment_id AND r.rn = 1;

CREATE VIEW public.v_slot_availability AS
 SELECT sl.slot_id,
    sl.facility_id,
    d.dock_code,
    d.dock_type,
    d.supports_refrigerated,
    d.max_vehicle_weight_kg,
    sl.slot_start_ts,
    sl.slot_end_ts,
        CASE
            WHEN sl.slot_status <> 'OPEN'::text THEN sl.slot_status
            WHEN a.appointment_id IS NOT NULL THEN 'OCCUPIED'::text
            ELSE 'AVAILABLE'::text
        END AS availability_status,
    a.appointment_id,
    a.shipment_id,
    a.appointment_status
   FROM appointment_slots sl
     JOIN docks d ON d.dock_id = sl.dock_id
     LEFT JOIN appointments a ON a.slot_id = sl.slot_id AND (a.appointment_status = ANY (ARRAY['PENDING_CONFIRMATION'::text, 'CONFIRMED'::text, 'IN_PROGRESS'::text]));

CREATE VIEW public.v_inbound_operational_state AS
 SELECT s.shipment_id,
    s.driver_id,
    s.vehicle_id,
    s.destination_facility_id,
    s.priority_code,
    s.required_dock_type,
    s.temperature_control_required,
    s.load_weight_kg,
    s.expected_unload_min,
    s.current_status,
    le.effective_eta_ts,
    le.eta_source,
    le.eta_confidence,
    ap.appointment_id,
    sl.slot_id,
    sl.slot_start_ts,
    sl.slot_end_ts,
    d.dock_code AS planned_dock_code,
    fc.gate_in_ts,
    fc.queue_state,
    fc.queue_position,
    ad.dock_code AS actual_dock_code
   FROM shipments s
     JOIN v_latest_eta le ON le.shipment_id = s.shipment_id
     LEFT JOIN appointments ap ON ap.shipment_id = s.shipment_id AND ap.is_current = 1 AND (ap.appointment_status = ANY (ARRAY['PENDING_CONFIRMATION'::text, 'CONFIRMED'::text, 'IN_PROGRESS'::text]))
     LEFT JOIN appointment_slots sl ON sl.slot_id = ap.slot_id
     LEFT JOIN docks d ON d.dock_id = sl.dock_id
     LEFT JOIN facility_checkins fc ON fc.shipment_id = s.shipment_id
     LEFT JOIN docks ad ON ad.dock_id = fc.actual_dock_id;

CREATE VIEW public.v_current_facility_queue AS
 SELECT fc.facility_id,
    fc.shipment_id,
    s.driver_id,
    s.vehicle_id,
    s.priority_code,
    fc.gate_in_ts,
    fc.arrival_state,
    fc.queue_state,
    fc.queue_position,
    le.effective_eta_ts,
    s.expected_unload_min,
    s.required_dock_type
   FROM facility_checkins fc
     JOIN shipments s ON s.shipment_id = fc.shipment_id
     JOIN v_latest_eta le ON le.shipment_id = s.shipment_id
  WHERE fc.queue_state = ANY (ARRAY['WAITING_EARLY'::text, 'WAITING_LATE'::text, 'WAITING_DOCK_UNAVAILABLE'::text, 'CALLED_TO_DOCK'::text]);

-- 5. dock_occupancy: the actual D1 concurrency mechanism -- one truck per dock per interval,
--    enforced structurally by Postgres, not by application-level locking alone.
CREATE TABLE IF NOT EXISTS public.dock_occupancy (
  occupancy_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dock_id text NOT NULL REFERENCES public.docks(dock_id),
  appointment_id text NOT NULL REFERENCES public.appointments(appointment_id),
  "window" tstzrange NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  EXCLUDE USING gist (dock_id WITH =, "window" WITH &&)
);

CREATE INDEX IF NOT EXISTS ix_dock_occupancy_appointment ON public.dock_occupancy (appointment_id);

-- 6. Extend escalation_queue for the two new D12 worklist reasons (backfill conflicts).
ALTER TABLE public.escalation_queue DROP CONSTRAINT IF EXISTS escalation_queue_escalation_type_check;
ALTER TABLE public.escalation_queue ADD CONSTRAINT escalation_queue_escalation_type_check
  CHECK (escalation_type = ANY (ARRAY[
    'NO_SLOT','CONTRADICTORY','APPROVAL_REQUIRED','REGULATED','EMERGENCY','WAREHOUSE_REPLY_CONFLICT',
    'REQUIRES_TIME_RESOLUTION','REQUIRES_DOCK_REASSIGNMENT'
  ]));

-- 7. Backfill: one dock_occupancy row per active appointment. A true-interval overlap raises
--    exclusion_violation, caught per-row and routed to escalation_queue as
--    REQUIRES_TIME_RESOLUTION (D12) rather than aborting the whole backfill or silently
--    dropping the row. A weight violation (load exceeds the assigned dock's rating) is a
--    separate, independent check -- the exclusion constraint has no opinion on weight -- and is
--    flagged as REQUIRES_DOCK_REASSIGNMENT (D15) whether or not the same row also had a time
--    conflict; dock_occupancy still gets the row on a weight violation alone (the truck really
--    is occupying that dock physically; the escalation is for the planner to reassign it later,
--    not a reason to pretend the slot is free).
DO $$
DECLARE
  r RECORD;
  computed_window tstzrange;
  time_conflict boolean;
BEGIN
  FOR r IN
    SELECT a.appointment_id, a.shipment_id, s.destination_facility_id, s.load_weight_kg,
           s.expected_unload_min, sl.dock_id, sl.slot_start_ts, d.max_vehicle_weight_kg
    FROM appointments a
    JOIN appointment_slots sl ON sl.slot_id = a.slot_id
    JOIN shipments s ON s.shipment_id = a.shipment_id
    JOIN docks d ON d.dock_id = sl.dock_id
    WHERE a.appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
  LOOP
    computed_window := tstzrange(r.slot_start_ts, r.slot_start_ts + ((r.expected_unload_min + 15) || ' minutes')::interval, '[)');
    time_conflict := false;

    BEGIN
      INSERT INTO dock_occupancy (dock_id, appointment_id, "window")
      VALUES (r.dock_id, r.appointment_id, computed_window);
    EXCEPTION WHEN exclusion_violation THEN
      time_conflict := true;
    END;

    IF time_conflict THEN
      INSERT INTO escalation_queue (
        escalation_id, shipment_id, facility_id, escalation_type, escalation_status,
        severity_code, payload_json, dedupe_key, created_at, updated_at
      ) VALUES (
        'ESC-D1BF-TIME-' || r.appointment_id,
        r.shipment_id, r.destination_facility_id, 'REQUIRES_TIME_RESOLUTION', 'OPEN', 'HIGH',
        json_build_object('appointment_id', r.appointment_id, 'dock_id', r.dock_id,
                           'reason', 'D1_BACKFILL_TIME_OVERLAP')::text,
        'D1BF-TIME-' || r.appointment_id, now()::text, now()::text
      ) ON CONFLICT (dedupe_key) DO NOTHING;
    END IF;

    IF r.load_weight_kg > r.max_vehicle_weight_kg THEN
      INSERT INTO escalation_queue (
        escalation_id, shipment_id, facility_id, escalation_type, escalation_status,
        severity_code, payload_json, dedupe_key, created_at, updated_at
      ) VALUES (
        'ESC-D1BF-WEIGHT-' || r.appointment_id,
        r.shipment_id, r.destination_facility_id, 'REQUIRES_DOCK_REASSIGNMENT', 'OPEN', 'HIGH',
        json_build_object('appointment_id', r.appointment_id, 'dock_id', r.dock_id,
                           'load_weight_kg', r.load_weight_kg, 'dock_max_kg', r.max_vehicle_weight_kg,
                           'reason', 'D1_BACKFILL_WEIGHT_VIOLATION')::text,
        'D1BF-WEIGHT-' || r.appointment_id, now()::text, now()::text
      ) ON CONFLICT (dedupe_key) DO NOTHING;
    END IF;
  END LOOP;
END $$;

COMMIT;
