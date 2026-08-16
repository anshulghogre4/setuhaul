from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.services.ids import new_id

ESCALATION_TYPES = frozenset(
    {"NO_SLOT", "CONTRADICTORY", "APPROVAL_REQUIRED", "REGULATED", "EMERGENCY", "WAREHOUSE_REPLY_CONFLICT"}
)


class EscalateExceptionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(min_length=1, max_length=100)
    escalation_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    severity_code: str = Field(default="HIGH", max_length=30)
    policy_version: str | None = Field(default=None, max_length=100)
    recommendation_id: str | None = Field(default=None, max_length=100)


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_ops_scope(ctx: ExecutionContext, facility_id: str) -> None:
    if ctx.is_admin or (ctx.is_operator and ctx.facility_id == facility_id):
        return
    raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)


async def _shipment_scope(session: AsyncSession, shipment_id: str) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, destination_facility_id AS facility_id, driver_id
                FROM public.shipments WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    return dict(row)


async def escalate_exception(
    session: AsyncSession, ctx: ExecutionContext, command: EscalateExceptionCommand
) -> dict[str, Any]:
    escalation_type = command.escalation_type.upper()
    if escalation_type not in ESCALATION_TYPES:
        raise AppError("Unsupported escalation type.", code="INVALID_ESCALATION_TYPE", status_code=422)
    shipment = await _shipment_scope(session, command.shipment_id)
    if ctx.is_driver:
        if shipment["driver_id"] != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    else:
        _assert_ops_scope(ctx, str(shipment["facility_id"]))

    now = _as_of()
    day = now[:10]
    dedupe_key = f"{command.shipment_id}:{day}:{escalation_type}"
    escalation_id = new_id("ESC")
    row = (
        await session.execute(
            text(
                """
                INSERT INTO public.escalation_queue (
                  escalation_id, shipment_id, facility_id, driver_id, escalation_type,
                  escalation_status, severity_code, policy_version, recommendation_id,
                  payload_json, dedupe_key, created_at, updated_at, resolved_at, resolved_by_user_id
                ) VALUES (
                  :escalation_id, :shipment_id, :facility_id, :driver_id, :escalation_type,
                  'OPEN', :severity_code, :policy_version, :recommendation_id,
                  :payload_json, :dedupe_key, :created_at, :updated_at, NULL, NULL
                )
                ON CONFLICT (dedupe_key) DO UPDATE
                SET payload_json = EXCLUDED.payload_json,
                    severity_code = EXCLUDED.severity_code,
                    policy_version = EXCLUDED.policy_version,
                    recommendation_id = EXCLUDED.recommendation_id,
                    updated_at = EXCLUDED.updated_at
                RETURNING escalation_id, shipment_id, facility_id, driver_id, escalation_type,
                          escalation_status, severity_code, policy_version, recommendation_id,
                          payload_json, dedupe_key, created_at, updated_at
                """
            ),
            {
                "escalation_id": escalation_id,
                "shipment_id": command.shipment_id,
                "facility_id": shipment["facility_id"],
                "driver_id": shipment["driver_id"],
                "escalation_type": escalation_type,
                "severity_code": command.severity_code,
                "policy_version": command.policy_version,
                "recommendation_id": command.recommendation_id,
                "payload_json": json.dumps(command.payload, default=str),
                "dedupe_key": dedupe_key,
                "created_at": now,
                "updated_at": now,
            },
        )
    ).mappings().one()
    await session.commit()
    data = dict(row)
    data["payload"] = json.loads(data.pop("payload_json"))
    return data


