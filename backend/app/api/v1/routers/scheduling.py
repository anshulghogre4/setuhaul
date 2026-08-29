from datetime import datetime
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
    MAX_BULK_CONFIRM_IDS,
    BulkConfirmCommand,
    CancelAppointmentCommand,
    ConfirmAppointmentCommand,
    CounterOfferCommand,
    ExpireAppointmentCommand,
    RejectAppointmentCommand,
    RequestSlotCommand,
    RescheduleAppointmentCommand,
    bulk_confirm,
    cancel_appointment,
    confirm_appointment,
    counter_offer,
    expire_appointment,
    get_appointment_request_status,
    reject_appointment,
    request_slot,
    reschedule_appointment,
)
from app.scheduling.feasibility import find_feasible_slots
from app.scheduling.holds import confirm_held_slot

router = APIRouter(prefix="/api/v1", tags=["scheduling"])


class CancelAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cancellation_reason: str = Field(min_length=1, max_length=500)
    client_message_id: str | None = Field(default=None, max_length=200)


class ConfirmAppointmentBody(BaseModel):
    """section 7.5.1 `confirm_request`. `snapshot_hash` is required (section 7.5 principle 3).

    `warehouse_confirmation_ref` became optional in issue #62 -- see
    `allocation.ConfirmAppointmentCommand` for why the mandatory version would have blocked every
    confirm the planner console makes.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_hash: str = Field(min_length=1, max_length=128)
    warehouse_confirmation_ref: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class CounterOfferBody(BaseModel):
    """section 7.5.1 `counter_offer` (issue #63). `appointment_id` comes from the path."""

    model_config = ConfigDict(extra="forbid")

    dock_id: str = Field(min_length=1, max_length=100)
    start_ts: datetime
    reason_code: str = Field(min_length=1, max_length=40)
    snapshot_hash: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=500)


class BulkConfirmBody(BaseModel):
    """section 7.5.1 `bulk_confirm` (issue #65).

    Not shipment-scoped, unlike every other route on this router: a spike-clearing batch crosses
    shipments by construction. Each id's facility scope is validated server-side, per id, from the
    verified identity (M15) -- there is no facility argument here for a client to supply.
    """

    model_config = ConfigDict(extra="forbid")

    appointment_ids: list[str] = Field(min_length=1, max_length=MAX_BULK_CONFIRM_IDS)
    snapshot_hash: str = Field(min_length=1, max_length=128)
    warehouse_confirmation_ref: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class RescheduleAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_slot_id: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    displayed_policy_version: str | None = Field(default=None, max_length=100)
    displayed_recommendation_id: str | None = Field(default=None, max_length=100)
    client_message_id: str | None = Field(default=None, max_length=200)


class RejectAppointmentBody(BaseModel):
    """section 7.5.1 `reject_request` (issue #66).

    **Wire change:** `rejection_reason` (free prose, 1-500 chars) became `reason_code`, validated
    against `allocation.REJECTION_REASON_CODES` in the service with a 422 naming the supported set.
    The value is rendered to the driver, which is section 7.5.1's stated reason for it being an
    enum. The old field name is not accepted as an alias -- grepped 2026-08-29, this router was its
    only caller, and keeping a deprecated free-prose door open would defeat the change.
    """

    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(min_length=1, max_length=40)
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


class ConfirmHeldSlotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


@router.post("/holds/{hold_id}/confirm")
async def confirm_hold(
    hold_id: str,
    body: ConfirmHeldSlotBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Section 7.1's `confirm_held_slot`: turn a live D2 hold into a PENDING_CONFIRMATION request.

    The route is `/holds/{hold_id}/confirm` rather than
    `/shipments/{shipment_id}/holds/{hold_id}/confirm` on purpose, and the difference is M15 rather
    than aesthetics: a shipment id in the path would be a client-supplied identifier sitting beside
    the hold id, and the natural (wrong) implementation scopes on the one the client sent. With only
    the hold id in the path there is nothing to trust -- the shipment is read off the held row and
    the caller's authority over *that* shipment is what is checked.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            status_code=400,
        )
    try:
        result = await confirm_held_slot(
            session,
            ctx,
            hold_id=hold_id,
            note=body.note,
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    response = ok(
        result.model_dump(),
        get_request_id(request),
        message="Slot request is pending warehouse confirmation.",
    )
    if result.code in {"HOLD_EXPIRED", "HOLD_ALREADY_ACTIONED", "SLOT_CONFLICT_REFRESH_REQUIRED"}:
        detail = (result.conflict or {}).get("message") or "That hold is no longer live."
        response["success"] = False
        response["errors"] = [{"code": result.code, "detail": detail, "field": None}]
        return JSONResponse(status_code=409, content=response)
    return response


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


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/counter-offer")
async def counter_offer_shipment_appointment(
    shipment_id: str,
    appointment_id: str,
    body: CounterOfferBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """section 7.5.1 `counter_offer` / `FR-PLN-002` (issue #63).

    Role gate is `OPS_PORTAL_ROLES`, matching the confirm/reject/expire routes it sits beside, with
    `allocation._assert_ops_scope` doing the actual facility check. **Owner fork:** section 7.5.1 is
    the *planner* catalog, and `routers/planner.py` deliberately narrows its two tools to
    `WAREHOUSE_PLANNER` + `ADMIN`. Narrowing here too would be defensible -- but narrowing
    `confirm_request`, a shipped endpoint, is a behaviour change that belongs in its own issue, and
    a new route that is stricter than its own sibling confirm would be an inconsistency with no
    safety gain.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    try:
        result = await counter_offer(
            session, ctx, shipment_id=shipment_id,
            command=CounterOfferCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message="Counter-offer recorded; the proposed interval is now held for this shipment.",
    )


@router.post("/appointments/bulk-confirm")
async def bulk_confirm_appointments(
    body: BulkConfirmBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """section 7.5.1 `bulk_confirm` / `FR-PLN-006` (issue #65).

    Always 200 with a per-id outcome list, never a partial 4xx: Flow 6 step 4 requires the skipped
    rows to be *named* rather than the call to fail, and a batch where 5 of 6 ids were written is
    not an error condition. The batch-level `code` stays `BULK_CONFIRM_COMPLETED`; the per-id codes
    carry the outcome.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    try:
        result = await bulk_confirm(
            session, ctx,
            command=BulkConfirmCommand(**body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message=f"{result.confirmed} confirmed, {result.skipped} skipped.",
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
