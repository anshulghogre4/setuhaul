from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_request_id, require_roles
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName

router = APIRouter(prefix="/api/v1", tags=["driver"])


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/driver/context")
async def driver_context(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    if not ctx.driver_id:
        raise AppError("Driver mapping missing.", code="DRIVER_UNMAPPED", status_code=403)

    driver = (
        await session.execute(
            text(
                """
                SELECT driver_id, driver_name, phone, licence_number, home_base_city, driver_status
                FROM public.drivers WHERE driver_id = :driver_id
                """
            ),
            {"driver_id": ctx.driver_id},
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
            {"driver_id": ctx.driver_id},
        )
    ).mappings().all()

    active = [s for s in shipments if s["current_status"] not in ("COMPLETED", "CANCELLED")]
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

    data = {
        "as_of": _as_of(),
        "source": "postgresql",
        "driver": dict(driver),
        "profile": {
            "user_id": ctx.user_id,
            "full_name": ctx.full_name,
            "email": ctx.email,
            "facility_id": ctx.facility_id,
        },
        "shipments": [dict(s) for s in shipments],
        "primary_shipment": dict(primary) if primary else None,
        "current_appointment": dict(appointment) if appointment else None,
        "latest_eta": dict(latest_eta) if latest_eta else None,
        "facility": dict(facility) if facility else None,
        "freshness": "live",
    }
    return ok(data, get_request_id(request))
