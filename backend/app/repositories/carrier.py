"""Carrier-portal reads (`E3.3`, issue #27, `SOLUTION_DESIGN.md` §7.5.6).

Every `carrier_id` parameter reaching this module is an *already-resolved* scope from
`repositories.scope.resolve_carrier_scope` -- derived from the verified identity, never a client
argument (`M15`/`NFR-019`). Unlike `repositories/operations.py`, `carrier_id` is never optional
here: there is no "no carrier filter" case, because no carrier persona may ever read across
carriers.

**The inference-risk rule governs every query in this file**
(`UI-UX/00-foundations/auth-and-scoping.md`, "The inference risk, stated plainly"; `U28`). Not one
statement below computes a facility-wide, cross-carrier or peer aggregate -- not even as an
intermediate value that gets divided away, because a total a carrier can subtract their own figure
from leaks the remainder. Every `count(*)` here sits behind a `carrier_id = :carrier_id`
predicate; if you add a query, that predicate is not optional.

Timestamp typing note: migration `20260823060000_d1_correctness_bedrock.sql` converted
`shipments`/`appointments`/`appointment_slots`/`facility_checkins` timestamps to real
`timestamptz`, but `driver_exceptions.reported_at` and `escalation_queue.created_at` are still
TEXT. Those two are cast with `::timestamptz` before any comparison or ordering, because
lexicographic text ordering is not chronological once offsets differ (live rows carry both
`+00` and `+05:30` -- verified 2026-08-23) -- the same reasoning `scheduling/feasibility.py:626`
records for its own TEXT columns.

IN-list style follows `scheduling/feasibility.py:618`: `NOT IN :param` plus
`bindparam(..., expanding=True)`, which SQLAlchemy 2.0 rewrites into the right number of
parameter slots per execution rather than string-interpolating the values.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# A shipment is "active" when it is neither finished nor called off. Mirrors the live
# shipments.current_status check constraint (baseline migration line 105) minus its two terminal
# values, rather than enumerating an "active" list that would silently drop a status added later.
_TERMINAL_SHIPMENT_STATUSES = ("COMPLETED", "CANCELLED")

# Closed states per table's own check constraint. Kept as explicit closed-sets (not open-sets) so
# a newly added status is treated as open and shows up, rather than vanishing from the carrier's
# exception list because nobody remembered to add it here.
_CLOSED_EXCEPTION_STATUSES = ("RESOLVED", "DUPLICATE", "CANCELLED")
_CLOSED_ESCALATION_STATUSES = ("RESOLVED", "CANCELLED")

# On-time = arrived early or on time. `arrival_state` is the already-recorded ground truth on
# facility_checkins (baseline migration line 217: EARLY/ON_TIME/LATE/NO_SHOW), so this metric
# reads a fact the gate process already established rather than re-deriving punctuality from a
# timestamp comparison this module would have to invent a tolerance for.
_ON_TIME_ARRIVAL_STATES = ("ON_TIME", "EARLY")

_EXCEPTION_STATUS_PARAMS = {
    "closed_exception_statuses": list(_CLOSED_EXCEPTION_STATUSES),
    "closed_escalation_statuses": list(_CLOSED_ESCALATION_STATUSES),
}

_EXCEPTION_STATUS_BINDS = (
    bindparam("closed_exception_statuses", expanding=True),
    bindparam("closed_escalation_statuses", expanding=True),
)

# The open-items set, defined once and used by both `list_open_exceptions` and
# `count_open_exceptions`. One definition on purpose: an earlier draft counted *shipments with
# something open* for the overview tile while the list returned *items*, which on live data gave
# 73 against 75 rows (measured 2026-08-23, CAR001) -- a carrier reading "73 open exceptions" above
# a list of 75 has been told something false about their own fleet.
#
# The column list here is also the enforcement mechanism for "status only" (§7.5.6,
# `components.md` §3): `escalation_queue.resolved_by_user_id`, `severity_code`, `policy_version`,
# `recommendation_id`, `payload_json` and `dedupe_key` are all absent on purpose -- no owner name,
# no SLA clock, no stepper, and no `queue_position` read from anywhere. There is no ranking field
# to select, because nothing in this projection is comparative in the first place (`U28`).
_OPEN_EXCEPTION_ITEMS_SQL = """
    SELECT 'DRIVER_EXCEPTION' AS source,
           e.exception_id AS reference_id,
           e.shipment_id,
           d.driver_name,
           e.exception_type AS reason_code,
           e.exception_status AS status,
           e.reported_at::timestamptz AS occurred_at
    FROM public.driver_exceptions e
    JOIN public.shipments s ON s.shipment_id = e.shipment_id
    JOIN public.drivers d ON d.driver_id = e.driver_id
    WHERE s.carrier_id = :carrier_id
      AND e.exception_status NOT IN :closed_exception_statuses
    UNION ALL
    SELECT 'ESCALATION',
           q.escalation_id,
           q.shipment_id,
           d.driver_name,
           q.escalation_type,
           q.escalation_status,
           q.created_at::timestamptz
    FROM public.escalation_queue q
    JOIN public.shipments s ON s.shipment_id = q.shipment_id
    LEFT JOIN public.drivers d ON d.driver_id = q.driver_id
    WHERE s.carrier_id = :carrier_id
      AND q.escalation_status NOT IN :closed_escalation_statuses
