from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_execution_context, get_request_id
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext

router = APIRouter(prefix="/api/v1", tags=["shipments"])


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/shipments/{shipment_id}")
async def get_shipment(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                       origin_name, origin_city, destination_facility_id, customer_name,
                       product_category, load_weight_kg, pallet_count, required_dock_type,
                       temperature_control_required, priority_code, planned_departure_ts,
                       actual_departure_ts, original_eta_ts, latest_eta_ts, expected_unload_min,
                       current_status, created_at, updated_at
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)

    if ctx.is_driver:
        if row["driver_id"] != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    elif ctx.is_operator:
        if row["destination_facility_id"] != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    elif not ctx.is_admin:
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)

    return ok(
        {"as_of": _as_of(), "source": "postgresql", "shipment": dict(row), "freshness": "live"},
        get_request_id(request),
    )


@router.get("/shipments/{shipment_id}/appointment/current")
async def current_appointment(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    shipment = (
        await session.execute(
            text(
                "SELECT shipment_id, driver_id, destination_facility_id FROM public.shipments "
                "WHERE shipment_id = :shipment_id"
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)

    if ctx.is_driver and shipment["driver_id"] != ctx.driver_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    if ctx.is_operator and shipment["destination_facility_id"] != ctx.facility_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    if not (ctx.is_driver or ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)

    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.is_current, a.booked_at, a.confirmed_at, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts, sl.slot_status
                FROM public.appointments a
                LEFT JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.shipment_id = :shipment_id AND a.is_current = 1
                ORDER BY a.updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()

    return ok(
        {
            "as_of": _as_of(),
            "source": "postgresql",
            "appointment": dict(row) if row else None,
            "freshness": "live",
            "label": "current_appointment_observation",
        },
        get_request_id(request),
    )
