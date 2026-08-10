from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.services.idempotency import (
    lookup_idempotency,
    payload_hash,
    store_idempotency,
)
from app.services.ids import new_id
from app.services.scheduling.schemas import (
    BookingResultDTO,
    CancelAppointmentCommand,
    RescheduleCommand,
    SlotBookingCommand,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def request_slot_service(
    session: AsyncSession,
    ctx: ExecutionContext,
    command: SlotBookingCommand,
) -> BookingResultDTO:
    # 1. Idempotency Check
    payload_dump = command.model_dump()
    req_hash = payload_hash(payload_dump)
    route = "REQUEST_SLOT"
    cached = await lookup_idempotency(
        session, key=command.idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if cached is not None:
        return BookingResultDTO.model_validate(cached["response"])

    # 2. Lock and Check Shipment
    shipment = (
        await session.execute(
            text(
                """
                SELECT shipment_id, driver_id, destination_facility_id, current_status
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                FOR UPDATE
                """
            ),
            {"shipment_id": command.shipment_id},
        )
    ).mappings().first()

    if not shipment:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)

    if ctx.is_driver and shipment["driver_id"] != ctx.driver_id:
        raise AppError("Access denied to shipment.", code="FORBIDDEN", status_code=403)

    # 3. Lock and Verify Slot
    slot = (
        await session.execute(
            text(
                """
                SELECT slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts, slot_status
                FROM public.appointment_slots
                WHERE slot_id = :slot_id
                FOR UPDATE
                """
            ),
            {"slot_id": command.slot_id},
        )
    ).mappings().first()

    if not slot or slot["slot_status"] != "OPEN":
        raise AppError(
            "Selected slot is no longer available.",
            code="SLOT_NO_LONGER_AVAILABLE",
            status_code=409,
        )

    # 4. Lock & Check Existing Appointments on the Slot
    conflict = (
        await session.execute(
            text(
                """
                SELECT appointment_id FROM public.appointments
                WHERE slot_id = :slot_id
                  AND appointment_status IN ('CONFIRMED', 'PENDING_CONFIRMATION', 'IN_PROGRESS')
                  AND is_current = 1
                FOR UPDATE
                """
            ),
            {"slot_id": command.slot_id},
        )
    ).mappings().first()

    if conflict:
        raise AppError(
            "Slot has been claimed by another transaction. Please select a different slot.",
            code="SLOT_NO_LONGER_AVAILABLE",
            status_code=409,
        )

    now = _now_iso()
    apt_id = new_id("APT")

    # 5. Archive Old Current Appointments for this Shipment
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET is_current = 0, updated_at = :updated_at
            WHERE shipment_id = :shipment_id AND is_current = 1
            """
        ),
        {"shipment_id": command.shipment_id, "updated_at": now},
    )

    # 6. Insert New Appointment
    await session.execute(
        text(
            """
            INSERT INTO public.appointments (
                appointment_id, shipment_id, slot_id, appointment_status,
                booking_source, is_current, booked_at, confirmed_at, updated_at
            ) VALUES (
                :apt_id, :shipment_id, :slot_id, 'CONFIRMED',
                :source, 1, :now, :now, :now
            )
            """
        ),
        {
            "apt_id": apt_id,
            "shipment_id": command.shipment_id,
            "slot_id": command.slot_id,
            "source": "DRIVER_CHAT" if ctx.is_driver else "SCHEDULING_TOOL",
            "now": now,
        },
    )

    # 7. Audit Log Entry
    audit_id = new_id("AUD")
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
                audit_id, user_id, action_type, entity_name, entity_id, new_value_json, created_at
            ) VALUES (
                :audit_id, :user_id, 'BOOK_APPOINTMENT', 'appointment', :apt_id, :payload, :now
            )
            """
        ),
        {
            "audit_id": audit_id,
            "user_id": ctx.user_id,
            "apt_id": apt_id,
            "payload": f"Booked slot {command.slot_id} for shipment {command.shipment_id}",
            "now": now,
        },
    )

    result = BookingResultDTO(
        appointment_id=apt_id,
        shipment_id=command.shipment_id,
        slot_id=command.slot_id,
        dock_id=slot["dock_id"],
        appointment_status="CONFIRMED",
        booking_source="DRIVER_CHAT" if ctx.is_driver else "SCHEDULING_TOOL",
        booked_at=now,
        confirmed_at=now,
        message="Appointment successfully booked and confirmed.",
    )

    await session.commit()
    await store_idempotency(
        session,
        key=command.idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
    )
    return result


