from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.execution_context import ExecutionContext
from app.services import driver_reads
from app.services.eta_service import EtaUpdateCommand, confirmation_preview, record_eta_update
from app.services.scheduling.booking import (
    cancel_appointment_service,
    request_slot_service,
    reschedule_appointment_service,
)
from app.services.scheduling.escalation import escalate_exception_service
from app.services.scheduling.feasibility import find_feasible_slots_service
from app.services.scheduling.schemas import (
    CancelAppointmentCommand,
    EscalationCommand,
    FeasibilitySearchCommand,
    RescheduleCommand,
    SlotBookingCommand,
)


class EmptyArgs(BaseModel):
    pass


class ShipmentIdArgs(BaseModel):
    shipment_id: str = Field(description="Shipment identifier, e.g. SHP1017")


class FacilityIdArgs(BaseModel):
    facility_id: str = Field(description="Facility identifier, e.g. FAC-JAI-01")


class ExceptionArgs(BaseModel):
    shipment_id: str | None = Field(default=None, description="Optional shipment filter")


class ReportDelayArgs(BaseModel):
    shipment_id: str | None = Field(
        default=None,
        description="Shipment to update. Required when the driver has multiple active shipments.",
    )
    declared_eta_ts: str | None = Field(
        default=None,
        description="ISO-8601 arrival timestamp WITH timezone offset. Not repair duration.",
    )
    repair_duration_min: int | None = Field(
        default=None,
        description="Repair duration in minutes. Never treat as ETA.",
    )
    reported_delay_min: int | None = Field(default=None, description="Reported delay minutes")
    delay_reason_code: str | None = Field(default=None, description="e.g. TRAFFIC, BREAKDOWN")
    confidence_code: str = Field(default="MEDIUM")
    note: str | None = None
    confirmed: bool = Field(
        default=False,
        description="True only after driver explicitly confirms the exact display ETA.",
    )
    confirmation_eta_ts: str | None = Field(
        default=None,
        description="Must equal declared_eta_ts when confirmed=true.",
    )
    description: str | None = None


class SchedulingArgs(BaseModel):
    intent: str = Field(description="Requested scheduling action")
    shipment_id: str | None = None


class FindFeasibleSlotsArgs(BaseModel):
    shipment_id: str | None = Field(default=None, description="Shipment ID to search slots for.")
    target_date: str | None = Field(default=None, description="Optional target date YYYY-MM-DD.")
    after_time_ts: str | None = Field(default=None, description="ISO timestamp filter for minimum slot start time.")
    revised_eta_ts: str | None = Field(default=None, description="Revised ETA timestamp override if declared.")


class RequestSlotArgs(BaseModel):
    shipment_id: str | None = Field(default=None, description="Shipment ID")
    slot_id: str = Field(description="Selected candidate slot_id to book")
    note: str | None = Field(default=None, description="Optional note")


class RescheduleSlotArgs(BaseModel):
    current_appointment_id: str = Field(description="ID of the current active appointment to replace")
    target_slot_id: str = Field(description="Target slot_id to move appointment to")
    reason: str | None = Field(default=None, description="Reason for reschedule")


class CancelSlotArgs(BaseModel):
    appointment_id: str = Field(description="ID of the appointment to cancel")
    reason: str | None = Field(default=None, description="Reason for cancellation")


class EscalateExceptionArgs(BaseModel):
    shipment_id: str | None = Field(default=None, description="Shipment ID requiring human escalation")
    reason: str = Field(description="Detailed reason why automated slot finding failed or takeover is needed")
    urgency: str = Field(default="HIGH", description="NORMAL, HIGH, or CRITICAL")


def _json(data: Any) -> str:
    return json.dumps(data, default=str)


