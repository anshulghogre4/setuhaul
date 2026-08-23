"""Facility, dock, slot and facility-rule reads.

Holds the SQL that `app/api/v1/routers/operations.py` used to execute inline (E2.2, issue #22),
plus the one scope-supporting probe that `repositories.scope.assert_facility_visible` needs but
cannot answer itself because it depends on data, not on the caller's identity alone.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def driver_serves_facility(session: AsyncSession, driver_id: str | None, facility_id: str) -> bool:
    """True when any shipment assigned to this driver is bound for this facility.

    This is a driver's only claim on a facility record: they may read the destination they are
    actually driving to, and nothing else. Callers pass the result to
    `repositories.scope.assert_facility_visible`, which owns the decision.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM public.shipments
                WHERE driver_id = :driver_id AND destination_facility_id = :facility_id
                LIMIT 1
                """
            ),
            {"driver_id": driver_id, "facility_id": facility_id},
        )
    ).first()
    return row is not None


async def get_facility(session: AsyncSession, facility_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT facility_id, facility_name, city, state, timezone, open_time, close_time,
                       checkin_grace_min, default_unload_min, active_flag
                FROM public.facilities WHERE facility_id = :facility_id
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_facility_contacts(session: AsyncSession, facility_id: str) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT contact_id, facility_id, contact_name, contact_role, phone, email
                FROM public.facility_contacts WHERE facility_id = :facility_id
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_facilities(session: AsyncSession, facility_id: str | None) -> list[dict[str, Any]]:
    """Every facility, or just one when the caller's resolved scope names one.

    `facility_id` here is an already-resolved scope from `repositories.scope`, never a raw
    client argument -- the caller must resolve before calling.
    """
    where = "WHERE facility_id = :facility_id" if facility_id else ""
    params = {"facility_id": facility_id} if facility_id else {}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT facility_id, facility_name, city, state, timezone, open_time, close_time,
                       checkin_grace_min, default_unload_min, active_flag
                FROM public.facilities
                {where}
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_facility_rules(session: AsyncSession, facility_id: str | None) -> list[dict[str, Any]]:
    where = "WHERE fr.facility_id = :facility_id" if facility_id else ""
    params = {"facility_id": facility_id} if facility_id else {}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT fr.rule_id, fr.facility_id, fr.rule_type, fr.rule_value, fr.description,
                       fr.effective_from, fr.effective_to, fr.active_flag
                FROM public.facility_rules fr
                {where}
                ORDER BY fr.facility_id, fr.rule_id
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_docks(session: AsyncSession, facility_id: str | None) -> list[dict[str, Any]]:
    where = "WHERE d.facility_id = :facility_id" if facility_id else ""
    params = {"facility_id": facility_id} if facility_id else {}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT d.dock_id, d.facility_id, d.dock_code, d.dock_type,
                       d.supports_refrigerated, d.max_vehicle_weight_kg, d.dock_status
                FROM public.docks d
                {where}
                ORDER BY d.dock_id
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def list_appointment_slots(session: AsyncSession, facility_id: str | None) -> list[dict[str, Any]]:
    where = "WHERE s.facility_id = :facility_id" if facility_id else ""
    params = {"facility_id": facility_id} if facility_id else {}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT s.slot_id, s.facility_id, s.dock_id, s.slot_start_ts, s.slot_end_ts,
                       s.slot_status, s.block_reason, s.created_at
                FROM public.appointment_slots s
                {where}
                ORDER BY s.slot_start_ts
                LIMIT 200
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]
