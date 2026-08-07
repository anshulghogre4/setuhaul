from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_request_id, require_roles
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName

router = APIRouter(prefix="/api/v1", tags=["operations"])


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_facility(ctx: ExecutionContext, facility_id: str | None) -> str | None:
    if ctx.is_admin:
        return facility_id
    if not ctx.facility_id:
        raise AppError("Operator facility scope missing.", code="SCOPE_MISSING", status_code=403)
    if facility_id and facility_id != ctx.facility_id:
        raise AppError("Cross-facility access denied.", code="FORBIDDEN", status_code=403)
    return ctx.facility_id


@router.get("/operations/dashboard-summary")
async def dashboard_summary(
    request: Request,
    ctx: Annotated[
        ExecutionContext,
        Depends(require_roles(RoleName.OPERATIONS_EXECUTIVE, RoleName.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    scope_facility = _resolve_facility(ctx, facility_id)
    params: dict[str, Any] = {}
    facility_filter = ""
    if scope_facility:
        facility_filter = "AND s.destination_facility_id = :facility_id"
        params["facility_id"] = scope_facility

    shipment_counts = (
        await session.execute(
            text(
                f"""
                SELECT current_status, count(*)::int AS n
                FROM public.shipments s
                WHERE 1=1 {facility_filter}
                GROUP BY current_status
                """
            ),
            params,
        )
    ).mappings().all()

    exception_params = dict(params)
    exception_join = ""
    if scope_facility:
        exception_join = (
            "JOIN public.shipments s ON s.shipment_id = e.shipment_id "
            "AND s.destination_facility_id = :facility_id"
        )

    open_exceptions = (
        await session.execute(
            text(
                f"""
                SELECT count(*)::int AS n
                FROM public.driver_exceptions e
                {exception_join}
                WHERE e.exception_status NOT IN ('CLOSED', 'RESOLVED')
                """
            ),
            exception_params,
        )
    ).scalar_one()

    data = {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": {
            "type": "global" if scope_facility is None and ctx.is_admin else "facility",
            "facility_id": scope_facility,
            "read_only": True,
        },
        "shipments_by_status": {row["current_status"]: row["n"] for row in shipment_counts},
        "open_exceptions": open_exceptions,
        "freshness": "live",
        "note": "Observational summary only; no scheduling mutations in Sprint 1.",
    }
    return ok(data, get_request_id(request))


@router.get("/operations/exceptions")
async def list_exceptions(
    request: Request,
    ctx: Annotated[
        ExecutionContext,
        Depends(require_roles(RoleName.OPERATIONS_EXECUTIVE, RoleName.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    scope_facility = _resolve_facility(ctx, facility_id)
    params: dict[str, Any] = {}
    join = "LEFT JOIN public.shipments s ON s.shipment_id = e.shipment_id"
    where = ""
    if scope_facility:
        where = "WHERE s.destination_facility_id = :facility_id"
        params["facility_id"] = scope_facility

    rows = (
        await session.execute(
            text(
                f"""
                SELECT e.exception_id, e.driver_id, e.shipment_id, s.destination_facility_id AS facility_id,
                       e.exception_type, e.exception_status, e.severity_code, e.description,
                       e.reported_at, e.declared_eta_ts, e.dedupe_key
                FROM public.driver_exceptions e
                {join}
                {where}
                ORDER BY e.reported_at DESC NULLS LAST
                LIMIT 100
                """
            ),
            params,
        )
    ).mappings().all()

    return ok(
        {
            "as_of": _as_of(),
            "source": "postgresql",
            "scope": {"facility_id": scope_facility, "read_only": True},
            "items": [dict(r) for r in rows],
            "freshness": "live",
        },
        get_request_id(request),
    )


@router.get("/operations/appointment-schedule")
async def appointment_schedule(
    request: Request,
    ctx: Annotated[
        ExecutionContext,
        Depends(require_roles(RoleName.OPERATIONS_EXECUTIVE, RoleName.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    scope_facility = _resolve_facility(ctx, facility_id)
    params: dict[str, Any] = {}
    where = ""
    if scope_facility:
        where = "WHERE sl.facility_id = :facility_id"
        params["facility_id"] = scope_facility

    rows = (
        await session.execute(
            text(
                f"""
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.is_current, a.booked_at, a.confirmed_at, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts, sl.slot_status
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                {where}
                ORDER BY sl.slot_start_ts NULLS LAST
                LIMIT 200
                """
            ),
            params,
        )
    ).mappings().all()

    return ok(
        {
            "as_of": _as_of(),
            "source": "postgresql",
            "scope": {"facility_id": scope_facility, "read_only": True},
            "items": [dict(r) for r in rows],
            "freshness": "live",
            "label": "displayed_schedule_not_reserved",
        },
        get_request_id(request),
    )


@router.get("/operations/dock-snapshot")
async def dock_snapshot(
    request: Request,
    ctx: Annotated[
        ExecutionContext,
        Depends(require_roles(RoleName.OPERATIONS_EXECUTIVE, RoleName.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    scope_facility = _resolve_facility(ctx, facility_id)
    params: dict[str, Any] = {}
    where = ""
    if scope_facility:
        where = "WHERE d.facility_id = :facility_id"
        params["facility_id"] = scope_facility

    docks = (
        await session.execute(
            text(
                f"""
                SELECT d.dock_id, d.facility_id, d.dock_code, d.dock_type,
                       d.supports_refrigerated, d.max_vehicle_weight_kg, d.dock_status
                FROM public.docks d
                {where}
                ORDER BY d.dock_id
                """
            ),
            params,
        )
    ).mappings().all()

    slot_where = "WHERE s.facility_id = :facility_id" if scope_facility else ""
    slots = (
        await session.execute(
            text(
                f"""
                SELECT s.slot_id, s.facility_id, s.dock_id, s.slot_start_ts, s.slot_end_ts,
                       s.slot_status, s.block_reason, s.created_at
                FROM public.appointment_slots s
                {slot_where}
                ORDER BY s.slot_start_ts
                LIMIT 200
                """
            ),
            params,
        )
    ).mappings().all()

    return ok(
        {
            "as_of": _as_of(),
            "source": "postgresql",
            "scope": {"facility_id": scope_facility, "read_only": True},
            "docks": [dict(r) for r in docks],
            "slots": [dict(r) for r in slots],
            "freshness": "live",
            "note": "Operational snapshot only; not bookable capacity.",
        },
        get_request_id(request),
    )


@router.get("/operations/facility-constraints")
async def facility_constraints(
    request: Request,
    ctx: Annotated[
        ExecutionContext,
        Depends(require_roles(RoleName.OPERATIONS_EXECUTIVE, RoleName.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    scope_facility = _resolve_facility(ctx, facility_id)
    params: dict[str, Any] = {}
    where = ""
    if scope_facility:
        where = "WHERE fr.facility_id = :facility_id"
        params["facility_id"] = scope_facility

    rules = (
        await session.execute(
            text(
                f"""
                SELECT fr.rule_id, fr.facility_id, fr.rule_type, fr.rule_value, fr.description,
                       fr.effective_from, fr.effective_to, fr.active_flag
                FROM public.facility_rules fr
                {where}
                ORDER BY fr.facility_id, fr.rule_id
                """
            ),
            params,
        )
    ).mappings().all()

    facilities = (
        await session.execute(
            text(
                f"""
                SELECT facility_id, facility_name, city, state, timezone, open_time, close_time,
                       checkin_grace_min, default_unload_min, active_flag
                FROM public.facilities
                {"WHERE facility_id = :facility_id" if scope_facility else ""}
                """
            ),
            params,
        )
    ).mappings().all()

    return ok(
        {
            "as_of": _as_of(),
            "source": "postgresql",
            "scope": {"facility_id": scope_facility, "read_only": True},
            "facilities": [dict(r) for r in facilities],
            "rules": [dict(r) for r in rules],
            "freshness": "live",
        },
        get_request_id(request),
    )
