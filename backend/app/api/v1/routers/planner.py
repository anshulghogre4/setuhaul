"""Planner console REST surface (`E3.6`/issue #30, issue #60, `SOLUTION_DESIGN.md` section 7.5.1).

`get_planner_queue` plus `block_dock` / `end_dock_block` / the `get_dock_block_impact` preview --
the functions `services/planner_service.py` implements. Thin by the E2.2 rule: authorise,
delegate, envelope.

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
from app.services.planner_service import (
    BOARD_HORIZON_HOURS,
    DEFAULT_QUEUE_LIMIT,
    MAX_QUEUE_LIMIT,
    block_dock,
    end_dock_block,
    get_dock_block_impact,
    get_dock_board,
    get_planner_queue,
)

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


@router.get("/queue")
async def planner_queue(
    request: Request,
    ctx: PlannerCtx,
    session: DbSession,
    facility_id: Annotated[str | None, Query()] = None,
    horizon_hours: Annotated[int | None, Query(ge=1, le=168)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_QUEUE_LIMIT)] = DEFAULT_QUEUE_LIMIT,
) -> dict[str, Any]:
    """FR-PLN-010 / section 7.5.1 `get_planner_queue` -- the seven-field row of section 7.3.

    `facility_id` is accepted but never trusted: the service passes it through
    `repositories.scope.resolve_facility_scope`, so it can only narrow a global-read persona's
    view or match an operator's own facility (M15/`NFR-019`). It exists because an `ADMIN` (the
    other role this router admits) holds global read scope and therefore has to name which
    facility's queue they want.
    """
    result = await get_planner_queue(
        session, ctx, facility_id=facility_id, horizon_hours=horizon_hours, limit=limit
    )
    return ok(result.model_dump(), get_request_id(request))


@router.get("/board")
async def planner_board(
    request: Request,
    ctx: PlannerCtx,
    session: DbSession,
    facility_id: Annotated[str | None, Query()] = None,
    horizon_hours: Annotated[int | None, Query(ge=1, le=BOARD_HORIZON_HOURS)] = None,
) -> dict[str, Any]:
    """The Board tab's at-rest occupancy view (`03-planner-dock-board/screens.md` section 3).

    Same scope contract as `/queue` above: `facility_id` is accepted, passed through
    `repositories.scope.resolve_facility_scope`, and can only narrow a global-read persona or match
    an operator's own facility (M15/`NFR-019`).

    `horizon_hours` is bounded at `BOARD_HORIZON_HOURS` by the query validator rather than only in
    the service, so a wider value is a 422 at the boundary instead of being silently clamped. The
    axis is *"four hours, or until closing time, whichever comes sooner"* by design, and a caller
    who could widen it would be reading a different board from the one the design specifies.
    """
    result = await get_dock_board(
        session, ctx, facility_id=facility_id, horizon_hours=horizon_hours
    )
    return ok(result.model_dump(), get_request_id(request))


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