def build_driver_tools(
    *,
    session: AsyncSession,
    ctx: ExecutionContext,
    thread_id: str,
) -> list[StructuredTool]:
    """Role-scoped POC tools for ChatOpenAI.bind_tools (driver allowlist)."""

    async def get_current_user_context(_: EmptyArgs | None = None) -> str:
        return _json(
            {
                "user_id": ctx.user_id,
                "full_name": ctx.full_name,
                "email": ctx.email,
                "role_name": ctx.role_name,
                "driver_id": ctx.driver_id,
                "facility_id": ctx.facility_id,
                "permissions": ctx.permissions,
            }
        )

    async def get_driver_operational_context(_: EmptyArgs | None = None) -> str:
        return _json(await driver_reads.get_driver_operational_context(session, ctx))

    async def list_active_shipments(_: EmptyArgs | None = None) -> str:
        data = await driver_reads.get_driver_operational_context(session, ctx)
        return _json(
            {
                "active_shipments": data.get("active_shipments", []),
                "as_of": data.get("as_of"),
                "source": "postgresql",
            }
        )

    async def get_shipment_details(args: ShipmentIdArgs) -> str:
        return _json(await driver_reads.get_shipment_details(session, ctx, args.shipment_id))

    async def get_latest_eta(args: ShipmentIdArgs) -> str:
        return _json(await driver_reads.get_latest_eta(session, ctx, args.shipment_id))

    async def get_eta_history(args: ShipmentIdArgs) -> str:
        return _json(await driver_reads.get_eta_history(session, ctx, args.shipment_id))

    async def get_current_appointment(args: ShipmentIdArgs) -> str:
        return _json(await driver_reads.get_current_appointment(session, ctx, args.shipment_id))

    async def get_facility_details(args: FacilityIdArgs) -> str:
        return _json(await driver_reads.get_facility_details(session, ctx, args.facility_id))

    async def get_exception_status(args: ExceptionArgs) -> str:
        return _json(await driver_reads.get_exception_status(session, ctx, args.shipment_id))

    async def report_delay_or_update_eta(args: ReportDelayArgs) -> str:
        context = await driver_reads.get_driver_operational_context(session, ctx)
        active = context.get("active_shipments") or []
        shipment_id = args.shipment_id
        if not shipment_id:
            if len(active) == 0:
                return _json({"code": "NO_ACTIVE_SHIPMENT", "message": "No active shipment found."})
            if len(active) > 1:
                return _json(
                    {
                        "code": "CLARIFICATION_REQUIRED",
                        "message": "Multiple active shipments. Ask which shipment_id to update.",
                        "candidates": [
                            {"shipment_id": s["shipment_id"], "status": s["current_status"]}
                            for s in active
                        ],
                    }
                )
            shipment_id = active[0]["shipment_id"]

        if args.repair_duration_min is not None and not args.declared_eta_ts:
            return _json(
                {
                    "code": "REPAIR_IS_NOT_ETA",
                    "message": (
                        f"Repair duration ({args.repair_duration_min} min) is not a revised ETA. "
                        "Ask for the expected arrival date/time with timezone."
                    ),
                    "repair_duration_min": args.repair_duration_min,
                }
            )

        if not args.declared_eta_ts:
            return _json(
                {
                    "code": "CLARIFICATION_REQUIRED",
                    "message": "Need an explicit revised arrival timestamp with timezone.",
                }
            )

        cmd = EtaUpdateCommand(
            declared_eta_ts=args.declared_eta_ts,
            delay_reason_code=args.delay_reason_code,
            confidence_code=args.confidence_code,
            note=args.note,
            reported_delay_min=args.reported_delay_min,
            repair_duration_min=args.repair_duration_min,
            confirmed=args.confirmed,
            confirmation_eta_ts=args.confirmation_eta_ts,
            description=args.description,
            thread_id=thread_id,
            client_message_id=None,
        )

        if not args.confirmed:
            preview = confirmation_preview(cmd)
            preview["shipment_id"] = shipment_id
            return _json(preview)

        try:
            result = await record_eta_update(
                session,
                ctx=ctx,
                shipment_id=shipment_id,
                command=cmd,
                idempotency_key=f"chat-{thread_id}-{uuid4().hex[:16]}",
            )
            return _json(result)
        except Exception as exc:  # noqa: BLE001 — surface tool error codes to the model
            code = getattr(exc, "code", "ETA_WRITE_FAILED")
            return _json({"code": code, "message": str(exc)})

    async def find_feasible_slots(args: FindFeasibleSlotsArgs) -> str:
        shipment_id = args.shipment_id
        if not shipment_id:
            op_ctx = await driver_reads.get_driver_operational_context(session, ctx)
            primary = op_ctx.get("primary_shipment")
            if not primary:
                return _json({"code": "NO_ACTIVE_SHIPMENT", "message": "No active shipment found."})
            shipment_id = primary["shipment_id"]

        cmd = FeasibilitySearchCommand(
            shipment_id=shipment_id,
            target_date=args.target_date,
            after_time_ts=args.after_time_ts,
            revised_eta_ts=args.revised_eta_ts,
        )
        try:
            res = await find_feasible_slots_service(session, ctx, cmd)
            return _json(res.model_dump())
        except Exception as exc:
            code = getattr(exc, "code", "SLOT_SEARCH_FAILED")
            return _json({"code": code, "message": str(exc)})

    async def request_slot(args: RequestSlotArgs) -> str:
        shipment_id = args.shipment_id
        if not shipment_id:
            op_ctx = await driver_reads.get_driver_operational_context(session, ctx)
            primary = op_ctx.get("primary_shipment")
            if not primary:
                return _json({"code": "NO_ACTIVE_SHIPMENT", "message": "No active shipment found."})
            shipment_id = primary["shipment_id"]

        cmd = SlotBookingCommand(
            shipment_id=shipment_id,
            slot_id=args.slot_id,
            idempotency_key=f"chat-book-{thread_id}-{uuid4().hex[:12]}",
            note=args.note,
        )
        try:
            res = await request_slot_service(session, ctx, cmd)
            return _json(res.model_dump())
        except Exception as exc:
            code = getattr(exc, "code", "SLOT_BOOKING_FAILED")
            return _json({"code": code, "message": str(exc)})

    async def reschedule_appointment(args: RescheduleSlotArgs) -> str:
        cmd = RescheduleCommand(
            current_appointment_id=args.current_appointment_id,
            target_slot_id=args.target_slot_id,
            idempotency_key=f"chat-resched-{thread_id}-{uuid4().hex[:12]}",
            reason=args.reason,
        )
        try:
            res = await reschedule_appointment_service(session, ctx, cmd)
            return _json(res.model_dump())
        except Exception as exc:
            code = getattr(exc, "code", "RESCHEDULE_FAILED")
            return _json({"code": code, "message": str(exc)})

    async def cancel_appointment(args: CancelSlotArgs) -> str:
        cmd = CancelAppointmentCommand(
            appointment_id=args.appointment_id,
            idempotency_key=f"chat-cancel-{thread_id}-{uuid4().hex[:12]}",
            reason=args.reason,
        )
        try:
            res = await cancel_appointment_service(session, ctx, cmd)
            return _json(res)
        except Exception as exc:
            code = getattr(exc, "code", "CANCEL_FAILED")
            return _json({"code": code, "message": str(exc)})

    async def escalate_exception(args: EscalateExceptionArgs) -> str:
        shipment_id = args.shipment_id
        if not shipment_id:
            op_ctx = await driver_reads.get_driver_operational_context(session, ctx)
            primary = op_ctx.get("primary_shipment")
            if not primary:
                return _json({"code": "NO_ACTIVE_SHIPMENT", "message": "No active shipment found."})
            shipment_id = primary["shipment_id"]

        cmd = EscalationCommand(
            shipment_id=shipment_id,
            reason=args.reason,
            urgency="HIGH" if args.urgency not in ("NORMAL", "HIGH", "CRITICAL") else args.urgency, # type: ignore
        )
        try:
            res = await escalate_exception_service(session, ctx, cmd)
            return _json(res)
        except Exception as exc:
            code = getattr(exc, "code", "ESCALATION_FAILED")
            return _json({"code": code, "message": str(exc)})

    async def scheduling_capability_disabled(args: SchedulingArgs) -> str:
        return _json(
            {
                "code": "CAPABILITY_NOT_ENABLED",
                "message": (
                    "Slot search, booking, rescheduling, cancellation, and appointment "
                    "confirmation are not enabled in the Sprint 2 POC. Operations handoff required."
                ),
                "intent": args.intent,
                "shipment_id": args.shipment_id,
                "appointment_writes": 0,
            }
        )

    return [
        StructuredTool.from_function(
            coroutine=get_current_user_context,
            name="get_current_user_context",
            description="Return verified authenticated user/role/driver mapping.",
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_driver_operational_context,
            name="get_driver_operational_context",
            description="Return the driver's shipments, appointment, ETA, and facility context.",
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            coroutine=list_active_shipments,
            name="list_active_shipments",
            description="List the driver's active (non-completed) shipments.",
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_shipment_details,
            name="get_shipment_details",
            description="Get details for one in-scope shipment.",
            args_schema=ShipmentIdArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_latest_eta,
            name="get_latest_eta",
            description="Get the latest ETA update for a shipment.",
            args_schema=ShipmentIdArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_eta_history,
            name="get_eta_history",
            description="Get ETA history for a shipment.",
            args_schema=ShipmentIdArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_current_appointment,
            name="get_current_appointment",
            description="Get the current appointment observation for a shipment.",
            args_schema=ShipmentIdArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_facility_details,
            name="get_facility_details",
            description="Get facility details and contacts (driver-safe / scoped).",
            args_schema=FacilityIdArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_exception_status,
            name="get_exception_status",
            description="Get exception status for the driver, optionally filtered by shipment.",
            args_schema=ExceptionArgs,
        ),
        StructuredTool.from_function(
            coroutine=report_delay_or_update_eta,
            name="report_delay_or_update_eta",
            description=(
                "Report delay / update ETA. Requires explicit confirmation of the exact "
                "interpreted ETA. Repair duration is never an ETA."
            ),
            args_schema=ReportDelayArgs,
        ),
        StructuredTool.from_function(
            coroutine=find_feasible_slots,
            name="find_feasible_slots",
            description="Find feasible replacement dock slots based on ETA, dock specs, and facility rules.",
            args_schema=FindFeasibleSlotsArgs,
        ),
        StructuredTool.from_function(
            coroutine=request_slot,
            name="request_slot",
            description="Book an available dock slot for a shipment with atomic row-level locking.",
            args_schema=RequestSlotArgs,
        ),
        StructuredTool.from_function(
            coroutine=reschedule_appointment,
            name="reschedule_appointment",
            description="Reschedule an active appointment to a new target slot.",
            args_schema=RescheduleSlotArgs,
        ),
        StructuredTool.from_function(
            coroutine=cancel_appointment,
            name="cancel_appointment",
            description="Cancel an active appointment.",
            args_schema=CancelSlotArgs,
        ),
        StructuredTool.from_function(
            coroutine=escalate_exception,
            name="escalate_exception",
            description="Escalate an exception to operations team when automated slot search fails or human intervention is required.",
            args_schema=EscalateExceptionArgs,
        ),
    ]
