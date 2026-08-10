from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_execution_context, get_request_id
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext
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

