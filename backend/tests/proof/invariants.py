"""The six section 10.2 invariant queries, as named SQL constants.

Design citation: `SOLUTION_DESIGN.md` section 10.2 ("Invariant queries, run continuously in CI"),
section 6.2 #7 (the two known weight violations), section 6.2 #9 (`dock_status_events` is the
single authority for availability), section 5 Stage 1 ("rule absence is permission, not
inheritance"), D1/D12/D15. GitHub issue #44.

They live in their own module rather than inline in the test so that the same six statements can be
lifted into a CI job, a psql check or an ops dashboard without importing pytest. Section 10.2 says
"run continuously in CI", and a query buried inside an assertion is not liftable.

Every query returns **rows that violate**, never a boolean, so a failure names the offending
appointment instead of just saying "false".
"""

from __future__ import annotations

# The four states that consume capacity, matching `dock_occupancy_dock_id_window_excl`'s own
# predicate (migration 20260829134929, step 5) character for character. If these two ever drifted
# the invariant would be checking something the database is not enforcing.
CAPACITY_CONSUMING_STATES = ("HELD", "PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")
ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")


# ----------------------------------------------------------------------------------------------
# 1. The headline invariant. "The GiST constraint should make it unfalsifiable, and the query
#    proves it." Self-join rather than a window function because the output has to name BOTH rows
#    of an overlapping pair -- a planner resolving one needs to see what it collides with.
# ----------------------------------------------------------------------------------------------
INV1_OVERLAPPING_DOCK_OCCUPANCY = """
SELECT a.occupancy_id AS left_occupancy_id,
       b.occupancy_id AS right_occupancy_id,
       a.dock_id,
       a.state AS left_state,
       b.state AS right_state,
       a."window" * b."window" AS overlap
FROM public.dock_occupancy a
JOIN public.dock_occupancy b
       ON b.dock_id = a.dock_id
      AND b.occupancy_id > a.occupancy_id
      AND a."window" && b."window"
WHERE a.state = ANY(:capacity_states)
  AND b.state = ANY(:capacity_states)
ORDER BY a.dock_id, a.occupancy_id, b.occupancy_id
"""


# ----------------------------------------------------------------------------------------------
# 2. "No shipment has >1 current active appointment."
#    `is_current = 1` alone is not the test: APT1001 is COMPLETED with is_current = 1 in the shipped
#    seed, and a completed appointment is history, not a live claim. Both conditions are required.
# ----------------------------------------------------------------------------------------------
INV2_MULTIPLE_ACTIVE_APPOINTMENTS = """
SELECT shipment_id,
       count(*) AS active_count,
       string_agg(appointment_id, ',' ORDER BY appointment_id) AS appointment_ids
FROM public.appointments
WHERE is_current = 1
  AND appointment_status = ANY(:active_statuses)
GROUP BY shipment_id
HAVING count(*) > 1
ORDER BY shipment_id
"""


# ----------------------------------------------------------------------------------------------
# 3. "No confirmed appointment overlaps a `dock_status_events` outage window."
#    The overlap predicate is copied from the engine's own candidate scan
#    (`feasibility.find_feasible_slots`) rather than re-derived: `event_start_ts < slot_end_ts AND
#    (event_end_ts IS NULL OR event_end_ts > slot_start_ts)`. Checking a different predicate here
#    than the one the engine schedules by would make this invariant meaningless.
#
#    Every event type counts, deliberately. `evaluate_candidate_slot` blocks on the presence of ANY
#    overlapping `dock_status_events` row, so a CAPACITY_REDUCTION is as much a scheduling blocker
#    as a BREAKDOWN as far as the live engine is concerned, and the invariant must reflect the
#    system's actual behaviour rather than a narrower reading of the word "outage".
# ----------------------------------------------------------------------------------------------
INV3_CONFIRMED_OVER_OUTAGE = """
SELECT a.appointment_id,
       a.shipment_id,
       a.appointment_status,
       sl.slot_id,
       sl.dock_id,
       sl.slot_start_ts,
       sl.slot_end_ts,
       e.dock_event_id,
       e.event_type,
       e.event_start_ts,
       e.event_end_ts
FROM public.appointments a
JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
JOIN public.dock_status_events e
       ON e.dock_id = sl.dock_id
      AND e.event_start_ts < sl.slot_end_ts
      AND (e.event_end_ts IS NULL OR e.event_end_ts > sl.slot_start_ts)
WHERE a.is_current = 1
  AND a.appointment_status = ANY(:active_statuses)
ORDER BY a.appointment_id, e.dock_event_id
"""


