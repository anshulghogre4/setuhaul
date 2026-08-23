"""Driver-facing reads: the driver record and the operational snapshot around it.

E2.2 (issue #22): `app/api/v1/routers/driver.py` and `app/services/driver_reads.py` each carried
their own copy of the same six queries -- byte-identical SQL, assembled into two payloads that
differ by one key. The SQL now lives here once; the two callers keep their own payload shapes so
no response changes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError

# Statuses that take a shipment out of a driver's active workload. Kept here beside the query it
# filters so the router and the service cannot drift apart on what "active" means.
_INACTIVE_STATUSES = ("COMPLETED", "CANCELLED")


async def load_driver_operational_snapshot(session: AsyncSession, driver_id: str) -> dict[str, Any]:
    """Driver, their recent shipments, and the appointment/facility/ETA around the primary one.

    Raises NOT_FOUND when the driver row is missing, matching both previous implementations.
    The three per-shipment reads are skipped entirely when the driver has no shipments, which is
    why they are guarded rather than issued unconditionally.
    """
    driver = (
        await session.execute(
            text(
                """
                SELECT driver_id, driver_name, phone, licence_number, home_base_city, driver_status
                FROM public.drivers WHERE driver_id = :driver_id
                """
            ),
            {"driver_id": driver_id},
        )
    ).mappings().first()
    if driver is None:
        raise AppError("Driver not found.", code="NOT_FOUND", status_code=404)

    shipments = (
        await session.execute(
            text(
                """
                SELECT shipment_id, order_reference, destination_facility_id, current_status,
                       latest_eta_ts, original_eta_ts, priority_code, updated_at
                FROM public.shipments
                WHERE driver_id = :driver_id
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 20
                """
            ),
            {"driver_id": driver_id},
        )
    ).mappings().all()

    active = [s for s in shipments if s["current_status"] not in _INACTIVE_STATUSES]
    primary = active[0] if active else (shipments[0] if shipments else None)

    appointment = None
    facility = None
    latest_eta = None
    if primary is not None:
        appointment = (
            await session.execute(
                text(
                    """
                    SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                           a.is_current, a.booked_at, a.confirmed_at, a.updated_at,
                           s.dock_id, s.facility_id, s.slot_start_ts, s.slot_end_ts, s.slot_status
                    FROM public.appointments a
                    LEFT JOIN public.appointment_slots s ON s.slot_id = a.slot_id
                    WHERE a.shipment_id = :shipment_id
                    ORDER BY a.is_current DESC, a.updated_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"shipment_id": primary["shipment_id"]},
            )
        ).mappings().first()
        facility = (
            await session.execute(
                text(
                    """
                    SELECT facility_id, facility_name, city, state, timezone, open_time, close_time
                    FROM public.facilities WHERE facility_id = :facility_id
                    """
                ),
                {"facility_id": primary["destination_facility_id"]},
            )
        ).mappings().first()
        latest_eta = (
            await session.execute(
                text(
                    """
                    SELECT eta_update_id, shipment_id, source_type, declared_eta_ts,
                           delay_reason_code, confidence_code, created_at
                    FROM public.eta_updates
                    WHERE shipment_id = :shipment_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"shipment_id": primary["shipment_id"]},
            )
        ).mappings().first()

    return {
        "driver": dict(driver),
        "shipments": [dict(s) for s in shipments],
        "active_shipments": [dict(s) for s in active],
        "primary_shipment": dict(primary) if primary else None,
        "current_appointment": dict(appointment) if appointment else None,
        "latest_eta": dict(latest_eta) if latest_eta else None,
        "facility": dict(facility) if facility else None,
    }
