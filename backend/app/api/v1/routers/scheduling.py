from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_execution_context, get_request_id
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext
from app.services.scheduling.booking import (
    cancel_appointment_service,
    request_slot_service,
    reschedule_appointment_service,
)
from app.services.scheduling.escalation import escalate_exception_service
from app.services.scheduling.feasibility import find_feasible_slots_service
from app.services.scheduling.schemas import (
    CancelAppointmentCommand,
    EscalationCommand,
    FeasibilitySearchCommand,
    RescheduleCommand,
    SlotBookingCommand,
)

router = APIRouter(prefix="/api/v1/scheduling", tags=["scheduling"])


@router.post("/slots/search")
async def search_feasible_slots(
    command: FeasibilitySearchCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Search feasible replacement dock slots based on ETA, dock specs, and facility rules."""
    res = await find_feasible_slots_service(session, ctx, command)
    return ok(res.model_dump(), get_request_id(request))


@router.post("/appointments/request")
async def request_slot(
    command: SlotBookingCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Atomically request and book a dock slot with row-level locking."""
    if idempotency_key:
        command.idempotency_key = idempotency_key
    res = await request_slot_service(session, ctx, command)
    return ok(res.model_dump(), get_request_id(request))


@router.post("/appointments/reschedule")
async def reschedule_appointment(
    command: RescheduleCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Reschedule an existing active appointment to a new target slot."""
    if idempotency_key:
        command.idempotency_key = idempotency_key
    res = await reschedule_appointment_service(session, ctx, command)
    return ok(res.model_dump(), get_request_id(request))


@router.post("/appointments/cancel")
async def cancel_appointment(
    command: CancelAppointmentCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Cancel an active appointment."""
    if idempotency_key:
        command.idempotency_key = idempotency_key
    res = await cancel_appointment_service(session, ctx, command)
    return ok(res, get_request_id(request))


@router.post("/exceptions/escalate")
async def escalate_exception(
    command: EscalationCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Escalate an unresolvable exception to operations for human takeover."""
    res = await escalate_exception_service(session, ctx, command)
    return ok(res, get_request_id(request))
