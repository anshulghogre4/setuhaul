from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    OPS_PORTAL_ROLES,
    get_db_session,
    get_request_id,
    get_settings_dep,
    require_roles,
)
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import Settings
from app.services import operations_reads
from app.services.escalation_service import (
    EscalateExceptionCommand,
    acknowledge_escalation,
    cancel_escalation,
    escalate_exception,
    get_dock_status,
    get_exception_queue,
    get_pending_confirmations,
    get_queue_status,
    hand_back_thread,
    reassign_escalation,
    resolve_escalation,
    start_escalation_work,
    take_over_thread,
)
from app.services.ops_copilot import get_resolution_suggestion
from app.services.thread_message_service import post_operations_message

router = APIRouter(prefix="/api/v1", tags=["operations"])


class EscalateExceptionBody(EscalateExceptionCommand):
    model_config = ConfigDict(extra="forbid")


class ResolveEscalationBody(BaseModel):
    resolution_note: str | None = "Resolved by Operations"
    reason_code: str = "ISSUE_FIXED"


class CancelEscalationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(min_length=1, max_length=40)
    resolution_note: str | None = None


class ReassignEscalationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_owner_id: str = Field(min_length=1, max_length=100)


class TakeOverThreadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    escalation_id: str = Field(min_length=1, max_length=100)


class PostOperationsMessageBody(BaseModel):
    """Issue #55's request body. Deliberately carries **no** sender, driver, or facility field.

    The sender is the verified token's `user_id`, the driver comes from the thread, and the
    facility comes from the thread's shipment -- all resolved server-side (M15/NFR-019).
    `extra="forbid"` means a client that tries to add one gets a 422, not a silently ignored field.
    """

    model_config = ConfigDict(extra="forbid")

    message_text: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=128)


def _require_idempotency_key(idempotency_key: str | None) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    return idempotency_key.strip()


@router.get("/operations/escalation-queue")
async def escalation_queue(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
    owner: Annotated[str, Query()] = "all",
) -> dict[str, Any]:
    result = await get_exception_queue(session, ctx, facility_id, owner)
    return ok(result, get_request_id(request))


@router.post("/operations/escalations/{escalation_id}/resolve")
async def resolve_escalation_endpoint(
    escalation_id: str,
    body: ResolveEscalationBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        result = await resolve_escalation(
            session, ctx, escalation_id, resolution_note=body.resolution_note or "Resolved",
            reason_code=body.reason_code, idempotency_key=idempotency_key,
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/operations/escalations/{escalation_id}/cancel")
async def cancel_escalation_endpoint(
    escalation_id: str,
    body: CancelEscalationBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await cancel_escalation(
            session, ctx, escalation_id, reason_code=body.reason_code,
            resolution_note=body.resolution_note, idempotency_key=key,
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/operations/escalations/{escalation_id}/acknowledge")
async def acknowledge_escalation_endpoint(
    escalation_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await acknowledge_escalation(session, ctx, escalation_id, key)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/operations/escalations/{escalation_id}/reassign")
async def reassign_escalation_endpoint(
    escalation_id: str,
    body: ReassignEscalationBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    try:
        result = await reassign_escalation(session, ctx, escalation_id, body.new_owner_id)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/operations/escalations/{escalation_id}/start")
async def start_escalation_work_endpoint(
    escalation_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Issue #56: advance an acknowledged escalation to `IN_PROGRESS` (the middle stepper dot)."""
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await start_escalation_work(session, ctx, escalation_id, key)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.get("/operations/escalations/{escalation_id}/suggestion")
async def escalation_suggestion(
    escalation_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Issue #57: the co-pilot's resolution-action suggestion.

    A `GET`, and that is the whole safety story rather than a REST nicety: this path writes
    nothing, calls no tool, and composes no driver-facing text -- it returns the name of a tool the
    coordinator may choose to press, plus the facts that point at it. `AGENTS.md`'s "the LLM
    orchestrates typed tools and never directly mutates business tables" is satisfied structurally
    here, not by convention.

    No `Idempotency-Key` header, deliberately (§7.5 principle 3 attaches keys to capacity-consuming
    writes); no `facility_id` query parameter, deliberately (the facility is derived from the
    escalation's own row -- M15/NFR-019). See `services/ops_copilot.py`.
    """
    return ok(
        await get_resolution_suggestion(session, ctx, escalation_id), get_request_id(request)
    )


@router.post("/operations/threads/{thread_id}/take-over")
async def take_over_thread_endpoint(
    thread_id: str,
    body: TakeOverThreadBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await take_over_thread(
            session, ctx, thread_id, body.escalation_id, key, settings=settings
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/operations/threads/{thread_id}/hand-back")
async def hand_back_thread_endpoint(
    thread_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict[str, Any]:
    try:
        result = await hand_back_thread(session, ctx, thread_id, settings=settings)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.get("/operations/threads/{thread_id}/messages")
async def thread_messages(
    thread_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """The ops-side read of a thread's durable transcript (`chat_messages`).

    `chat.py`'s `/chat/history` is DRIVER-only and Redis-backed, so before this the console had no
    way to read the conversation it was about to take over.
    """
    return ok(
        await operations_reads.get_thread_messages(session, ctx, thread_id),
        get_request_id(request),
    )


@router.post("/operations/threads/{thread_id}/messages")
async def post_thread_message(
    thread_id: str,
    body: PostOperationsMessageBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Issue #55: the coordinator reply path. The one thing the takeover composer exists to do."""
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await post_operations_message(
            session, ctx, thread_id=thread_id, message_text=body.message_text,
            idempotency_key=key, client_message_id=body.client_message_id, settings=settings,
        )
    except Exception:
        await session.rollback()
        raise
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