# ----------------------------------------------------------------------------------------------
# 4. "No appointment starts after LAST_NEW_START_TIME without a recorded approval -- at facilities
#    that define the rule; FAC-GGN-01 does not, and an absent rule is unrestricted (section 5
#    Stage 1)." The INNER JOIN onto the rule is what encodes "rule absence is permission": a
#    facility with no such rule contributes no rows at all, rather than inheriting another's.
#
#    "A recorded approval" has no dedicated column in the shipped schema, so it is defined here,
#    explicitly, as either of the two artefacts that actually exist and actually mean a human
#    signed off: a `warehouse_confirmation_ref` on the appointment, or an APPROVAL_REQUIRED
#    escalation for that shipment. Stated rather than assumed, because an unstated definition here
#    would silently decide whether the invariant is satisfiable at all.
#
#    `AT TIME ZONE f.timezone` converts the timestamptz to the facility's own wall clock, which is
#    the only clock '21:00' can possibly mean.
# ----------------------------------------------------------------------------------------------
INV4_LATE_START_WITHOUT_APPROVAL = """
WITH last_start AS (
    SELECT facility_id, rule_value::time AS last_new_start
    FROM public.facility_rules
    WHERE rule_type = 'LAST_NEW_START_TIME'
      AND active_flag = 1
)
SELECT a.appointment_id,
       a.shipment_id,
       sl.slot_id,
       sl.facility_id,
       (sl.slot_start_ts AT TIME ZONE f.timezone)::time AS local_start_time,
       r.last_new_start
FROM public.appointments a
JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
JOIN public.facilities f ON f.facility_id = sl.facility_id
JOIN last_start r ON r.facility_id = sl.facility_id
WHERE a.is_current = 1
  AND a.appointment_status = ANY(:active_statuses)
  AND (sl.slot_start_ts AT TIME ZONE f.timezone)::time > r.last_new_start
  AND a.warehouse_confirmation_ref IS NULL
  AND NOT EXISTS (
        SELECT 1 FROM public.escalation_queue eq
        WHERE eq.shipment_id = a.shipment_id
          AND eq.escalation_type = 'APPROVAL_REQUIRED'
  )
ORDER BY a.appointment_id
"""


# ----------------------------------------------------------------------------------------------
# 5. "Every reefer load sits on a `supports_refrigerated` dock."
# ----------------------------------------------------------------------------------------------
INV5_REEFER_ON_NON_REEFER_DOCK = """
SELECT a.appointment_id,
       s.shipment_id,
       s.temperature_control_required,
       d.dock_id,
       d.dock_code,
       d.dock_type,
       d.supports_refrigerated
FROM public.appointments a
JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
JOIN public.docks d ON d.dock_id = sl.dock_id
JOIN public.shipments s ON s.shipment_id = a.shipment_id
WHERE a.is_current = 1
  AND a.appointment_status = ANY(:active_statuses)
  AND s.temperature_control_required = 1
  AND d.supports_refrigerated = 0
ORDER BY a.appointment_id
"""


# ----------------------------------------------------------------------------------------------
# 6. "Every load above a dock's `max_vehicle_weight_kg` is rejected -- which, run against the
#    shipped seed, must return exactly the two known violations of section 6.2 #7 and nothing else."
#
#    `shipments.load_weight_kg`, not the vehicle's capacity. Section 6.2 #7 settles the ambiguity
#    explicitly: "the column name says vehicle, RULE004's text says load ... **We compare
#    `shipments.load_weight_kg`**". Both seeded rows violate under either reading, so the expected
#    result does not depend on this choice -- but the choice still has to be written down, because
#    it decides which options are feasible for every OTHER shipment.
# ----------------------------------------------------------------------------------------------
INV6_LOAD_OVER_DOCK_WEIGHT_LIMIT = """
SELECT a.appointment_id,
       s.shipment_id,
       s.load_weight_kg,
       d.dock_id,
       d.dock_code,
       d.max_vehicle_weight_kg
FROM public.appointments a
JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
JOIN public.docks d ON d.dock_id = sl.dock_id
JOIN public.shipments s ON s.shipment_id = a.shipment_id
WHERE a.is_current = 1
  AND a.appointment_status = ANY(:active_statuses)
  AND s.load_weight_kg > d.max_vehicle_weight_kg
ORDER BY a.appointment_id
"""


INVARIANTS: dict[str, str] = {
    "inv1_no_overlapping_dock_occupancy": INV1_OVERLAPPING_DOCK_OCCUPANCY,
    "inv2_no_shipment_with_two_active_appointments": INV2_MULTIPLE_ACTIVE_APPOINTMENTS,
    "inv3_no_active_appointment_over_a_dock_outage": INV3_CONFIRMED_OVER_OUTAGE,
    "inv4_no_late_start_without_approval": INV4_LATE_START_WITHOUT_APPROVAL,
    "inv5_every_reefer_load_on_a_refrigerated_dock": INV5_REEFER_ON_NON_REEFER_DOCK,
    "inv6_no_load_over_its_dock_weight_limit": INV6_LOAD_OVER_DOCK_WEIGHT_LIMIT,
}
