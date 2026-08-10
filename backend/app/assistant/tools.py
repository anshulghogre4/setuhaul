from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.execution_context import ExecutionContext
from app.scheduling.allocation import RequestSlotCommand, get_appointment_request_status, request_slot
from app.scheduling.feasibility import find_feasible_slots
from app.services import driver_reads
from app.services.eta_service import EtaUpdateCommand, confirmation_preview, record_eta_update


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
    shipment_id: str | None = Field(
        default=None,
        description="Shipment to evaluate. Required when the driver has multiple active shipments.",
    )
    limit: int = Field(default=5, ge=1, le=10, description="Maximum number of slot options to return")


class RequestSlotArgs(BaseModel):
    shipment_id: str = Field(description="Shipment for the selected slot")
    slot_id: str = Field(description="Exact slot_id selected from find_feasible_slots")
    displayed_policy_version: str | None = Field(default=None)
    note: str | None = Field(default=None, description="Optional driver note for the request")


class AppointmentRequestStatusArgs(BaseModel):
    shipment_id: str | None = Field(
        default=None,
        description="Shipment whose appointment request status should be checked.",
    )
    appointment_id: str | None = Field(
        default=None,
        description="Optional appointment_id returned by request_slot.",
    )


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

    async def find_feasible_slots_tool(args: FindFeasibleSlotsArgs) -> str:
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
                        "message": "Multiple active shipments. Ask which shipment_id to evaluate.",
                        "candidates": [
                            {"shipment_id": s["shipment_id"], "status": s["current_status"]}
                            for s in active
                        ],
                    }
                )
            shipment_id = active[0]["shipment_id"]

        try:
            result = await find_feasible_slots(session, ctx, shipment_id, limit=args.limit)
            payload = result.model_dump()
            payload["code"] = "FEASIBLE_SLOTS_FOUND" if payload["options"] else "NO_FEASIBLE_SLOTS"
            payload["appointment_writes"] = 0
            return _json(payload)
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "FEASIBILITY_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def request_slot_tool(args: RequestSlotArgs) -> str:
        command = RequestSlotCommand(
            note=args.note,
            displayed_policy_version=args.displayed_policy_version,
            client_message_id=None,
        )
        try:
            result = await request_slot(
                session,
                ctx,
                shipment_id=args.shipment_id,
                slot_id=args.slot_id,
                command=command,
                idempotency_key=f"chat-{thread_id}-request-slot-{args.shipment_id}-{args.slot_id}",
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "REQUEST_SLOT_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def get_appointment_request_status_tool(args: AppointmentRequestStatusArgs) -> str:
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
                        "message": "Multiple active shipments. Ask which shipment_id to check.",
                        "candidates": [
                            {"shipment_id": s["shipment_id"], "status": s["current_status"]}
                            for s in active
                        ],
                    }
                )
            shipment_id = active[0]["shipment_id"]

        try:
            result = await get_appointment_request_status(
                session,
                ctx,
                shipment_id=shipment_id,
                appointment_id=args.appointment_id,
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "APPOINTMENT_REQUEST_STATUS_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def scheduling_capability_disabled(args: SchedulingArgs) -> str:
        return _json(
            {
                "code": "CAPABILITY_NOT_ENABLED",
                "message": (
                    "Rescheduling, cancellation, and appointment confirmation are not enabled "
                    "until their Sprint 3 transactional services are complete. Use request_slot "
                    "only for a driver's explicit selected slot request."
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
            coroutine=find_feasible_slots_tool,
            name="find_feasible_slots",
            description=(
                "Find fresh, explainable, non-reserved feasible replacement slot options for "
                "an in-scope shipment. This never books, holds, reserves, confirms, or mutates appointments."
            ),
            args_schema=FindFeasibleSlotsArgs,
        ),
        StructuredTool.from_function(
            coroutine=request_slot_tool,
            name="request_slot",
            description=(
                "Request an exact selected slot for an in-scope shipment after the driver explicitly "
                "chooses a slot_id. Revalidates transactionally and creates PENDING_CONFIRMATION only; "
                "it never confirms the appointment."
            ),
            args_schema=RequestSlotArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_appointment_request_status_tool,
            name="get_appointment_request_status",
            description=(
                "Check the authoritative status of a prior slot request for an in-scope shipment. "
                "Reports pending confirmation, confirmed, cancelled, rejected, completed, or no request; "
                "it never mutates appointments."
            ),
            args_schema=AppointmentRequestStatusArgs,
        ),
        StructuredTool.from_function(
            coroutine=scheduling_capability_disabled,
            name="scheduling_capability_disabled",
            description=(
                "Return CAPABILITY_NOT_ENABLED for reschedule/cancel/confirm mutations."
            ),
            args_schema=SchedulingArgs,
        ),
    ]
