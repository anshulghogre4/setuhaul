"""Operations-portal reads: shipment rollups, exceptions and the appointment schedule.

E2.2 (issue #22): this SQL was embedded directly in `app/api/v1/routers/operations.py`, which
also resolved facility scope inline -- the router was neither thin nor scope-free. Every
`facility_id` parameter reaching this module is an *already-resolved* scope from
`repositories.scope.resolve_facility_scope`, never a raw client argument (`M15`/`NFR-019`);
`None` means "no facility filter" and is only ever produced for a global-read persona.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def count_shipments_by_status(session: AsyncSession, facility_id: str | None) -> dict[str, int]:
    facility_filter = "AND s.destination_facility_id = :facility_id" if facility_id else ""
    params = {"facility_id": facility_id} if facility_id else {}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT current_status, count(*)::int AS n
                FROM public.shipments s
                WHERE 1=1 {facility_filter}
                GROUP BY current_status
                """
            ),
            params,
        )
    ).mappings().all()
    return {row["current_status"]: row["n"] for row in rows}


async def count_open_exceptions(session: AsyncSession, facility_id: str | None) -> int:
    # Scoping this count needs a join to shipments, because driver_exceptions carries no facility
    # of its own -- a shipment's destination facility is what places an exception in a facility.
    exception_join = (
        "JOIN public.shipments s ON s.shipment_id = e.shipment_id "
        "AND s.destination_facility_id = :facility_id"
        if facility_id
        else ""
    )
    params = {"facility_id": facility_id} if facility_id else {}
    return (
        await session.execute(
            text(
                f"""
                SELECT count(*)::int AS n
                FROM public.driver_exceptions e
                {exception_join}
                WHERE e.exception_status NOT IN ('CLOSED', 'RESOLVED')
                """
            ),
            params,
        )
    ).scalar_one()


