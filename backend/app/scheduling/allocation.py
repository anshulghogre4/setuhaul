from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import evaluate_candidate_slot, find_feasible_slots
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

AUDIT_ACTION_BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")
ALLOCATION_UNIQUE_CONSTRAINTS = frozenset(
    {
        "ux_active_appointment_per_slot",
        "ux_current_active_appointment_per_shipment",
    }
)


class RequestSlotCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)
    displayed_policy_version: str | None = Field(
        default=None,
        description="Policy version shown with the displayed option, if the client has it.",
    )
    client_message_id: str | None = Field(default=None, max_length=200)


class RequestSlotResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    status: str
    code: str
    shipment_id: str
    slot_id: str
    appointment_id: str | None = None
    policy_version: str
    appointment: dict[str, Any] | None = None
    conflict: dict[str, Any] | None = None
    refreshed_options: dict[str, Any] | None = None
    idempotency_key: str | None = None
    idempotent_replay: bool = False
    appointment_writes: int = 0


class AppointmentRequestStatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    code: str
    shipment_id: str
    appointment_id: str | None = None
    appointment: dict[str, Any] | None = None
    history: list[dict[str, Any]]
    requires_human_confirmation: bool = False
    options_are_reserved: bool = False
    appointment_writes: int = 0


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_driver_scope(ctx: ExecutionContext, shipment: dict[str, Any]) -> None:
    if not ctx.is_driver or not ctx.driver_id:
        raise AppError("Only the assigned driver may request a slot.", code="FORBIDDEN", status_code=403)
    if shipment["driver_id"] != ctx.driver_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)


def _assert_read_scope(ctx: ExecutionContext, shipment: dict[str, Any]) -> None:
    if ctx.is_driver:
        if shipment["driver_id"] != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_operator:
        if shipment["destination_facility_id"] != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_admin:
        return
    raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


def appointment_request_status_code(status: str | None) -> tuple[str, bool]:
    if status is None:
        return "NO_APPOINTMENT_REQUEST", False
    normalized = status.upper()
    if normalized == "PENDING_CONFIRMATION":
        return "APPOINTMENT_PENDING_CONFIRMATION", True
    if normalized == "CONFIRMED":
        return "APPOINTMENT_CONFIRMED", False
    if normalized == "IN_PROGRESS":
        return "APPOINTMENT_IN_PROGRESS", False
    if normalized == "REJECTED":
        return "APPOINTMENT_REJECTED", False
    if normalized == "CANCELLED":
        return "APPOINTMENT_CANCELLED", False
    if normalized == "COMPLETED":
        return "APPOINTMENT_COMPLETED", False
    if normalized == "NO_SHOW":
        return "APPOINTMENT_NO_SHOW", False
    return "APPOINTMENT_STATUS_UNKNOWN", False


