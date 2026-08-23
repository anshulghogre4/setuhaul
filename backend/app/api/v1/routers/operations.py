from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import OPS_PORTAL_ROLES, get_db_session, get_request_id, require_roles
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext
from app.services import operations_reads
from app.services.escalation_service import (
    EscalateExceptionCommand,
    escalate_exception,
    get_dock_status,
    get_exception_queue,
    get_pending_confirmations,
    get_queue_status,
    resolve_escalation,
)

router = APIRouter(prefix="/api/v1", tags=["operations"])


class EscalateExceptionBody(EscalateExceptionCommand):
    model_config = ConfigDict(extra="forbid")


class ResolveEscalationBody(BaseModel):
    resolution_note: str | None = "Resolved by Operations"
    status: str = "RESOLVED"


@router.get("/operations/escalation-queue")
async def escalation_queue(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    result = await get_exception_queue(session, ctx, facility_id)
    return ok(result, get_request_id(request))


@router.post("/operations/escalations/{escalation_id}/resolve")
async def resolve_escalation_endpoint(
    escalation_id: str,
    body: ResolveEscalationBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    result = await resolve_escalation(
        session, ctx, escalation_id, resolution_note=body.resolution_note or "Resolved", status=body.status
    )
    return ok(result, get_request_id(request))


@router.get("/operations/dock-status")
async def dock_status(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await get_dock_status(session, ctx, facility_id), get_request_id(request))


@router.get("/operations/queue-status")
async def queue_status(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await get_queue_status(session, ctx, facility_id), get_request_id(request))


@router.get("/operations/pending-confirmations")
async def pending_confirmations(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await get_pending_confirmations(session, ctx, facility_id), get_request_id(request))


@router.post("/operations/escalate")
async def escalate(
    body: EscalateExceptionBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    try:
        result = await escalate_exception(session, ctx, body)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request), message="Escalation queued for operations.")


# E2.2 (issue #22): the five read endpoints below each used to resolve facility scope inline and
# run their own text() SQL. Scope now resolves once in repositories/scope.py and the SQL lives in
# the repository tier; these are pure transport -- authorise, delegate, envelope.


@router.get("/operations/dashboard-summary")
async def dashboard_summary(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await operations_reads.get_dashboard_summary(session, ctx, facility_id), get_request_id(request))


@router.get("/operations/exceptions")
async def list_exceptions(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await operations_reads.list_exceptions(session, ctx, facility_id), get_request_id(request))


@router.get("/operations/appointment-schedule")
async def appointment_schedule(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await operations_reads.get_appointment_schedule(session, ctx, facility_id), get_request_id(request))


@router.get("/operations/dock-snapshot")
async def dock_snapshot(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await operations_reads.get_dock_snapshot(session, ctx, facility_id), get_request_id(request))


@router.get("/operations/facility-constraints")
async def facility_constraints(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    return ok(await operations_reads.get_facility_constraints(session, ctx, facility_id), get_request_id(request))
