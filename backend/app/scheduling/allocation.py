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
from app.core.settings import get_settings
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import evaluate_candidate_slot, find_feasible_slots
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id
from app.services.redis_memory import ConversationMemory

AUDIT_ACTION_BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
AUDIT_ACTION_CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
AUDIT_ACTION_CONFIRM_APPOINTMENT = "UPDATE"
AUDIT_ACTION_RESCHEDULE_APPOINTMENT = "RESCHEDULE_APPOINTMENT"
AUDIT_ACTION_REJECT_APPOINTMENT = "REJECT_APPOINTMENT"
AUDIT_ACTION_EXPIRE_APPOINTMENT = "EXPIRE_APPOINTMENT"
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
    displayed_recommendation_id: str | None = Field(default=None, max_length=100)
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


class CancelAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    cancellation_reason: str = Field(min_length=1, max_length=500)
    client_message_id: str | None = Field(default=None, max_length=200)


class ConfirmAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    warehouse_confirmation_ref: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class RescheduleAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    new_slot_id: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    displayed_policy_version: str | None = Field(default=None, max_length=100)
    displayed_recommendation_id: str | None = Field(default=None, max_length=100)
    client_message_id: str | None = Field(default=None, max_length=200)


class RejectAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    rejection_reason: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=500)


class ExpireAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    expire_reason: str = Field(min_length=1, max_length=500)


class AppointmentTransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    status: str
    code: str
    shipment_id: str
    appointment_id: str
    appointment: dict[str, Any] | None = None
    idempotency_key: str
    idempotent_replay: bool = False
    appointment_writes: int = 1


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


def _assert_ops_scope(ctx: ExecutionContext, shipment: dict[str, Any]) -> None:
    if ctx.is_operator:
        if shipment["destination_facility_id"] != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_admin:
        return
    raise AppError("Only operations or admin may confirm appointments.", code="FORBIDDEN", status_code=403)


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
    if normalized == "EXPIRED":
        return "APPOINTMENT_EXPIRED", False
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


def replay_claim_is_active(appointment: dict[str, Any] | None) -> bool:
    if not appointment:
        return False
    status = str(appointment.get("appointment_status") or "")
    try:
        current = int(appointment.get("is_current") or 0)
    except (TypeError, ValueError):
        current = 0
    return status in ACTIVE_APPOINTMENT_STATUSES and current == 1


async def _store_request_idempotency(
    session: AsyncSession,
    *,
    persist: bool,
    key: str,
    user_id: str,
    route: str,
    request_hash: str,
    response: dict[str, Any],
    status_code: int,
) -> None:
    await store_idempotency(
        session,
        key=key,
        user_id=user_id,
        route=route,
        request_hash=request_hash,
        response=response,
        status_code=status_code,
    )
    if persist:
        await session.commit()