async def list_exceptions(session: AsyncSession, facility_id: str | None) -> list[dict[str, Any]]:
    where = "WHERE s.destination_facility_id = :facility_id" if facility_id else ""
    params = {"facility_id": facility_id} if facility_id else {}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT e.exception_id, e.driver_id, e.shipment_id, s.destination_facility_id AS facility_id,
                       e.exception_type, e.exception_status, e.severity_code, e.description,
                       e.reported_at, e.declared_eta_ts, e.dedupe_key
                FROM public.driver_exceptions e
                LEFT JOIN public.shipments s ON s.shipment_id = e.shipment_id
                {where}
                ORDER BY e.reported_at DESC NULLS LAST
                LIMIT 100
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_planner_queue_rows(
    session: AsyncSession,
    *,
    facility_id: str,
    horizon_end: datetime | None,
    limit: int,
) -> list[dict[str, Any]]:
    """The §7.5.1 `get_planner_queue` candidate set -- one row per pending request (FR-PLN-010).

    Deliberately *not* `list_appointment_schedule` above, and not
    `escalation_service.get_pending_confirmations`: both join `appointment_slots` for the
    interval, and D1 (§0.9) declares `dock_occupancy` the authority for what time a dock is
    actually taken. The slot row cannot see a 75-minute unload booked into a 60-minute slot
    (§6.2 #1), so a planner reading a slot interval is reading a number the booking path does
    not use.

    `dock_occupancy` is joined **LEFT**, not INNER, on purpose. A pending appointment can
    legitimately hold no claim -- E1.1's backfill routed 50 genuinely-overlapping pairs to the
    D12 worklist instead of claiming for them
    (`20260823060000_d1_correctness_bedrock.sql`), and `allocation._release_dock_occupancy`
    deletes a claim on release. An INNER JOIN would drop exactly those rows out of the queue,
    and the D9 sweeper (`scheduling/expiry.py::_pending_candidates`) would then expire them
    unseen and open a `PENDING_EXPIRED_UNACTIONED` escalation for a request no planner was ever
    shown. The fallback interval mirrors `allocation._claim_dock_occupancy`'s window expression
    character for character (slot start + `expected_unload_min` + the flat 15-minute changeover
    buffer, half-open) so "occupied" means one thing everywhere; the caller reports which source
    it got via `interval_source`.

    `WHERE` mirrors the sweeper's own candidate predicate (`appointment_status =
    'PENDING_CONFIRMATION' AND is_current = 1`) so the queue shows precisely the set that is
    under the D9 clock -- no more, and crucially no less. `booking_source` is returned rather
    than filtered: §7.3 describes the queue as exception-driven (`DRIVER_CHAT` /
    `SCHEDULING_TOOL`), but filtering it here would re-create the hide-then-expire hole above
    for a `PLANNER`-sourced row left pending, so the distinction is handed to the caller.

    The `horizon_end` bound filters on `slot_start_ts` rather than the coalesced
    `interval_start`, which is not the inconsistency it looks like: `_claim_dock_occupancy` builds
    the claim window *starting at* `sl.slot_start_ts`, so the two lower bounds are equal by
    construction. Filtering on the alias would need a subquery for no behavioural gain.

    `ORDER BY booked_at ASC` is the *truncation* order, not the display order -- the composite
    urgency of §7.3 is computed in the service. Oldest-first is the honest way to cut the list,
    because `booked_at` is what the D9 deadline is derived from, so the rows kept under a
    `LIMIT` are the ones closest to expiring.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.booking_source, a.is_current, a.booked_at,
                       -- #64: expires_at is written only by hold_for_information (the one-shot
                       -- D9 extension), so non-NULL doubles as the "hold already used" marker
                       -- the UI needs to disable the Hold action (edge-cases.md #6: prevention,
                       -- not error handling) and to render the paused countdown.
                       a.expires_at,
                       (a.expires_at IS NOT NULL) AS hold_used,
                       s.order_reference, s.driver_id, s.carrier_id, s.priority_code,
                       s.required_dock_type, s.expected_unload_min, s.original_eta_ts,
                       dr.driver_name, c.carrier_name,
                       sl.facility_id, sl.slot_start_ts, sl.slot_end_ts,
                       d.dock_id, d.dock_code, d.dock_type,
                       occ.window_start AS occupancy_start,
                       occ.window_end AS occupancy_end,
                       COALESCE(occ.window_start, sl.slot_start_ts) AS interval_start,
                       COALESCE(
                           occ.window_end,
                           sl.slot_start_ts
                             + ((s.expected_unload_min + 15) || ' minutes')::interval
                       ) AS interval_end,
                       le.effective_eta_ts, le.eta_confidence, le.eta_source,
                       fc.queue_state, fc.queue_position, fc.gate_in_ts,
                       ex.exception_id AS limit_exception_id,
                       ex.latest_acceptable_ts
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                JOIN public.docks d ON d.dock_id = sl.dock_id
                JOIN public.drivers dr ON dr.driver_id = s.driver_id
                JOIN public.carriers c ON c.carrier_id = s.carrier_id
                LEFT JOIN LATERAL (
                    SELECT lower(o."window") AS window_start, upper(o."window") AS window_end
                    FROM public.dock_occupancy o
                    WHERE o.appointment_id = a.appointment_id
                    ORDER BY o.occupancy_id ASC
                    LIMIT 1
                ) occ ON true
                LEFT JOIN public.v_latest_eta le ON le.shipment_id = a.shipment_id
                LEFT JOIN public.facility_checkins fc ON fc.shipment_id = a.shipment_id
                LEFT JOIN LATERAL (
                    SELECT e.exception_id, e.latest_acceptable_ts
                    FROM public.driver_exceptions e
                    WHERE e.shipment_id = a.shipment_id
                      AND e.latest_acceptable_ts IS NOT NULL
                    ORDER BY e.reported_at DESC
                    LIMIT 1
                ) ex ON true
                WHERE a.appointment_status = 'PENDING_CONFIRMATION'
                  AND a.is_current = 1
                  AND sl.facility_id = :facility_id
                  AND (
                      CAST(:horizon_end AS timestamptz) IS NULL
                      OR sl.slot_start_ts < CAST(:horizon_end AS timestamptz)
                  )
                ORDER BY a.booked_at ASC
                LIMIT :limit
                """
            ),
            {"facility_id": facility_id, "horizon_end": horizon_end, "limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------------------------
# The hold-aware half of `list_live_dock_occupancy` (issue #84).
#
# Held as a separate literal rather than an interpolated fragment so that with the D2 flag off the
# statement below is *byte-identical* to the one that shipped -- the only guarantee that makes this
# change zero-risk on a database where `20260829134929_d2_held_state_dock_occupancy.sql` has not
# been applied. `o.state` / `o.expires_at` / `o.shipment_id` do not exist there, and PostgreSQL
# resolves column references at parse time, so a runtime `if` inside one statement would not have
# saved it: an unapplied migration turns the whole read into `UndefinedColumn`, not an empty result.
_LIVE_DOCK_OCCUPANCY_SQL = """
                SELECT o.occupancy_id, o.dock_id, o.appointment_id,
                       lower(o."window") AS window_start,
                       upper(o."window") AS window_end,
                       a.shipment_id, a.appointment_status, s.order_reference
                FROM public.dock_occupancy o
                JOIN public.appointments a ON a.appointment_id = o.appointment_id
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                JOIN public.docks d ON d.dock_id = o.dock_id
                WHERE d.facility_id = :facility_id
                  AND a.appointment_status = ANY(:active_statuses)
                  AND o."window" && tstzrange(:range_start, :range_end, '[)')
                ORDER BY o.dock_id ASC, lower(o."window") ASC
"""

_LIVE_DOCK_OCCUPANCY_WITH_HOLDS_SQL = """
                SELECT o.occupancy_id, o.dock_id, o.appointment_id,
                       lower(o."window") AS window_start,
                       upper(o."window") AS window_end,
                       COALESCE(a.shipment_id, o.shipment_id) AS shipment_id,
                       COALESCE(a.appointment_status, o.state) AS appointment_status,
                       CASE WHEN o.appointment_id IS NULL
                            THEN 'dock_occupancy_hold' ELSE 'appointments'
                       END AS claim_source,
                       o.expires_at AS hold_expires_at,
                       s.order_reference
                FROM public.dock_occupancy o
                LEFT JOIN public.appointments a ON a.appointment_id = o.appointment_id
                LEFT JOIN public.shipments s
                  ON s.shipment_id = COALESCE(a.shipment_id, o.shipment_id)
                JOIN public.docks d ON d.dock_id = o.dock_id
                WHERE d.facility_id = :facility_id
                  AND o."window" && tstzrange(:range_start, :range_end, '[)')
                  AND (
                        a.appointment_status = ANY(:active_statuses)
                     OR (o.appointment_id IS NULL AND o.state = ANY(:hold_states))
                  )
                ORDER BY o.dock_id ASC, lower(o."window") ASC
"""


async def list_live_dock_occupancy(
    session: AsyncSession,
    *,
    facility_id: str,
    range_start: datetime,
    range_end: datetime,
    active_statuses: list[str],
    include_holds: bool = False,
    hold_states: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Every live dock claim in one facility overlapping a bounding window.

    The raw material for §7.3's displacement check. Fetched as one flat set rather than a
    correlated sub-select per queue row: the overlap test itself is then pure Python
    (`services/planner_service.py::_conflicts_for`), which keeps it unit-testable without a
    database and costs one query for the whole page instead of N.

    `&&` on a half-open `tstzrange` is the same predicate the `EXCLUDE USING gist` constraint on
    this table enforces, so "overlaps" means exactly what the database means by it -- notably,
    two abutting windows (`[10:00,11:00)` and `[11:00,12:00)`) do **not** overlap
    (PostgreSQL "Range Functions and Operators": `&&` is "have any elements in common", while
    adjacency is the separate `-|-` operator).

    ## `include_holds` -- issue #84, and why the join had to stop being INNER

    D2 models a hold as a `dock_occupancy` row with `appointment_id IS NULL`
    (`SOLUTION_DESIGN.md` §4: *"Held is not booked: no appointments row exists yet"*), so the
    `JOIN public.appointments` this query shipped with dropped every hold on the floor. Reproduced
    empirically 2026-08-29 against PostgreSQL 18.3 built from this repo's own migration chain: with
    one live `HELD` row on `DOCK-JAI-D1`, the shipped statement returned **0 rows** while the same
    cluster refused a competing claim on that interval with
    `dock_occupancy_dock_id_window_excl`. The displacement preview said "nobody would be hurt"
    about capacity the database was already defending.

    Two things about the hold predicate are deliberate and were each checked against the live
    constraint rather than assumed:

    * **`o.state = ANY(:hold_states)`, and no `expires_at > now()` term.** §0.8 tells *promise*
      reads to filter `state = 'HELD' AND expires_at > now()`, and the driver/carrier reads
      (issues #83/#85) do exactly that. This query answers a different question -- "what will
      PostgreSQL refuse?" -- and the exclusion constraint's predicate is
      `WHERE (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS'))` with **no time
      term at all**. Verified empirically the same day: a `HELD` row whose TTL lapsed ten minutes
      ago, which the M8 sweeper has not yet retired, still raises the exclusion violation. Adding
      the expiry filter here would therefore have re-introduced a smaller version of the same lie.
      The caller receives `hold_expires_at` and can say "a lapsed hold the sweeper has not retired
      yet" rather than pretending it is not there.
    * **`COALESCE(a.appointment_status, o.state)`, not `o.state` alone.** For an
      *appointment-backed* row `o.state` drifts: `allocation._claim_dock_occupancy` inserts without
      naming a state (taking the column default `'PENDING_CONFIRMATION'`) and
      `allocation.confirm_appointment` deliberately does not touch `dock_occupancy` at all, so a
      CONFIRMED appointment's claim row still reads `PENDING_CONFIRMATION`. `appointments` remains
      the authority for a row that has an appointment; `o.state` answers only for the rows that
      have none.

    `shipments` is joined **LEFT**, and that is not defensive tidying. `dock_occupancy.shipment_id`
    ships *nullable* -- the D2 migration defers `SET NOT NULL` to a follow-up so it can be applied
    ahead of the `_claim_dock_occupancy` fix that populates it -- so between those two deploys a
    freshly written claim legitimately has no `shipment_id`. An inner join would drop exactly such a
    row, which is issue #84's own failure mode wearing a different hat: a claim that consumes
    capacity must never disappear from the query that predicts refusals because a *display* column
    is NULL. `order_reference` is then NULL for that row, which is the honest answer.
    """
    sql = _LIVE_DOCK_OCCUPANCY_WITH_HOLDS_SQL if include_holds else _LIVE_DOCK_OCCUPANCY_SQL
    params: dict[str, Any] = {
        "facility_id": facility_id,
        "active_statuses": active_statuses,
        "range_start": range_start,
        "range_end": range_end,
    }
    if include_holds:
        params["hold_states"] = list(hold_states or [])
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [dict(row) for row in rows]


async def list_appointment_schedule(session: AsyncSession, facility_id: str | None) -> list[dict[str, Any]]:
    where = "WHERE sl.facility_id = :facility_id" if facility_id else ""
    params = {"facility_id": facility_id} if facility_id else {}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.is_current, a.booked_at, a.confirmed_at, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts, sl.slot_status
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                {where}
                ORDER BY sl.slot_start_ts NULLS LAST
                LIMIT 200
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]
