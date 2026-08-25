"""Planner dock-blocking REST surface (`E3.6`, issue #30, `SOLUTION_DESIGN.md` section 7.5.1).

`block_dock` / `end_dock_block` / the `get_dock_block_impact` preview -- the three functions
`services/planner_service.py` implements. Thin by the E2.2 rule: authorise, delegate, envelope.

Role gate: `WAREHOUSE_PLANNER` (section 7.5.1's own persona) plus `ADMIN` (the project's existing
write-authorised superset -- see `core/execution_context.py::is_admin`). Deliberately narrower
than `OPS_PORTAL_ROLES`: `assert_facility_write_scope` (the service-tier gate) would let any
`is_operator` role through, so this router is what actually narrows "who may block a dock" to the
persona section 7.5.1 names, the same role-gate-agrees-with-scope-rule shape `carrier.py` uses.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_request_id, require_roles
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services.planner_service import block_dock, end_dock_block, get_dock_block_impact

router = APIRouter(prefix="/api/v1/planner", tags=["planner"])

PlannerCtx = Annotated[ExecutionContext, Depends(require_roles(RoleName.WAREHOUSE_PLANNER, RoleName.ADMIN))]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


class BlockDockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_start: datetime
    window_end: datetime
    reason: str = Field(min_length=1, max_length=500)


def _require_idempotency_key(idempotency_key: str | None) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    return idempotency_key.strip()


@router.get("/docks/{dock_id}/block-impact")
async def dock_block_impact(
    dock_id: str,
    request: Request,
    ctx: PlannerCtx,
    session: DbSession,
    window_start: Annotated[datetime, Query()],
    window_end: Annotated[datetime, Query()],
) -> dict[str, Any]:
    """Preview -- names affected appointments before the planner commits (FR-PLN-007).

    Not in section 7.5.1's own catalog; flagged as an addition, not silently folded in, per the
    same discipline `services/planner_service.py::get_dock_block_impact`'s own docstring uses.
    """
    result = await get_dock_block_impact(
        session, ctx, dock_id=dock_id, window_start=window_start, window_end=window_end
    )
    return ok(result.model_dump(), get_request_id(request))


@router.post("/docks/{dock_id}/block")
async def block_dock_route(
    dock_id: str,
    body: BlockDockBody,
    request: Request,
    ctx: PlannerCtx,
    session: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """FR-PLN-007 / section 7.5.1 `block_dock`. `Idempotency-Key` is required by the catalog."""
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await block_dock(
            session,
            ctx,
            dock_id=dock_id,
            window_start=body.window_start,
            window_end=body.window_end,
            reason=body.reason,
            idempotency_key=key,
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    message = (
        "Dock blocked; affected appointments named in the response."
        if result.code == "BLOCKED"
        else "Window already overlaps an existing block."
    )
    return ok(result.model_dump(), get_request_id(request), message=message)


@router.post("/dock-status-events/{dock_status_event_id}/end")
async def end_dock_block_route(
    dock_status_event_id: str,
    request: Request,
    ctx: PlannerCtx,
    session: DbSession,
) -> dict[str, Any]:
    """FR-PLN-008 / section 7.5.1 `end_dock_block`. No `Idempotency-Key`: the catalog names none."""
    try:
        result = await end_dock_block(session, ctx, dock_status_event_id=dock_status_event_id)
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request))
