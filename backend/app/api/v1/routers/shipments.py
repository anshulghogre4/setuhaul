from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_execution_context, get_request_id, require_roles
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services.driver_reads import get_current_appointment, get_shipment_details
from app.services.eta_service import EtaUpdateCommand, record_eta_update

router = APIRouter(prefix="/api/v1", tags=["shipments"])


@router.get("/shipments/{shipment_id}")
async def get_shipment(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    # E2.2: this endpoint previously re-implemented get_shipment_details' query *and* its scope
    # check verbatim. The two produced an identical payload, so the duplicate was deleted rather
    # than merely re-pointed at the shared scope helper.
    return ok(await get_shipment_details(session, ctx, shipment_id), get_request_id(request))


@router.get("/shipments/{shipment_id}/appointment/current")
async def current_appointment(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    return ok(await get_current_appointment(session, ctx, shipment_id), get_request_id(request))


@router.post("/shipments/{shipment_id}/eta-updates")
async def create_eta_update(
    shipment_id: str,
    body: EtaUpdateCommand,
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
        result = await record_eta_update(
            session,
            ctx=ctx,
            shipment_id=shipment_id,
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
        "Confirmation required before write."
        if result.get("status") == "CONFIRMATION_REQUIRED"
        else "ETA update persisted."
    )
    return ok(result, get_request_id(request), message=message)