"""

# Shared subquery answering a *different* question: does this one shipment have anything open
# against it? That is the fleet row's warning flag and the HAS_OPEN_EXCEPTION filter -- a
# per-shipment boolean, not a count of items, which is why it is not derived from the union above.
# Both nonetheless read the same two tables with the same closed-status sets, so a shipment can
# never be flagged in the list while being absent from the exceptions section
# (`UI-UX/05-carrier-portal/edge-cases.md` #3 depends on exactly that).
_HAS_OPEN_EXCEPTION_SQL = """
    (
        EXISTS (
            SELECT 1 FROM public.driver_exceptions e
            WHERE e.shipment_id = s.shipment_id
              AND e.exception_status NOT IN :closed_exception_statuses
        )
        OR EXISTS (
            SELECT 1 FROM public.escalation_queue q
            WHERE q.shipment_id = s.shipment_id
              AND q.escalation_status NOT IN :closed_escalation_statuses
        )
    )
"""


async def count_active_shipments(session: AsyncSession, carrier_id: str) -> int:
    return (
        await session.execute(
            text(
                """
                SELECT count(*)::int
                FROM public.shipments s
                WHERE s.carrier_id = :carrier_id
                  AND s.current_status NOT IN :terminal_statuses
                """
            ).bindparams(bindparam("terminal_statuses", expanding=True)),
            {"carrier_id": carrier_id, "terminal_statuses": list(_TERMINAL_SHIPMENT_STATUSES)},
        )
    ).scalar_one()


async def count_open_exceptions(session: AsyncSession, carrier_id: str) -> int:
    """Open items from both sources, counted over this carrier's shipments only.

    Wraps `_OPEN_EXCEPTION_ITEMS_SQL` in `COUNT(*)` -- the exact same rows `list_open_exceptions`
    returns, just counted instead of fetched. Two different definitions here previously gave 73
    (distinct shipments with something open, via `_HAS_OPEN_EXCEPTION_SQL`) against 75 (items) on
    live data (measured 2026-08-23, CAR001): a carrier reading "73 open exceptions" above a list
    of 75 rows was told something false about their own fleet. `_HAS_OPEN_EXCEPTION_SQL` still
    answers a genuinely different, legitimate question elsewhere (does *this one* shipment have
    anything open, for `list_fleet_shipments`'s per-row flag) -- it is not wrong there, only wrong
    as a stand-in for this count.
    """
    return (
        await session.execute(
            text(f"SELECT count(*)::int FROM ({_OPEN_EXCEPTION_ITEMS_SQL}) t").bindparams(
                *_EXCEPTION_STATUS_BINDS
            ),
            {"carrier_id": carrier_id, **_EXCEPTION_STATUS_PARAMS},
        )
    ).scalar_one()


async def count_shipments_ever(session: AsyncSession, carrier_id: str) -> int:
    """Lifetime shipment count for this carrier, for the empty-state distinction only.

    `FR-CAR-006` / `edge-cases.md` #5 require "no active shipments right now" and "no shipments on
    record yet" to read differently, and the client cannot tell those apart from an empty list
    alone. Answering it server-side keeps the surface from having to make a second speculative
    call to find out which empty state it is in.
    """
    return (
        await session.execute(
            text("SELECT count(*)::int FROM public.shipments WHERE carrier_id = :carrier_id"),
            {"carrier_id": carrier_id},
        )
    ).scalar_one()


async def list_fleet_shipments(
    session: AsyncSession,
    carrier_id: str,
    *,
    appointment_status: str | None = None,
    only_with_open_exception: bool = False,
) -> list[dict[str, Any]]:
    """This carrier's shipments across every facility they operate at (§7.5.6).

    Cross-facility by design and with no facility filter at all: §7.5.6 notes carriers are not
    facility-scoped, unlike every other role, so there is deliberately no `facility_id` parameter
    to narrow this with. Facility is a column value per row, never a scope control
    (`UI-UX/05-carrier-portal/screens.md` §1).

    The current appointment is joined by LATERAL rather than a plain `is_current = 1` join so a
    shipment that somehow carries two current rows yields one row here instead of duplicating in
    the carrier's fleet list -- the same "most recently updated wins" tie-break
    `services/driver_reads.get_current_appointment` already applies.

    `has_open_exception` is computed in an inner select and filtered on in the outer one so the
    shared EXISTS fragment appears exactly once per statement; recomputing it in the WHERE clause
    would be a second identical scan for no benefit.
    """
    inner_filter = ""
    params: dict[str, Any] = {"carrier_id": carrier_id, **_EXCEPTION_STATUS_PARAMS}
    if appointment_status:
        inner_filter = " AND appt.appointment_status = :appointment_status"
        params["appointment_status"] = appointment_status
    outer_filter = "WHERE t.has_open_exception" if only_with_open_exception else ""

    rows = (
        await session.execute(
            text(
                f"""
                SELECT * FROM (
                    SELECT s.shipment_id,
                           s.order_reference,
                           s.current_status,
                           s.latest_eta_ts,
                           s.original_eta_ts,
                           s.updated_at,
                           d.driver_id,
                           d.driver_name,
                           f.facility_id,
                           f.facility_name,
                           f.city AS facility_city,
                           appt.appointment_status AS promise_state,
                           appt.slot_start_ts,
                           appt.slot_end_ts,
                           appt.dock_code,
                           {_HAS_OPEN_EXCEPTION_SQL} AS has_open_exception
                    FROM public.shipments s
                    JOIN public.drivers d ON d.driver_id = s.driver_id
                    JOIN public.facilities f ON f.facility_id = s.destination_facility_id
                    LEFT JOIN LATERAL (
                        SELECT a.appointment_status, sl.slot_start_ts, sl.slot_end_ts, dk.dock_code
                        FROM public.appointments a
                        JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                        LEFT JOIN public.docks dk ON dk.dock_id = sl.dock_id
                        WHERE a.shipment_id = s.shipment_id AND a.is_current = 1
                        ORDER BY a.updated_at DESC NULLS LAST
                        LIMIT 1
                    ) appt ON TRUE
                    WHERE s.carrier_id = :carrier_id
                      {inner_filter}
                ) t
                {outer_filter}
                ORDER BY t.updated_at DESC NULLS LAST, t.shipment_id
                LIMIT 200
                """
            ).bindparams(*_EXCEPTION_STATUS_BINDS),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def get_fleet_shipment(
    session: AsyncSession, carrier_id: str, shipment_id: str
) -> dict[str, Any] | None:
    """One shipment, scoped in SQL -- a cross-carrier id simply produces no row.

    Scoping in the predicate rather than fetching and then comparing is deliberate: another
    carrier's row is never read into this process at all, so no later code path can accidentally
    return a field from it. The caller still passes the result through
    `repositories.scope.assert_shipment_in_carrier_fleet`, which is what turns "no row" into the
    refusal `edge-cases.md` #1 requires -- and because a nonexistent id and a cross-carrier id
    both land here as `None`, the two are indistinguishable to the client, as that same section
    demands ("never confirms or denies whether the shipment exists at all outside their scope").
    """
    row = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.order_reference, s.carrier_id, s.driver_id,
                       s.origin_name, s.origin_city, s.customer_name, s.product_category,
                       s.load_weight_kg, s.pallet_count, s.required_dock_type,
                       s.temperature_control_required, s.priority_code,
                       s.planned_departure_ts, s.actual_departure_ts,
                       s.original_eta_ts, s.latest_eta_ts, s.expected_unload_min,
                       s.current_status, s.created_at, s.updated_at,
                       d.driver_name,
                       v.registration_number, v.vehicle_type_code,
                       f.facility_id, f.facility_name, f.city AS facility_city,
                       appt.appointment_id, appt.appointment_status AS promise_state,
                       appt.slot_start_ts, appt.slot_end_ts, appt.dock_code,
                       appt.booked_at, appt.confirmed_at
                FROM public.shipments s
                JOIN public.drivers d ON d.driver_id = s.driver_id
                JOIN public.vehicles v ON v.vehicle_id = s.vehicle_id
                JOIN public.facilities f ON f.facility_id = s.destination_facility_id
                LEFT JOIN LATERAL (
                    SELECT a.appointment_id, a.appointment_status, a.booked_at, a.confirmed_at,
                           sl.slot_start_ts, sl.slot_end_ts, dk.dock_code
                    FROM public.appointments a
                    JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                    LEFT JOIN public.docks dk ON dk.dock_id = sl.dock_id
                    WHERE a.shipment_id = s.shipment_id AND a.is_current = 1
                    ORDER BY a.updated_at DESC NULLS LAST
                    LIMIT 1
                ) appt ON TRUE
                WHERE s.shipment_id = :shipment_id
                  AND s.carrier_id = :carrier_id
                """
            ),
            {"shipment_id": shipment_id, "carrier_id": carrier_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_shipment_history(
    session: AsyncSession, carrier_id: str, shipment_id: str
) -> list[dict[str, Any]]:
    """Outcome-only timeline for one shipment (`screens.md` §2, `components.md` §4).

    Deliberately omits every free-text field on the tables it reads --
    `appointments.cancellation_reason`, `driver_exceptions.description`/`resolution_note`,
    `eta_updates.note`, `escalation_queue.payload_json`. `components.md` §4 draws that line
    explicitly ("History never surfaces another party's internal-only content"), and the safe way
    to hold it is a column allowlist rather than a redaction pass over a `SELECT *`.

    Still carries `AND s.carrier_id = :carrier_id` (via the `scoped` CTE) even though the caller
    has already refused a cross-carrier shipment: this function is one `text()` call away from
    being reused by something that hasn't, and a timeline is exactly the shape that leaks quietly.
    """
    rows = (
        await session.execute(
            text(
                """
                WITH scoped AS (
                    SELECT s.shipment_id
                    FROM public.shipments s
                    WHERE s.shipment_id = :shipment_id AND s.carrier_id = :carrier_id
                )
                SELECT 'ETA_UPDATE' AS event_type,
                       e.created_at::timestamptz AS occurred_at,
                       e.source_type AS detail_code,
                       e.delay_reason_code AS reason_code
                FROM public.eta_updates e JOIN scoped ON scoped.shipment_id = e.shipment_id
                UNION ALL
                SELECT 'APPOINTMENT_BOOKED', a.booked_at::timestamptz, a.appointment_status, NULL
                FROM public.appointments a JOIN scoped ON scoped.shipment_id = a.shipment_id
                WHERE a.booked_at IS NOT NULL
                UNION ALL
                SELECT 'APPOINTMENT_CONFIRMED', a.confirmed_at::timestamptz, a.appointment_status, NULL
                FROM public.appointments a JOIN scoped ON scoped.shipment_id = a.shipment_id
                WHERE a.confirmed_at IS NOT NULL
                UNION ALL
                SELECT 'APPOINTMENT_CANCELLED', a.cancelled_at::timestamptz, a.appointment_status, NULL
                FROM public.appointments a JOIN scoped ON scoped.shipment_id = a.shipment_id
                WHERE a.cancelled_at IS NOT NULL
                UNION ALL
                SELECT 'EXCEPTION_REPORTED', x.reported_at::timestamptz, x.exception_status, x.exception_type
                FROM public.driver_exceptions x JOIN scoped ON scoped.shipment_id = x.shipment_id
                UNION ALL
                SELECT 'GATE_IN', c.gate_in_ts::timestamptz, c.arrival_state, NULL
                FROM public.facility_checkins c JOIN scoped ON scoped.shipment_id = c.shipment_id
                WHERE c.gate_in_ts IS NOT NULL
                UNION ALL
                SELECT 'DOCK_IN', c.dock_in_ts::timestamptz, c.queue_state, NULL
                FROM public.facility_checkins c JOIN scoped ON scoped.shipment_id = c.shipment_id
                WHERE c.dock_in_ts IS NOT NULL
                UNION ALL
                SELECT 'GATE_OUT', c.gate_out_ts::timestamptz, c.queue_state, NULL
                FROM public.facility_checkins c JOIN scoped ON scoped.shipment_id = c.shipment_id
                WHERE c.gate_out_ts IS NOT NULL
                ORDER BY occurred_at
                LIMIT 100
                """
            ),
            {"shipment_id": shipment_id, "carrier_id": carrier_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_open_exceptions(session: AsyncSession, carrier_id: str) -> list[dict[str, Any]]:
    """Open items on this carrier's shipments -- status only (§7.5.6, `components.md` §3).

    The column list is the enforcement mechanism for "never another carrier's queue position or
    why a contested interval was lost" (`U28`) and for `components.md` §3's "no owner name, no SLA
    clock, no stepper": `escalation_queue.resolved_by_user_id`, `severity_code`, `policy_version`,
    `recommendation_id`, `payload_json` and `dedupe_key` are all absent on purpose, and
    `queue_position` is not read from any table here. There is no ranking field to select, because
    nothing in this projection is comparative in the first place.
    """
    rows = (
        await session.execute(
            text(f"{_OPEN_EXCEPTION_ITEMS_SQL} ORDER BY occurred_at DESC LIMIT 100").bindparams(
                *_EXCEPTION_STATUS_BINDS
            ),
            {"carrier_id": carrier_id, **_EXCEPTION_STATUS_PARAMS},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def get_on_time_totals(
    session: AsyncSession, carrier_id: str, *, window_start: datetime, window_end: datetime
) -> dict[str, int]:
    """This carrier's own arrivals in one window: how many, how many punctual.

    NO_SHOWs are outside this metric by construction -- the window predicate is on `gate_in_ts`,
    and a vehicle that never arrived has none. Stated rather than silently true, because the
    figure would otherwise look like it should include them.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT count(*)::int AS arrivals,
                       count(*) FILTER (
                           WHERE c.arrival_state IN :on_time_states
                       )::int AS on_time
                FROM public.facility_checkins c
                JOIN public.shipments s ON s.shipment_id = c.shipment_id
                WHERE s.carrier_id = :carrier_id
                  AND c.arrival_state IS NOT NULL
                  AND c.gate_in_ts >= :window_start
                  AND c.gate_in_ts < :window_end
                """
            ).bindparams(bindparam("on_time_states", expanding=True)),
            {
                "carrier_id": carrier_id,
                "on_time_states": list(_ON_TIME_ARRIVAL_STATES),
                "window_start": window_start,
                "window_end": window_end,
            },
        )
    ).mappings().first()
    return {"arrivals": int(row["arrivals"]), "on_time": int(row["on_time"])}


async def get_on_time_daily_series(
    session: AsyncSession, carrier_id: str, *, window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    """Daily points for the sparkline (`U33`/`U66`) -- this carrier's own arrivals only.

    Days with no arrivals are absent rather than zero-filled: a zero-percent point would draw a
    sparkline trough that reads as "everything was late" when it actually means "no data", which
    is the gaps-vs-zeros misreading a series like this has to avoid.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT date_trunc('day', c.gate_in_ts) AS day,
                       count(*)::int AS arrivals,
                       count(*) FILTER (
                           WHERE c.arrival_state IN :on_time_states
                       )::int AS on_time
                FROM public.facility_checkins c
                JOIN public.shipments s ON s.shipment_id = c.shipment_id
                WHERE s.carrier_id = :carrier_id
                  AND c.arrival_state IS NOT NULL
                  AND c.gate_in_ts >= :window_start
                  AND c.gate_in_ts < :window_end
                GROUP BY 1
                ORDER BY 1
                """
            ).bindparams(bindparam("on_time_states", expanding=True)),
            {
                "carrier_id": carrier_id,
                "on_time_states": list(_ON_TIME_ARRIVAL_STATES),
                "window_start": window_start,
                "window_end": window_end,
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]
