"""Carrier portal REST surface (`E3.3`, issue #27, `SOLUTION_DESIGN.md` §7.5.6).

Five GETs and nothing else. §7.5.6's "**No mutating tool exists here by design**" is enforced
structurally by this file containing no POST/PATCH/DELETE route -- a carrier manager who needs to
act does so through the conversation/control planes that already own that action.

Thin by the E2.2 rule: authorise, delegate, envelope. No scope resolution, no SQL, no business
rule lives here -- `services/carrier_reads.py` resolves scope through `repositories/scope.py` and
`repositories/carrier.py` holds the queries.

Note what is *absent* from every signature below: there is no `carrier_id` path parameter, query
parameter or body field on any of these endpoints. That is `M15`/§7.5.6's "scope-derived from the
caller's own `carrier_id`, never accepted as an argument" made unforgeable at the transport layer
-- there is no wire format in which a client can express a carrier other than its own.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_request_id, require_roles
from app.core.envelope import ok
from app.core.execution_context import CARRIER_PORTAL_ROLES, ExecutionContext
from app.services import carrier_reads

router = APIRouter(prefix="/api/v1", tags=["carrier"])

# The carrier-portal roles, and nothing else -- still deliberately not "the global-read personas".
#
# **Issue #101 (owner decision (a), 2026-09-01).** This was `RoleName.CARRIER` alone, and the note
# that used to sit here ("adding TRANSPORT_MANAGER would produce a 403 from the service tier
# anyway") was correct about the mechanism and wrong about the consequence: *no user holds the
# CARRIER role*, so the gate refused every real account and the surface had no working identity at
# all. `CARRIER_PORTAL_ROLES` (core/execution_context.py) carries the full argument, including why
# this is not a scope widening -- the reach still comes from a per-user
# `user_scopes(scope_type='CARRIER')` row, never from the role name, and a TRANSPORT_MANAGER
# without one is refused with `CARRIER_UNMAPPED` rather than served the whole fleet table.
#
# The role gate and the scope rule still agree; what changed is which roles the scope rule can
# admit, not whether it is enforced. ADMIN and REGIONAL_OPERATIONS_HEAD are deliberately still out.
CarrierCtx = Annotated[
    ExecutionContext, Depends(require_roles(*sorted(CARRIER_PORTAL_ROLES)))
]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/carrier/fleet-overview")
async def fleet_overview(
    request: Request,
    ctx: CarrierCtx,
    session: DbSession,
) -> dict[str, Any]:
    """§7.5.6 `get_fleet_overview` (`FR-CAR-001`)."""
    return ok(await carrier_reads.get_fleet_overview(session, ctx), get_request_id(request))


@router.get("/carrier/shipments")
async def fleet_shipments(
    request: Request,
    ctx: CarrierCtx,
    session: DbSession,
    status_filter: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """§7.5.6 `list_fleet_shipments` (`FR-CAR-001`, `FR-CAR-002`).

    `status_filter` narrows list membership only; it is not a scope control and cannot widen what
    this carrier sees.
    """
    return ok(
        await carrier_reads.list_fleet_shipments(session, ctx, status_filter),
        get_request_id(request),
    )


@router.get("/carrier/shipments/{shipment_id}")
async def shipment_detail(
    shipment_id: str,
    request: Request,
    ctx: CarrierCtx,
    session: DbSession,
) -> dict[str, Any]:
    """§7.5.6 `get_shipment_detail` (`FR-CAR-003`, `FR-CAR-004`).

    Refuses a cross-carrier id with 403 rather than returning an empty payload, and refuses an
    unknown id identically so the response cannot be used to probe for existence
    (`UI-UX/05-carrier-portal/edge-cases.md` #1).
    """
    return ok(
        await carrier_reads.get_shipment_detail(session, ctx, shipment_id),
        get_request_id(request),
    )


@router.get("/carrier/exceptions")
async def fleet_exceptions(
    request: Request,
    ctx: CarrierCtx,
    session: DbSession,
) -> dict[str, Any]:
    """§7.5.6 `list_fleet_exceptions` (`FR-CAR-001`)."""
    return ok(await carrier_reads.list_fleet_exceptions(session, ctx), get_request_id(request))


@router.get("/carrier/on-time-performance")
async def on_time_performance(
    request: Request,
    ctx: CarrierCtx,
    session: DbSession,
    window: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """§7.5.6 `get_carrier_on_time_performance` (`FR-CAR-001`)."""
    return ok(
        await carrier_reads.get_carrier_on_time_performance(session, ctx, window),
        get_request_id(request),
    )