def allocation_unique_constraint_name(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    constraint_name = getattr(orig, "constraint_name", None)
    if constraint_name in ALLOCATION_UNIQUE_CONSTRAINTS:
        return str(constraint_name)
    message = str(exc)
    for name in ALLOCATION_UNIQUE_CONSTRAINTS:
        if name in message:
            return name
    return None


async def _reread_appointment(session: AsyncSession, appointment_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.booking_source, a.is_current, a.booked_at, a.confirmed_at,
                       a.cancelled_at, a.cancellation_reason, a.replaced_appointment_id,
                       a.warehouse_confirmation_ref, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.appointment_id = :appointment_id
                """
            ),
            {"appointment_id": appointment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _shipment_for_status(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, driver_id, destination_facility_id
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _appointment_request_status_row(
    session: AsyncSession,
    *,
    shipment_id: str,
    appointment_id: str | None,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.booking_source, a.is_current, a.booked_at, a.confirmed_at,
                       a.cancelled_at, a.cancellation_reason, a.replaced_appointment_id,
                       a.warehouse_confirmation_ref, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       d.dock_code, d.dock_type
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                LEFT JOIN public.docks d ON d.dock_id = sl.dock_id
                WHERE a.shipment_id = :shipment_id
                  AND (:appointment_id IS NULL OR a.appointment_id = :appointment_id)
                ORDER BY
                  CASE
                    WHEN a.is_current = 1
                     AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                    THEN 0
                    ELSE 1
                  END,
                  a.updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id, "appointment_id": appointment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _appointment_request_history(session: AsyncSession, shipment_id: str) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status,
                       booking_source, is_current, booked_at, confirmed_at,
                       cancelled_at, cancellation_reason, replaced_appointment_id,
                       warehouse_confirmation_ref, updated_at
                FROM public.appointments
                WHERE shipment_id = :shipment_id
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 10
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _active_appointment_for_slot(session: AsyncSession, slot_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status, is_current, updated_at
                FROM public.appointments
                WHERE slot_id = :slot_id
                  AND appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"slot_id": slot_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _current_active_appointment_for_shipment(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status, is_current, updated_at
                FROM public.appointments
                WHERE shipment_id = :shipment_id
                  AND is_current = 1
                  AND appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _conflict_result(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    policy_version: str,
    reason_code: str,
    message: str,
    idempotency_key: str,
) -> RequestSlotResult:
    refreshed = await find_feasible_slots(session, ctx, shipment_id, limit=5)
    return RequestSlotResult(
        as_of=_as_of(),
        status="CONFLICTED",
        code="SLOT_CONFLICT_REFRESH_REQUIRED",
        shipment_id=shipment_id,
        slot_id=slot_id,
        policy_version=policy_version,
        conflict={"reason_code": reason_code, "message": message},
        refreshed_options=refreshed.model_dump(),
        idempotency_key=idempotency_key,
        appointment_writes=0,
    )


async def get_appointment_request_status(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    appointment_id: str | None = None,
) -> AppointmentRequestStatusResult:
    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_read_scope(ctx, shipment)

    appointment = await _appointment_request_status_row(
        session,
        shipment_id=shipment_id,
        appointment_id=appointment_id,
    )
    history = await _appointment_request_history(session, shipment_id)
    status = appointment["appointment_status"] if appointment else None
    code, requires_confirmation = appointment_request_status_code(str(status) if status else None)

    return AppointmentRequestStatusResult(
        as_of=_as_of(),
        code=code,
        shipment_id=shipment_id,
        appointment_id=appointment["appointment_id"] if appointment else appointment_id,
        appointment=appointment,
        history=history,
        requires_human_confirmation=requires_confirmation,
    )


async def request_slot(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    command: RequestSlotCommand,
    idempotency_key: str,
) -> RequestSlotResult:
    constraints = load_scheduling_constraints()
    route = f"POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request"
    req_hash = payload_hash(
        {
            "shipment_id": shipment_id,
            "slot_id": slot_id,
            **command.model_dump(),
        }
    )

    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        return RequestSlotResult.model_validate({**replay["response"], "idempotent_replay": True})

    now = datetime.now(timezone.utc).isoformat()
    shipment = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.driver_id, s.vehicle_id, s.destination_facility_id,
                       s.priority_code, s.required_dock_type, s.temperature_control_required,
                       s.load_weight_kg, s.expected_unload_min, s.current_status,
                       le.effective_eta_ts, le.eta_source, le.eta_confidence,
                       f.facility_id, f.timezone, f.open_time, f.close_time, f.active_flag
                FROM public.shipments s
                JOIN public.v_latest_eta le ON le.shipment_id = s.shipment_id
                JOIN public.facilities f ON f.facility_id = s.destination_facility_id
                WHERE s.shipment_id = :shipment_id
                FOR UPDATE OF s
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    shipment_data = dict(shipment)
    _assert_driver_scope(ctx, shipment_data)
    if int(shipment_data["active_flag"]) != 1:
        raise AppError("Destination facility is not active.", code="FACILITY_UNAVAILABLE", status_code=409)
    if shipment_data["current_status"] in ("COMPLETED", "CANCELLED"):
        raise AppError("Shipment is not eligible for slot request.", code="SHIPMENT_NOT_ACTIVE", status_code=409)

    active_for_shipment = await _current_active_appointment_for_shipment(session, shipment_id)
    if active_for_shipment:
        result = await _conflict_result(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            reason_code="ACTIVE_APPOINTMENT_EXISTS",
            message="Shipment already has an active current appointment. Use reschedule flow next.",
            idempotency_key=idempotency_key,
        )
        await store_idempotency(
            session,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
        await session.commit()
        return result

    slot = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       sl.slot_status, sl.block_reason, d.dock_code, d.dock_type,
                       d.supports_refrigerated, d.max_vehicle_weight_kg, d.dock_status
                FROM public.appointment_slots sl
                JOIN public.docks d ON d.dock_id = sl.dock_id
                WHERE sl.slot_id = :slot_id
                  AND sl.facility_id = :facility_id
                FOR UPDATE OF sl
                """
            ),
            {"slot_id": slot_id, "facility_id": shipment_data["destination_facility_id"]},
        )
    ).mappings().first()
    if slot is None:
        raise AppError("Slot not found for shipment facility.", code="SLOT_NOT_FOUND", status_code=404)

    active_for_slot = await _active_appointment_for_slot(session, slot_id)
    dock_event = (
        await session.execute(
            text(
                """
                SELECT dock_event_id
                FROM public.dock_status_events
                WHERE dock_id = :dock_id
                  AND event_start_ts < :slot_end_ts
                  AND (event_end_ts IS NULL OR event_end_ts > :slot_start_ts)
                ORDER BY event_start_ts DESC
                LIMIT 1
                """
            ),
            {
                "dock_id": slot["dock_id"],
                "slot_start_ts": slot["slot_start_ts"],
                "slot_end_ts": slot["slot_end_ts"],
            },
        )
    ).mappings().first()

    candidate = dict(slot)
    candidate["active_appointment_id"] = active_for_slot["appointment_id"] if active_for_slot else None
    candidate["active_dock_event_id"] = dock_event["dock_event_id"] if dock_event else None
    option, reason = evaluate_candidate_slot(
        shipment=shipment_data,
        facility=shipment_data,
        eta_dt=datetime.fromisoformat(str(shipment_data["effective_eta_ts"])),
        candidate=candidate,
        checked_constraints=sorted(constraints.hard_constraint_ids()),
    )
    if option is None:
        result = await _conflict_result(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            reason_code=reason.failure_code if reason else "SLOT_NOT_FEASIBLE",
            message=reason.message if reason else "Selected slot is no longer feasible.",
            idempotency_key=idempotency_key,
        )
        await store_idempotency(
            session,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
        await session.commit()
        return result

    appointment_id = new_id("APT")
    audit_id = new_id("AUD")
    try:
        await session.execute(
            text(
                """
                INSERT INTO public.appointments (
                  appointment_id, shipment_id, slot_id, appointment_status, booking_source,
                  is_current, booked_at, confirmed_at, cancelled_at, cancellation_reason,
                  replaced_appointment_id, warehouse_confirmation_ref, updated_at
                ) VALUES (
                  :appointment_id, :shipment_id, :slot_id, 'PENDING_CONFIRMATION', 'DRIVER_CHAT',
                  1, :booked_at, NULL, NULL, NULL, NULL, NULL, :updated_at
                )
                """
            ),
            {
                "appointment_id": appointment_id,
                "shipment_id": shipment_id,
                "slot_id": slot_id,
                "booked_at": now,
                "updated_at": now,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO public.audit_logs (
                  audit_id, user_id, action_type, entity_name, entity_id,
                  old_value_json, new_value_json, ip_address, user_agent, created_at
                ) VALUES (
                  :audit_id, :user_id, :action_type, 'appointments', :entity_id,
                  NULL, :new_value_json, NULL, NULL, :created_at
                )
                """
            ),
            {
                "audit_id": audit_id,
                "user_id": ctx.user_id,
                "action_type": AUDIT_ACTION_BOOK_APPOINTMENT,
                "entity_id": appointment_id,
                "new_value_json": json.dumps(
                    {
                        "shipment_id": shipment_id,
                        "slot_id": slot_id,
                        "status": "PENDING_CONFIRMATION",
                        "policy_version": constraints.policy_version,
                        "displayed_policy_version": command.displayed_policy_version,
                        "note": command.note,
                    },
                    default=str,
                ),
                "created_at": now,
            },
        )
        await session.flush()
    except IntegrityError as exc:
        constraint_name = allocation_unique_constraint_name(exc)
        if constraint_name is None:
            raise
        await session.rollback()
        result = await _conflict_result(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            reason_code="POSTGRES_UNIQUE_ALLOCATION_CONFLICT",
            message=(
                "PostgreSQL rejected the appointment claim because another active appointment "
                f"already satisfies {constraint_name}."
            ),
            idempotency_key=idempotency_key,
        )
        await store_idempotency(
            session,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
        await session.commit()
        return result

    appointment = await _reread_appointment(session, appointment_id)
    result = RequestSlotResult(
        as_of=_as_of(),
        status="PENDING_CONFIRMATION",
        code="SLOT_REQUESTED",
        shipment_id=shipment_id,
        slot_id=slot_id,
        appointment_id=appointment_id,
        policy_version=constraints.policy_version,
        appointment=appointment,
        idempotency_key=idempotency_key,
        appointment_writes=1,
    )
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
        status_code=200,
    )
    await session.commit()

    final_appointment = await _reread_appointment(session, appointment_id)
    result.appointment = final_appointment
    result.idempotent_replay = False
    return result
