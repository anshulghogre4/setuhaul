from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_execution_context, get_request_id, require_roles
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.allocation import RequestSlotCommand, get_appointment_request_status, request_slot
from app.scheduling.feasibility import find_feasible_slots

router = APIRouter(prefix="/api/v1", tags=["scheduling"])


@router.get("/shipments/{shipment_id}/slots/feasible")
async def feasible_slots(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> dict[str, Any]:
    result = await find_feasible_slots(session, ctx, shipment_id, limit=limit)
    return ok(result.model_dump(), get_request_id(request), message="Feasible slot options computed.")


@router.post("/shipments/{shipment_id}/slots/{slot_id}/request")
async def request_shipment_slot(
    shipment_id: str,
    slot_id: str,
    body: RequestSlotCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            status_code=400,
        )
    try:
        result = await request_slot(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            command=body,
            idempotency_key=idempotency_key.strip(),
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    message = (
        "Slot request is pending warehouse confirmation."
        if result.code == "SLOT_REQUESTED"
        else "Selected slot is no longer available; refreshed options returned."
    )
    return ok(result.model_dump(), get_request_id(request), message=message)


@router.get("/shipments/{shipment_id}/appointment-request/status")
async def appointment_request_status(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    appointment_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    result = await get_appointment_request_status(
        session,
        ctx,
        shipment_id=shipment_id,
        appointment_id=appointment_id,
    )
    return ok(result.model_dump(), get_request_id(request), message="Appointment request status loaded.")
