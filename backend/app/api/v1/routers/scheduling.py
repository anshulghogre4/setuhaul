from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    OPS_PORTAL_ROLES,
    get_db_session,
    get_execution_context,
    get_request_id,
    require_roles,
)
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.allocation import (
    CancelAppointmentCommand,
    ConfirmAppointmentCommand,
    ExpireAppointmentCommand,
    RejectAppointmentCommand,
    RequestSlotCommand,
    RescheduleAppointmentCommand,
    cancel_appointment,
    confirm_appointment,
    expire_appointment,
    get_appointment_request_status,
    reject_appointment,
    request_slot,
    reschedule_appointment,
)
from app.scheduling.feasibility import find_feasible_slots

router = APIRouter(prefix="/api/v1", tags=["scheduling"])


class CancelAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cancellation_reason: str = Field(min_length=1, max_length=500)
    client_message_id: str | None = Field(default=None, max_length=200)


class ConfirmAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_confirmation_ref: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class RescheduleAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_slot_id: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    displayed_policy_version: str | None = Field(default=None, max_length=100)
    displayed_recommendation_id: str | None = Field(default=None, max_length=100)
    client_message_id: str | None = Field(default=None, max_length=200)


class RejectAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rejection_reason: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=500)


class ExpireAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expire_reason: str = Field(min_length=1, max_length=500)


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
    body = ok(result.model_dump(), get_request_id(request), message=message)
    if result.code in {"SLOT_CONFLICT_REFRESH_REQUIRED", "SLOT_OPTIONS_STALE"}:
        body["success"] = False
        body["errors"] = [{"code": result.code, "detail": message, "field": None}]
        return JSONResponse(status_code=409, content=body)
    return body


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/reschedule")
async def reschedule_shipment_appointment(
    shipment_id: str, appointment_id: str, body: RescheduleAppointmentBody, request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER, *OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)
    try:
        result = await reschedule_appointment(
            session, ctx, shipment_id=shipment_id,
            command=RescheduleAppointmentCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    response = ok(result.model_dump(), get_request_id(request), message="Replacement appointment requested.")
    if result.code in {"SLOT_CONFLICT_REFRESH_REQUIRED", "SLOT_OPTIONS_STALE"}:
        response["success"] = False
        response["errors"] = [{"code": result.code, "detail": "Refresh options and select again.", "field": None}]
        return JSONResponse(status_code=409, content=response)
    return response


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


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/cancel")
async def cancel_shipment_appointment(
    shipment_id: str,
    appointment_id: str,
    body: CancelAppointmentBody,
    request: Request,
    ctx: Annotated[
        ExecutionContext,
        Depends(require_roles(RoleName.DRIVER, *OPS_PORTAL_ROLES)),
    ],
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
        result = await cancel_appointment(
            session,
            ctx,
            shipment_id=shipment_id,
            command=CancelAppointmentCommand(
                appointment_id=appointment_id,
                **body.model_dump(),
            ),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message="Appointment cancelled and slot capacity released.",
    )


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/confirm")
async def confirm_shipment_appointment(
    shipment_id: str,
    appointment_id: str,
    body: ConfirmAppointmentBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
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
        result = await confirm_appointment(
            session,
            ctx,
            shipment_id=shipment_id,
            command=ConfirmAppointmentCommand(
                appointment_id=appointment_id,
                **body.model_dump(),
            ),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message="Appointment confirmed by operations.",
    )


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/reject")
async def reject_shipment_appointment(
    shipment_id: str, appointment_id: str, body: RejectAppointmentBody, request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)
    try:
        result = await reject_appointment(
            session, ctx, shipment_id=shipment_id,
            command=RejectAppointmentCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request), message="Appointment rejected by operations.")


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/expire")
async def expire_shipment_appointment(
    shipment_id: str, appointment_id: str, body: ExpireAppointmentBody, request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)
    try:
        result = await expire_appointment(
            session, ctx, shipment_id=shipment_id,
            command=ExpireAppointmentCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request), message="Appointment expired by operations.")