async def reschedule_appointment_service(
    session: AsyncSession,
    ctx: ExecutionContext,
    command: RescheduleCommand,
) -> BookingResultDTO:
    payload_dump = command.model_dump()
    req_hash = payload_hash(payload_dump)
    route = "RESCHEDULE_SLOT"
    cached = await lookup_idempotency(
        session, key=command.idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if cached is not None:
        return BookingResultDTO.model_validate(cached["response"])

    # 1. Lock Current Appointment
    curr_apt = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status
                FROM public.appointments
                WHERE appointment_id = :apt_id AND is_current = 1
                FOR UPDATE
                """
            ),
            {"apt_id": command.current_appointment_id},
        )
    ).mappings().first()

    if not curr_apt:
        raise AppError("Active appointment not found.", code="NOT_FOUND", status_code=404)

    shipment_id = curr_apt["shipment_id"]

    # 2. Lock Target Slot
    target_slot = (
        await session.execute(
            text(
                """
                SELECT slot_id, facility_id, dock_id, slot_status
                FROM public.appointment_slots
                WHERE slot_id = :slot_id
                FOR UPDATE
                """
            ),
            {"slot_id": command.target_slot_id},
        )
    ).mappings().first()

    if not target_slot or target_slot["slot_status"] != "OPEN":
        raise AppError(
            "Target slot is not available for reschedule.",
            code="SLOT_NO_LONGER_AVAILABLE",
            status_code=409,
        )

    # Check for overlapping active appointment on target slot
    conflict = (
        await session.execute(
            text(
                """
                SELECT appointment_id FROM public.appointments
                WHERE slot_id = :slot_id
                  AND appointment_status IN ('CONFIRMED', 'PENDING_CONFIRMATION', 'IN_PROGRESS')
                  AND is_current = 1
                FOR UPDATE
                """
            ),
            {"slot_id": command.target_slot_id},
        )
    ).mappings().first()

    if conflict:
        raise AppError(
            "Target slot has been booked by another driver.",
            code="SLOT_NO_LONGER_AVAILABLE",
            status_code=409,
        )

    now = _now_iso()

    # 3. Cancel Current Appointment
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CANCELLED', is_current = 0,
                cancelled_at = :now, cancellation_reason = 'RESCHEDULED', updated_at = :now
            WHERE appointment_id = :apt_id
            """
        ),
        {"apt_id": command.current_appointment_id, "now": now},
    )

    # 4. Create New Appointment
    new_apt_id = new_id("APT")
    await session.execute(
        text(
            """
            INSERT INTO public.appointments (
                appointment_id, shipment_id, slot_id, appointment_status,
                booking_source, is_current, booked_at, confirmed_at,
                replaced_appointment_id, updated_at
            ) VALUES (
                :apt_id, :shipment_id, :slot_id, 'CONFIRMED',
                :source, 1, :now, :now, :old_apt_id, :now
            )
            """
        ),
        {
            "apt_id": new_apt_id,
            "shipment_id": shipment_id,
            "slot_id": command.target_slot_id,
            "source": "DRIVER_CHAT" if ctx.is_driver else "SCHEDULING_TOOL",
            "now": now,
            "old_apt_id": command.current_appointment_id,
        },
    )

    # 5. Audit Log
    audit_id = new_id("AUD")
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
                audit_id, user_id, action_type, entity_name, entity_id, new_value_json, created_at
            ) VALUES (
                :audit_id, :user_id, 'BOOK_APPOINTMENT', 'appointment', :apt_id, :payload, :now
            )
            """
        ),
        {
            "audit_id": audit_id,
            "user_id": ctx.user_id,
            "apt_id": new_apt_id,
            "payload": f"Rescheduled appointment {command.current_appointment_id} -> {new_apt_id} (slot {command.target_slot_id})",
            "now": now,
        },
    )

    result = BookingResultDTO(
        appointment_id=new_apt_id,
        shipment_id=shipment_id,
        slot_id=command.target_slot_id,
        dock_id=target_slot["dock_id"],
        appointment_status="CONFIRMED",
        booking_source="DRIVER_CHAT" if ctx.is_driver else "SCHEDULING_TOOL",
        booked_at=now,
        confirmed_at=now,
        message="Appointment successfully rescheduled.",
    )

    await session.commit()
    await store_idempotency(
        session,
        key=command.idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
    )
    return result


async def cancel_appointment_service(
    session: AsyncSession,
    ctx: ExecutionContext,
    command: CancelAppointmentCommand,
) -> dict[str, Any]:
    payload_dump = command.model_dump()
    req_hash = payload_hash(payload_dump)
    route = "CANCEL_APPOINTMENT"
    cached = await lookup_idempotency(
        session, key=command.idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if cached is not None:
        return cached["response"]

    apt = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status
                FROM public.appointments
                WHERE appointment_id = :apt_id AND is_current = 1
                FOR UPDATE
                """
            ),
            {"apt_id": command.appointment_id},
        )
    ).mappings().first()

    if not apt:
        raise AppError("Appointment not found or already inactive.", code="NOT_FOUND", status_code=404)

    now = _now_iso()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CANCELLED', is_current = 0,
                cancelled_at = :now, cancellation_reason = :reason, updated_at = :now
            WHERE appointment_id = :apt_id
            """
        ),
        {
            "apt_id": command.appointment_id,
            "reason": command.reason or "DRIVER_CANCELLED",
            "now": now,
        },
    )

    # Audit Log
    audit_id = new_id("AUD")
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
                audit_id, user_id, action_type, entity_name, entity_id, new_value_json, created_at
            ) VALUES (
                :audit_id, :user_id, 'CANCEL_APPOINTMENT', 'appointment', :apt_id, :payload, :now
            )
            """
        ),
        {
            "audit_id": audit_id,
            "user_id": ctx.user_id,
            "apt_id": command.appointment_id,
            "payload": f"Cancelled appointment {command.appointment_id}: {command.reason}",
            "now": now,
        },
    )

    result = {
        "appointment_id": command.appointment_id,
        "shipment_id": apt["shipment_id"],
        "status": "CANCELLED",
        "cancelled_at": now,
        "message": "Appointment successfully cancelled.",
    }

    await session.commit()
    await store_idempotency(
        session,
        key=command.idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result,
    )
    return result
