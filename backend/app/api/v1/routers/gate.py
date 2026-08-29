"""Gate and yard REST surface (`E3.6`, issue #30, `SOLUTION_DESIGN.md` section 7.5.2).

The five `services/gate_yard_service.py` writes, plus the one
`services/gate_yard_reads.py` read (`GY-G1`, issue #67) that reaches them -- until that read
existed this router had zero `GET` routes, so `UI-UX/04-gate-yard-kiosk/flows-and-states.md`
Flow 1 (the entry point to every other screen on the surface) had no endpoint at all. Thin by the
E2.2 rule: authorise, delegate, envelope -- state-machine enforcement, bind-type handling, match
semantics and the `facility_checkins` write all live in the services, not here.

Role gate: `WAREHOUSE_PLANNER` and `FACILITY_MANAGER` plus `ADMIN`. Section 7.5.2's own "Gate/yard
officer" persona (`SOLUTION_DESIGN.md` line 328, `auth-and-scoping.md` line 200) has no seeded DB
role of its own -- `public.roles` only ever carried the original eight personas plus `CARRIER`
(E2.3) -- so this is an explicit mapping decision (owner-confirmed 2026-08-24, not silently
guessed), not a rediscovery of an existing role. Deliberately narrower than `OPS_PORTAL_ROLES`:
`assert_facility_write_scope` (the service-tier gate) would let any `is_operator` role through, so
this router is what actually narrows "who may work the gate kiosk" to the two chosen personas, the
same role-gate-agrees-with-scope-rule shape `carrier.py` uses.
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
from app.services.gate_yard_reads import MAX_QUERY_LENGTH, search_gate_yard_trucks
from app.services.gate_yard_service import (
    record_dock_in,
    record_gate_in,
    record_gate_out,
    record_unload_start_end,
    update_queue_state,
)

router = APIRouter(prefix="/api/v1/gate", tags=["gate"])

GateCtx = Annotated[
    ExecutionContext,
    Depends(require_roles(RoleName.WAREHOUSE_PLANNER, RoleName.FACILITY_MANAGER, RoleName.ADMIN)),
]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


class GateInBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: datetime | None = None


class QueueStateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_state: str = Field(min_length=1, max_length=40)
    queue_position: int | None = Field(default=None, gt=0)


class DockInBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dock_id: str = Field(min_length=1, max_length=100)
    ts: datetime | None = None


class UnloadPhaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str = Field(pattern="^(START|END)$")
    ts: datetime | None = None


class GateOutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: datetime | None = None


def _require_idempotency_key(idempotency_key: str | None) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    return idempotency_key.strip()


@router.get("/trucks")
async def search_trucks(
    request: Request,
    ctx: GateCtx,
    session: DbSession,
    query: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
) -> dict[str, Any]:
    """`GY-G1` (issue #67) / section 7.5.2, `04-gate-yard-kiosk/flows-and-states.md` Flow 1.

    No `facility_id` parameter, deliberately (`M15`/`NFR-019`): the scope is derived from the
    verified token inside the service. `flows-and-states.md` Flow 8 also makes this the *refresh*
    endpoint -- `edge-cases.md` #3 requires the kiosk to re-fetch a truck's current state after an
    `INVALID_TRANSITION`, and re-searching that shipment id returns exactly that one truck, so no
    separate per-shipment route exists.

    No `try/rollback` wrapper unlike this router's five writes: nothing here opens a transaction to
    roll back.
    """
    result = await search_gate_yard_trucks(session, ctx, query=query)
    return ok(result.model_dump(), get_request_id(request))


@router.post("/shipments/{shipment_id}/gate-in")
async def gate_in(
    shipment_id: str,
    body: GateInBody,
    request: Request,
    ctx: GateCtx,
    session: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """FR-GATE-004 / section 7.5.2 `record_gate_in`. `Idempotency-Key` required by the catalog."""
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await record_gate_in(session, ctx, shipment_id=shipment_id, ts=body.ts, idempotency_key=key)
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request))


@router.post("/shipments/{shipment_id}/queue-state")
async def queue_state(
    shipment_id: str,
    body: QueueStateBody,
    request: Request,
    ctx: GateCtx,
    session: DbSession,
) -> dict[str, Any]:
    """FR-GATE-005 / section 7.5.2 `update_queue_state`. No `Idempotency-Key`: none in the catalog."""
    try:
        result = await update_queue_state(
            session, ctx, shipment_id=shipment_id, queue_state=body.queue_state,
            queue_position=body.queue_position,
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request))


@router.post("/shipments/{shipment_id}/dock-in")
async def dock_in(
    shipment_id: str,
    body: DockInBody,
    request: Request,
    ctx: GateCtx,
    session: DbSession,
) -> dict[str, Any]:
    """FR-GATE-006 / section 7.5.2 `record_dock_in`."""
    try:
        result = await record_dock_in(
            session, ctx, shipment_id=shipment_id, dock_id=body.dock_id, ts=body.ts
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request))


@router.post("/shipments/{shipment_id}/unload")
async def unload_phase(
    shipment_id: str,
    body: UnloadPhaseBody,
    request: Request,
    ctx: GateCtx,
    session: DbSession,
) -> dict[str, Any]:
    """FR-GATE-007 / section 7.5.2 `record_unload_start_end`."""
    try:
        result = await record_unload_start_end(
            session, ctx, shipment_id=shipment_id, phase=body.phase, ts=body.ts
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request))


@router.post("/shipments/{shipment_id}/gate-out")
async def gate_out(
    shipment_id: str,
    body: GateOutBody,
    request: Request,
    ctx: GateCtx,
    session: DbSession,
) -> dict[str, Any]:
    """FR-GATE-008 / section 7.5.2 `record_gate_out`."""
    try:
        result = await record_gate_out(session, ctx, shipment_id=shipment_id, ts=body.ts)
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request))