async def persist_noslot_escalation(
    session: AsyncSession,
    *,
    ctx: ExecutionContext,
    shipment_id: str,
    facility_id: str,
    driver_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    # Facility/driver fields are independently verified inside escalate_exception.
    del facility_id, driver_id
    return await escalate_exception(
        session,
        ctx,
        EscalateExceptionCommand(
            shipment_id=shipment_id,
            escalation_type="NO_SLOT",
            payload=payload,
            policy_version=payload.get("policy_version"),
            recommendation_id=payload.get("recommendation_id"),
        ),
    )


async def get_exception_queue(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None = None
) -> dict[str, Any]:
    scope = facility_id if ctx.is_admin else ctx.facility_id
    if not ctx.is_admin:
        if not scope or (facility_id and facility_id != scope):
            raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    params: dict[str, Any] = {}
    facility_filter = ""
    if scope:
        facility_filter = "AND facility_id = :facility_id"
        params["facility_id"] = scope
    rows = (
        await session.execute(
            text(
                f"""
                SELECT escalation_id, shipment_id, facility_id, driver_id, escalation_type,
                       escalation_status, severity_code, policy_version, recommendation_id,
                       payload_json, created_at, updated_at
                FROM public.escalation_queue
                WHERE escalation_status IN ('OPEN', 'IN_PROGRESS')
                  {facility_filter}
                ORDER BY created_at DESC
                LIMIT 100
                """
            ),
            params,
        )
    ).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        items.append(item)
    return {"as_of": _as_of(), "source": "postgresql", "facility_id": scope, "items": items}


async def resolve_escalation(
    session: AsyncSession,
    ctx: ExecutionContext,
    escalation_id: str,
    resolution_note: str = "Resolved by Operations",
    status: str = "RESOLVED",
) -> dict[str, Any]:
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to resolve escalations.", code="FORBIDDEN", status_code=403)

    now_iso = datetime.now(timezone.utc).isoformat()
    row = (
        await session.execute(
            text(
                """
                UPDATE public.escalation_queue
                SET escalation_status = :status,
                    updated_at = :now_iso,
                    resolved_at = :now_iso,
                    resolved_by_user_id = :user_id,
                    resolution_note = :note
                WHERE escalation_id = :eid
                RETURNING escalation_id, shipment_id, escalation_type, escalation_status, resolution_note
                """
            ),
            {
                "status": status,
                "now_iso": now_iso,
                "eid": escalation_id,
                "user_id": ctx.user_id,
                "note": resolution_note,
            },
        )
    ).mappings().first()

    if row is None:
        row = (
            await session.execute(
                text(
                    """
                    UPDATE public.driver_exceptions
                    SET exception_status = :status,
                        resolution_note = :note
                    WHERE exception_id = :eid
                    RETURNING exception_id AS escalation_id, shipment_id, exception_type AS escalation_type,
                              exception_status AS escalation_status, resolution_note
                    """
                ),
                {"status": status, "eid": escalation_id, "note": resolution_note},
            )
        ).mappings().first()

    if row is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)

    shipment_id = row.get("shipment_id")
    if shipment_id:
        await session.execute(
            text(
                """
                UPDATE public.driver_exceptions
                SET exception_status = :status,
                    resolution_note = :note
                WHERE shipment_id = :shipment_id
                  AND exception_status NOT IN ('RESOLVED', 'CANCELLED', 'DUPLICATE')
                """
            ),
            {"shipment_id": shipment_id, "status": status, "note": resolution_note},
        )

    await session.commit()
    return dict(row)


async def get_dock_status(session: AsyncSession, ctx: ExecutionContext, facility_id: str | None) -> dict[str, Any]:
    scope = facility_id if ctx.is_admin else ctx.facility_id
    if not scope or (not ctx.is_admin and facility_id and facility_id != scope):
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    rows = (
        await session.execute(
            text(
                """
                SELECT d.dock_id, d.dock_code, d.dock_type, d.dock_status,
                       count(sl.slot_id) FILTER (WHERE sl.slot_status = 'OPEN')::int AS open_slots
                FROM public.docks d
                LEFT JOIN public.appointment_slots sl ON sl.dock_id = d.dock_id
                WHERE d.facility_id = :facility_id
                GROUP BY d.dock_id, d.dock_code, d.dock_type, d.dock_status
                ORDER BY d.dock_code
                """
            ),
            {"facility_id": scope},
        )
    ).mappings().all()
    return {"as_of": _as_of(), "source": "postgresql", "facility_id": scope, "docks": [dict(row) for row in rows]}


async def get_queue_status(session: AsyncSession, ctx: ExecutionContext, facility_id: str | None) -> dict[str, Any]:
    scope = facility_id if ctx.is_admin else ctx.facility_id
    if not scope or (not ctx.is_admin and facility_id and facility_id != scope):
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    pending = (
        await session.execute(
            text(
                """
                SELECT count(*)::int FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE sl.facility_id = :facility_id AND a.appointment_status = 'PENDING_CONFIRMATION'
                """
            ),
            {"facility_id": scope},
        )
    ).scalar_one()
    open_escalations = (
        await session.execute(
            text(
                """
                SELECT count(*)::int FROM public.escalation_queue
                WHERE facility_id = :facility_id AND escalation_status IN ('OPEN', 'IN_PROGRESS')
                """
            ),
            {"facility_id": scope},
        )
    ).scalar_one()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "facility_id": scope,
        "pending_appointments": pending,
        "open_escalations": open_escalations,
    }
