"""Operations-portal reads: shipment rollups, exceptions and the appointment schedule.

E2.2 (issue #22): this SQL was embedded directly in `app/api/v1/routers/operations.py`, which
also resolved facility scope inline -- the router was neither thin nor scope-free. Every
`facility_id` parameter reaching this module is an *already-resolved* scope from
`repositories.scope.resolve_facility_scope`, never a raw client argument (`M15`/`NFR-019`);
`None` means "no facility filter" and is only ever produced for a global-read persona.
"""

from __future__ import annotations

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
