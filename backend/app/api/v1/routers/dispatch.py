from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import OPS_PORTAL_ROLES, get_db_session, get_execution_context, get_request_id, require_roles
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext
from app.services.dispatch_service import (
    CreateDispatchShipmentCommand,
    create_dispatch_shipment,
    list_dispatch_drivers,
    list_dispatch_facilities,
)

router = APIRouter(prefix="/api/v1/dispatch", tags=["dispatch"])


@router.get("/drivers")
async def dispatch_drivers(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    available_only: Annotated[bool, Query()] = True,
) -> dict[str, Any]:
    drivers = await list_dispatch_drivers(session, available_only=available_only)
    return ok(
        {"drivers": drivers, "filter": "available_unassigned_only" if available_only else "all"},
        get_request_id(request),
    )


@router.get("/facilities")
async def dispatch_facilities(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    facilities = await list_dispatch_facilities(session)
    return ok({"facilities": facilities}, get_request_id(request))


@router.post("/shipments")
async def dispatch_create_shipment(
    cmd: CreateDispatchShipmentCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    result = await create_dispatch_shipment(session, ctx, cmd)
    return ok(result, get_request_id(request))
