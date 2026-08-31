"""Gate and yard REST surface (`E3.6`, issue #30, `SOLUTION_DESIGN.md` section 7.5.2).

The five `services/gate_yard_service.py` writes, plus the one
`services/gate_yard_reads.py` read (`GY-G1`, issue #67) that reaches them -- until that read
existed this router had zero `GET` routes, so `UI-UX/04-gate-yard-kiosk/flows-and-states.md`
Flow 1 (the entry point to every other screen on the surface) had no endpoint at all. Thin by the
E2.2 rule: authorise, delegate, envelope -- state-machine enforcement, bind-type handling, match
semantics and the `facility_checkins` write all live in the services, not here.

Role gate: `GATE_OFFICER`, `WAREHOUSE_PLANNER`, `FACILITY_MANAGER`, `ADMIN`.

**`GATE_OFFICER` added 2026-08-29 (issue #79, owner-approved), superseding the 2026-08-24 mapping
decision that ran this kiosk under a planner/facility-manager login.** That mapping was made
because `public.roles` carried only the original eight personas plus `CARRIER` (E2.3) and the
design's own gate persona had no row -- a real constraint at the time, not a guess. It is now
resolved the other way, on three pieces of evidence the mapping could not satisfy:

1. `SOLUTION_DESIGN.md` section 2 lists "Gate / yard officer" as an in-v1 persona with its own
   surface and its own table (`facility_checkins`); section 7.5.2 gives it five tools of its own.
   The persona was always in the design; only the DB row was missing.
2. `UI-UX/00-foundations/auth-and-scoping.md` gives the role a landing row ("Yard queue for the
   device's facility") **and** a "never sees" row: *"Scheduling controls. Anything beyond the
   current facility's yard."* A `WAREHOUSE_PLANNER` credential cannot honour that -- it carries
   `planner.py`'s dock-block/schedule-apply authority and `OPS_PORTAL_ROLES`' appointment
   confirm/reject. The borrowed identity was strictly wider than the persona it stood in for.
3. That over-grant sat on the one session in the product with **no idle timeout at all**
   (`auth-and-scoping.md` "Session expiry": the gate kiosk is device-bound and "signs out only on
   explicit action or shift change"), on a shared device at a physical gate. Least privilege --
   "assigning users only the minimum privileges necessary to complete their job", OWASP
   *Authorization Cheat Sheet* (cheatsheetseries.owasp.org, read 2026-08-29) -- matters most
   exactly there, and that cheat sheet's own note that permissions are far easier to grant than
   to revoke is why this was worth fixing before any kiosk account was provisioned.

`GATE_OFFICER` is therefore **not** in `OPS_PORTAL_ROLES` and **not** in `is_operator`; its only
write reach is `repositories.scope.assert_gate_write_scope`, its own facility. U111's shared-shift
model is unaffected -- it governs which *human* is stamped on a write within a device session
(issue #68, closed 2026-08-31 and described below), not which role the *device* authenticates as;
`auth-and-scoping.md` says as much when it notes the facility is "the *device's*, not the user's".

The two ops roles stay for continuity: this router still narrows "who may work the gate kiosk"
below `OPS_PORTAL_ROLES`, the same role-gate-agrees-with-scope-rule shape `carrier.py` uses.

**Two identities, one request (issue #68, 2026-08-31).** Because the principal above is now a
*device* account, every write body carries an optional `officer_name` -- U111's shift label for the
human standing at the kiosk. The two must not be conflated and are deliberately kept apart at every
layer: the device is authenticated and authorises the write; the human is a self-declared,
unverified string that authorises nothing and is recorded as an attribute of the event. See
`OfficerAttributedBody` below and `gate_yard_service.OFFICER_ATTRIBUTION_KEY`.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import GATE_KIOSK_ROLES, get_db_session, get_request_id, require_roles
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
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
    Depends(require_roles(*GATE_KIOSK_ROLES)),
]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


class OfficerAttributedBody(BaseModel):
    """Base for all five section 7.5.2 writes: U111's shift label, carried on every event.

    **What this field is.** `04-gate-yard-kiosk/components.md` section 1 and `flows-and-states.md`
    Flow 0: the officer types their name once per shift and it is stamped on every event that shift
    -- "an attribute of the write, not as a re-asked credential" (FR-GATE-001; issue #68 was this
    field's total absence).

    **What this field is NOT: a credential, an identity or an authorisation input.** It is free text
    somebody typed at a shared booth and no part of the system verifies it. Authorisation on every
    route below is `require_roles(*GATE_KIOSK_ROLES)` plus, inside the service,
    `assert_gate_write_scope` against the *verified* token -- and neither consults this value. It is
    intentionally in the body, alongside `dock_id` and `ts`, and **not** in a header: a header would
    sit it next to `Authorization` and `Idempotency-Key`, where a later reader could reasonably take
    it for part of the request's identity or its replay key. It is neither. It is data being
    recorded, and it is shaped like data being recorded.

    **No length or format constraint, deliberately.** The same label is replayed on every write of a
    whole shift, so any rule that could reject it would not lose one arrival -- it would lose the
    shift's. `gate_yard_service.normalise_officer_name` is the single authority and it sanitises and
    truncates rather than refusing. That is a considered divergence from `dock_id`'s `max_length`
    below: a wrong `dock_id` must stop the write, a wrong label must never.

    **Optional.** A kiosk mid-shift-change, or reloaded before Flow 0, sends nothing here and the
    event still records, attributed to nobody. See `OFFICER_ATTRIBUTION_KEY` in the service for why
    there is no fallback to the device account's name.
    """

    model_config = ConfigDict(extra="forbid")

    officer_name: str | None = None


class GateInBody(OfficerAttributedBody):
    ts: datetime | None = None


class QueueStateBody(OfficerAttributedBody):
    queue_state: str = Field(min_length=1, max_length=40)
    queue_position: int | None = Field(default=None, gt=0)


class DockInBody(OfficerAttributedBody):
    dock_id: str = Field(min_length=1, max_length=100)
    ts: datetime | None = None


class UnloadPhaseBody(OfficerAttributedBody):
    phase: str = Field(pattern="^(START|END)$")
    ts: datetime | None = None


class GateOutBody(OfficerAttributedBody):
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
    """FR-GATE-004 / section 7.5.2 `record_gate_in`. `Idempotency-Key` required by the catalog.

    `body.officer_name` is FR-GATE-001's shift label, not an identity -- see `OfficerAttributedBody`.
    """
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await record_gate_in(
            session, ctx, shipment_id=shipment_id, ts=body.ts, idempotency_key=key,
            officer_name=body.officer_name,
        )
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
            queue_position=body.queue_position, officer_name=body.officer_name,
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
            session, ctx, shipment_id=shipment_id, dock_id=body.dock_id, ts=body.ts,
            officer_name=body.officer_name,
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
            session, ctx, shipment_id=shipment_id, phase=body.phase, ts=body.ts,
            officer_name=body.officer_name,
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
        result = await record_gate_out(
            session, ctx, shipment_id=shipment_id, ts=body.ts, officer_name=body.officer_name
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request))