async def _locked_appointment(
    session: AsyncSession,
    *,
    shipment_id: str,
    appointment_id: str,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status,
                       booking_source, is_current, booked_at, confirmed_at,
                       cancelled_at, cancellation_reason, replaced_appointment_id,
                       warehouse_confirmation_ref, updated_at
                FROM public.appointments
                WHERE shipment_id = :shipment_id
                  AND appointment_id = :appointment_id
                FOR UPDATE
                """
            ),
            {"shipment_id": shipment_id, "appointment_id": appointment_id},
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
    params: dict[str, Any] = {"shipment_id": shipment_id}
    appointment_filter = ""
    if appointment_id:
        appointment_filter = "AND a.appointment_id = :appointment_id"
        params["appointment_id"] = appointment_id
    row = (
        await session.execute(
            text(
                f"""
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
                  {appointment_filter}
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
            params,
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


async def _stale_recommendation_result(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    policy_version: str,
    idempotency_key: str,
    message: str,
) -> RequestSlotResult:
    refreshed = await find_feasible_slots(session, ctx, shipment_id, limit=5)
    return RequestSlotResult(
        as_of=_as_of(),
        status="CONFLICTED",
        code="SLOT_OPTIONS_STALE",
        shipment_id=shipment_id,
        slot_id=slot_id,
        policy_version=policy_version,
        conflict={"reason_code": "SLOT_OPTIONS_STALE", "message": message},
        refreshed_options=refreshed.model_dump(),
        idempotency_key=idempotency_key,
        appointment_writes=0,
    )


async def _validate_displayed_recommendation(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    displayed_policy_version: str | None,
    displayed_recommendation_id: str | None,
    idempotency_key: str,
) -> RequestSlotResult | None:
    constraints = load_scheduling_constraints()
    if displayed_policy_version and displayed_policy_version != constraints.policy_version:
        return await _stale_recommendation_result(
            session, ctx, shipment_id=shipment_id, slot_id=slot_id,
            policy_version=constraints.policy_version, idempotency_key=idempotency_key,
            message="The displayed scheduling policy is no longer current.",
        )
    redis_stale = False
    try:
        redis_stale = ConversationMemory(get_settings()).is_recommendation_stale(
            user_id=ctx.user_id, shipment_id=shipment_id
        )
    except Exception:  # noqa: BLE001
        pass
    if not displayed_recommendation_id:
        if redis_stale:
            return await _stale_recommendation_result(
                session, ctx, shipment_id=shipment_id, slot_id=slot_id,
                policy_version=constraints.policy_version, idempotency_key=idempotency_key,
                message="Displayed slot options are stale; use the refreshed recommendation.",
            )
        return None
    refreshed = await find_feasible_slots(session, ctx, shipment_id, limit=5)
    if redis_stale or refreshed.recommendation_id != displayed_recommendation_id:
        return await _stale_recommendation_result(
            session, ctx, shipment_id=shipment_id, slot_id=slot_id,
            policy_version=constraints.policy_version, idempotency_key=idempotency_key,
            message="Displayed slot options are stale; use the refreshed recommendation.",
        )
    return None


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


async def cancel_appointment(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    command: CancelAppointmentCommand,
    idempotency_key: str,
) -> AppointmentTransitionResult:
    route = (
        f"POST /api/v1/shipments/{shipment_id}/appointments/"
        f"{command.appointment_id}/cancel"
    )
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        return AppointmentTransitionResult.model_validate(
            {**replay["response"], "idempotent_replay": True}
        )

    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_read_scope(ctx, shipment)

    appointment = await _locked_appointment(
        session,
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    old_status = str(appointment["appointment_status"])
    if old_status not in ACTIVE_APPOINTMENT_STATUSES:
        raise AppError(
            f"Cannot cancel appointment from {old_status}.",
            code="INVALID_APPOINTMENT_TRANSITION",
            status_code=409,
        )

    now = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CANCELLED',
                is_current = 0,
                cancelled_at = :cancelled_at,
                cancellation_reason = :cancellation_reason,
                updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {
            "appointment_id": command.appointment_id,
            "cancelled_at": now,
            "cancellation_reason": command.cancellation_reason,
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
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_CANCEL_APPOINTMENT,
            "entity_id": command.appointment_id,
            "old_value_json": json.dumps(
                {"status": old_status, "is_current": appointment["is_current"]},
                default=str,
            ),
            "new_value_json": json.dumps(
                {
                    "status": "CANCELLED",
                    "is_current": 0,
                    "cancellation_reason": command.cancellation_reason,
                },
                default=str,
            ),
            "created_at": now,
        },
    )
    updated = await _reread_appointment(session, command.appointment_id)
    result = AppointmentTransitionResult(
        as_of=_as_of(),
        status="CANCELLED",
        code="APPOINTMENT_CANCELLED",
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
        appointment=updated,
        idempotency_key=idempotency_key,
    )
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, command.appointment_id)
    return result


async def confirm_appointment(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    command: ConfirmAppointmentCommand,
    idempotency_key: str,
) -> AppointmentTransitionResult:
    route = (
        f"POST /api/v1/shipments/{shipment_id}/appointments/"
        f"{command.appointment_id}/confirm"
    )
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        return AppointmentTransitionResult.model_validate(
            {**replay["response"], "idempotent_replay": True}
        )

    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_ops_scope(ctx, shipment)

    appointment = await _locked_appointment(
        session,
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    old_status = str(appointment["appointment_status"])
    if old_status != "PENDING_CONFIRMATION":
        raise AppError(
            f"Cannot confirm appointment from {old_status}.",
            code="INVALID_APPOINTMENT_TRANSITION",
            status_code=409,
        )

    now = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CONFIRMED',
                confirmed_at = :confirmed_at,
                warehouse_confirmation_ref = :warehouse_confirmation_ref,
                updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {
            "appointment_id": command.appointment_id,
            "confirmed_at": now,
            "warehouse_confirmation_ref": command.warehouse_confirmation_ref,
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
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_CONFIRM_APPOINTMENT,
            "entity_id": command.appointment_id,
            "old_value_json": json.dumps({"status": old_status}, default=str),
            "new_value_json": json.dumps(
                {
                    "status": "CONFIRMED",
                    "warehouse_confirmation_ref": command.warehouse_confirmation_ref,
                    "note": command.note,
                },
                default=str,
            ),
            "created_at": now,
        },
    )
    updated = await _reread_appointment(session, command.appointment_id)
    result = AppointmentTransitionResult(
        as_of=_as_of(),
        status="CONFIRMED",
        code="APPOINTMENT_CONFIRMED",
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
        appointment=updated,
        idempotency_key=idempotency_key,
    )
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, command.appointment_id)
    return result


