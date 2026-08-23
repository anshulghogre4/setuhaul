from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_request_id, require_roles
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext, RoleName
from app.services.driver_reads import get_driver_context_payload

router = APIRouter(prefix="/api/v1", tags=["driver"])


@router.get("/driver/context")
async def driver_context(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    return ok(await get_driver_context_payload(session, ctx), get_request_id(request))