async def request_slot(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    command: RequestSlotCommand,
    idempotency_key: str,
    persist: bool = True,
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
        result = RequestSlotResult.model_validate({**replay["response"], "idempotent_replay": True})
        if result.code == "SLOT_REQUESTED" and result.appointment_id:
            existing = await _reread_appointment(session, result.appointment_id)
            if replay_claim_is_active(existing):
                return result
            await session.execute(
                text("DELETE FROM public.idempotency_requests WHERE idempotency_key = :key"),
                {"key": idempotency_key},
            )
        else:
            return result

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
    if ctx.is_driver:
        _assert_driver_scope(ctx, shipment_data)
    else:
        _assert_ops_scope(ctx, shipment_data)
    if int(shipment_data["active_flag"]) != 1:
        raise AppError("Destination facility is not active.", code="FACILITY_UNAVAILABLE", status_code=409)
    if shipment_data["current_status"] in ("COMPLETED", "CANCELLED"):
        raise AppError("Shipment is not eligible for slot request.", code="SHIPMENT_NOT_ACTIVE", status_code=409)

    stale = await _validate_displayed_recommendation(
        session,
        ctx,
        shipment_id=shipment_id,
        slot_id=slot_id,
        displayed_policy_version=command.displayed_policy_version,
        displayed_recommendation_id=command.displayed_recommendation_id,
        idempotency_key=idempotency_key,
    )
    if stale is not None:
        await _store_request_idempotency(
            session, persist=persist, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=stale.model_dump(), status_code=409,
        )
        return stale

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
        await _store_request_idempotency(
            session,
            persist=persist,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
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
        await _store_request_idempotency(
            session,
            persist=persist,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
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
        await _store_request_idempotency(
            session,
            persist=persist,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
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
    await _store_request_idempotency(
        session,
        persist=persist,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
        status_code=200,
    )
    if persist:
        final_appointment = await _reread_appointment(session, appointment_id)
        result.appointment = final_appointment
    result.idempotent_replay = False
    try:
        ConversationMemory(get_settings()).clear_recommendation_stale(
            user_id=ctx.user_id, shipment_id=shipment_id
        )
    except Exception:  # noqa: BLE001
        pass
    return result


async def _ops_pending_transition(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    appointment_id: str,
    target_status: str,
    reason: str,
    action_type: str,
    idempotency_key: str,
) -> AppointmentTransitionResult:
    route = f"POST /api/v1/shipments/{shipment_id}/appointments/{appointment_id}/{target_status.lower()}"
    req_hash = payload_hash({"shipment_id": shipment_id, "appointment_id": appointment_id, "reason": reason})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return AppointmentTransitionResult.model_validate({**replay["response"], "idempotent_replay": True})
    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_ops_scope(ctx, shipment)
    appointment = await _locked_appointment(
        session, shipment_id=shipment_id, appointment_id=appointment_id
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    if appointment["appointment_status"] != "PENDING_CONFIRMATION":
        raise AppError(
            f"Cannot transition appointment from {appointment['appointment_status']}.",
            code="INVALID_APPOINTMENT_TRANSITION",
            status_code=409,
        )
    now = _as_of()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = :status, is_current = 0,
                cancellation_reason = :reason, updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {"status": target_status, "reason": reason, "updated_at": now, "appointment_id": appointment_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'appointments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "user_id": ctx.user_id, "action_type": action_type,
            "entity_id": appointment_id,
            "old_value_json": json.dumps({"status": "PENDING_CONFIRMATION"}),
            "new_value_json": json.dumps({"status": target_status, "reason": reason}),
            "created_at": now,
        },
    )
    result = AppointmentTransitionResult(
        as_of=_as_of(), status=target_status, code=f"APPOINTMENT_{target_status}",
        shipment_id=shipment_id, appointment_id=appointment_id,
        appointment=await _reread_appointment(session, appointment_id), idempotency_key=idempotency_key,
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump()
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, appointment_id)
    return result


async def reject_appointment(
    session: AsyncSession, ctx: ExecutionContext, *, shipment_id: str,
    command: RejectAppointmentCommand, idempotency_key: str
) -> AppointmentTransitionResult:
    return await _ops_pending_transition(
        session, ctx, shipment_id=shipment_id, appointment_id=command.appointment_id,
        target_status="REJECTED", reason=command.rejection_reason,
        action_type=AUDIT_ACTION_REJECT_APPOINTMENT, idempotency_key=idempotency_key,
    )


async def expire_appointment(
    session: AsyncSession, ctx: ExecutionContext, *, shipment_id: str,
    command: ExpireAppointmentCommand, idempotency_key: str
) -> AppointmentTransitionResult:
    return await _ops_pending_transition(
        session, ctx, shipment_id=shipment_id, appointment_id=command.appointment_id,
        target_status="EXPIRED", reason=command.expire_reason,
        action_type=AUDIT_ACTION_EXPIRE_APPOINTMENT, idempotency_key=idempotency_key,
    )


async def reschedule_appointment(
    session: AsyncSession, ctx: ExecutionContext, *, shipment_id: str,
    command: RescheduleAppointmentCommand, idempotency_key: str
) -> RequestSlotResult:
    route = f"POST /api/v1/shipments/{shipment_id}/appointments/{command.appointment_id}/reschedule"
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return RequestSlotResult.model_validate({**replay["response"], "idempotent_replay": True})
    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_read_scope(ctx, shipment)
    stale = await _validate_displayed_recommendation(
        session, ctx, shipment_id=shipment_id, slot_id=command.new_slot_id,
        displayed_policy_version=command.displayed_policy_version,
        displayed_recommendation_id=command.displayed_recommendation_id,
        idempotency_key=idempotency_key,
    )
    if stale is not None:
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=stale.model_dump(), status_code=409
        )
        await session.commit()
        return stale
    # Verify the requested replacement remains among the fresh options before
    # retiring the current claim. The subsequent request_slot performs locked
    # revalidation and PostgreSQL remains the final concurrency authority.
    options = await find_feasible_slots(session, ctx, shipment_id, limit=10)
    if command.new_slot_id not in {option.slot_id for option in options.options}:
        conflict = await _conflict_result(
            session, ctx, shipment_id=shipment_id, slot_id=command.new_slot_id,
            policy_version=options.policy_version, reason_code="SLOT_NOT_FEASIBLE",
            message="Replacement slot is no longer a fresh feasible option.", idempotency_key=idempotency_key,
        )
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=conflict.model_dump(), status_code=409,
        )
        await session.commit()
        return conflict
    old = await _locked_appointment(
        session, shipment_id=shipment_id, appointment_id=command.appointment_id
    )
    if old is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    if old["appointment_status"] not in ACTIVE_APPOINTMENT_STATUSES:
        raise AppError("Appointment is not active.", code="INVALID_APPOINTMENT_TRANSITION", status_code=409)
    now = _as_of()
    prior_status = str(old["appointment_status"])
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CANCELLED', is_current = 0, cancelled_at = :updated_at,
                cancellation_reason = :reason, updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {"appointment_id": command.appointment_id, "updated_at": now, "reason": "Replaced by reschedule"},
    )
    # Recommendation freshness was already validated above against the true
    # pre-cancel snapshot, and new_slot_id was already confirmed to be a live
    # feasible option. Do not re-pass displayed_recommendation_id/policy_version
    # here: cancelling the old appointment just freed its slot back into the
    # candidate pool, so a fresh find_feasible_slots inside request_slot's own
    # staleness check would almost always disagree with the pre-cancel hash and
    # incorrectly reject every reschedule as SLOT_OPTIONS_STALE. Concurrency
    # safety still comes from request_slot's row lock and the DB unique
    # constraints, not from this hash comparison.
    result = await request_slot(
        session, ctx, shipment_id=shipment_id, slot_id=command.new_slot_id,
        command=RequestSlotCommand(
            note=command.note, displayed_policy_version=None,
            displayed_recommendation_id=None,
            client_message_id=command.client_message_id,
        ),
        idempotency_key=f"{idempotency_key}:claim",
        persist=False,
    )
    if result.code != "SLOT_REQUESTED":
        await session.execute(
            text(
                """
                UPDATE public.appointments
                SET appointment_status = :status, is_current = 1,
                    cancelled_at = NULL, cancellation_reason = NULL, updated_at = :updated_at
                WHERE appointment_id = :appointment_id
                """
            ),
            {
                "status": prior_status,
                "updated_at": _as_of(),
                "appointment_id": command.appointment_id,
            },
        )
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=result.model_dump(), status_code=409,
        )
        await session.commit()
        return result
    await session.execute(
        text("UPDATE public.appointments SET replaced_appointment_id = :old_id WHERE appointment_id = :new_id"),
        {"old_id": command.appointment_id, "new_id": result.appointment_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'appointments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_RESCHEDULE_APPOINTMENT, "entity_id": result.appointment_id,
            "old_value_json": json.dumps({"appointment_id": command.appointment_id, "status": old["appointment_status"]}),
            "new_value_json": json.dumps({"appointment_id": result.appointment_id, "slot_id": command.new_slot_id}),
            "created_at": _as_of(),
        },
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump()
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, str(result.appointment_id))
    return result
