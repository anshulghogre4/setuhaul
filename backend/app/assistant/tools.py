from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.scheduling.allocation import (
    CancelAppointmentCommand,
    RequestSlotCommand,
    RescheduleAppointmentCommand,
    cancel_appointment,
    get_appointment_request_status,
    request_slot,
    reschedule_appointment,
)
from app.scheduling.feasibility import find_feasible_slots
from app.services import driver_reads
from app.services.eta_service import EtaUpdateCommand, confirmation_preview, record_eta_update
from app.services.escalation_service import (
    EscalateExceptionCommand,
    escalate_exception,
    persist_noslot_escalation,
)
from app.services.redis_memory import ConversationMemory


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ShipmentIdArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str = Field(description="Shipment identifier, e.g. SHP1017")


class FacilityIdArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    facility_id: str = Field(description="Facility identifier, e.g. FAC-JAI-01")


class ExceptionArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str | None = Field(default=None, description="Optional shipment filter")


class ReportDelayArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
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
    model_config = ConfigDict(extra="ignore")
    intent: str = Field(description="Requested scheduling action")
    shipment_id: str | None = None


class FindFeasibleSlotsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str | None = Field(
        default=None,
        description="Shipment to evaluate. Required when the driver has multiple active shipments.",
    )
    limit: int = Field(default=5, ge=1, le=10, description="Maximum number of slot options to return")


class RequestSlotArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str = Field(description="Shipment for the selected slot")
    slot_id: str = Field(description="Exact slot_id selected from find_feasible_slots")
    displayed_policy_version: str | None = Field(default=None)
    displayed_recommendation_id: str | None = Field(default=None)
    note: str | None = Field(default=None, description="Optional driver note for the request")


class AppointmentRequestStatusArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str | None = Field(
        default=None,
        description="Shipment whose appointment request status should be checked.",
    )
    appointment_id: str | None = Field(
        default=None,
        description="Optional appointment_id returned by request_slot.",
    )


class CancelAppointmentArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str = Field(description="Shipment whose current appointment should be cancelled.")
    appointment_id: str = Field(description="Exact current appointment_id to cancel.")
    cancellation_reason: str = Field(
        min_length=1,
        max_length=500,
        description="Driver-provided reason for cancellation.",
    )


class RescheduleAppointmentArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str
    appointment_id: str
    new_slot_id: str
    displayed_policy_version: str | None = None
    displayed_recommendation_id: str | None = None
    note: str | None = None


class EscalateExceptionArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str
    escalation_type: str = Field(default="NO_SLOT")
    reason: str | None = None


class ConversationMemoryArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    include_recent_messages: bool = Field(
        default=True,
        description="Whether to include bounded recent chat snippets from Redis.",
    )


def _json(data: Any) -> str:
    return json.dumps(data, default=str)


def _tool_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return _json(
            {
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
                "status_code": exc.status_code,
            }
        )
    return _json({"code": "TOOL_ERROR", "message": str(exc)[:300]})


def build_driver_tools(
    *,
    session: AsyncSession,
    ctx: ExecutionContext,
    thread_id: str,
    session_id: str | None = None,
    memory: ConversationMemory | None = None,
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

    async def get_conversation_memory(**kwargs: Any) -> str:
        args = ConversationMemoryArgs.model_validate(kwargs)
        if memory is None:
            return _json(
                {
                    "code": "REDIS_MEMORY_UNAVAILABLE",
                    "source": "upstash_redis",
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "recent_messages": [],
                    "session": {},
                    "ttl_seconds": 24 * 60 * 60,
                    "non_authoritative": True,
                    "degraded": True,
                    "degrade_reason": "MEMORY_NOT_ATTACHED_TO_TOOL",
                }
            )
        return _json(
            memory.snapshot(
                user_id=ctx.user_id,
                thread_id=thread_id,
                session_id=session_id,
                include_recent_messages=args.include_recent_messages,
            )
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

    async def get_shipment_details(**kwargs: Any) -> str:
        try:
            args = ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_shipment_details(session, ctx, args.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_latest_eta(**kwargs: Any) -> str:
        try:
            args = ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_latest_eta(session, ctx, args.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_eta_history(**kwargs: Any) -> str:
        try:
            args = ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_eta_history(session, ctx, args.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_current_appointment(**kwargs: Any) -> str:
        try:
            args = ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_current_appointment(session, ctx, args.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_facility_details(**kwargs: Any) -> str:
        try:
            args = FacilityIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_facility_details(session, ctx, args.facility_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_exception_status(**kwargs: Any) -> str:
        args = ExceptionArgs.model_validate(kwargs)
        return _json(await driver_reads.get_exception_status(session, ctx, args.shipment_id))

    async def report_delay_or_update_eta(**kwargs: Any) -> str:
        args = ReportDelayArgs.model_validate(kwargs)
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

    async def find_feasible_slots_tool(**kwargs: Any) -> str:
        args = FindFeasibleSlotsArgs.model_validate(kwargs)
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
            if memory is not None:
                memory.store_active_recommendation(
                    user_id=ctx.user_id,
                    shipment_id=shipment_id,
                    recommendation_id=result.recommendation_id,
                )
            payload = result.model_dump()
            payload["code"] = "FEASIBLE_SLOTS_FOUND" if payload["options"] else "NO_FEASIBLE_SLOTS"
            payload["appointment_writes"] = 0
            if payload["code"] == "NO_FEASIBLE_SLOTS":
                escalation = dict(payload.get("escalation") or {})
                escalation["recommendation_id"] = result.recommendation_id
                try:
                    persisted = await persist_noslot_escalation(
                        session,
                        ctx=ctx,
                        shipment_id=shipment_id,
                        facility_id=str(payload.get("facility_id") or ""),
                        driver_id=ctx.driver_id,
                        payload=escalation,
                    )
                    payload["persisted_escalation"] = {
                        "escalation_id": persisted.get("escalation_id"),
                        "escalation_status": persisted.get("escalation_status"),
                        "dedupe_key": f"{shipment_id}:{persisted.get('created_at', '')[:10]}:NO_SLOT",
                    }
                except Exception as escalate_exc:  # noqa: BLE001 — feasibility still returns
                    payload["persisted_escalation_error"] = {
                        "code": getattr(escalate_exc, "code", "ESCALATION_PERSIST_FAILED"),
                        "message": str(escalate_exc),
                    }
                payload["user_facing_summary"] = (
                    "No shipment-feasible replacement slots were found for the current "
                    "declared ETA and unload constraints. This is a structured no-feasible "
                    "result, not a transport failure. Use blocking_reasons and "
                    "recommended_human_queue from escalation."
                )
            else:
                payload["user_facing_summary"] = (
                    f"{len(payload['options'])} DISPLAYED_NOT_RESERVED options found. "
                    "They are not reserved and not a confirmed booking."
                )
            return _json(payload)
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "FEASIBILITY_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def request_slot_tool(**kwargs: Any) -> str:
        args = RequestSlotArgs.model_validate(kwargs)
        command = RequestSlotCommand(
            note=args.note,
            displayed_policy_version=args.displayed_policy_version,
            displayed_recommendation_id=args.displayed_recommendation_id,
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

    async def reschedule_appointment_tool(**kwargs: Any) -> str:
        args = RescheduleAppointmentArgs.model_validate(kwargs)
        try:
            result = await reschedule_appointment(
                session, ctx, shipment_id=args.shipment_id,
                command=RescheduleAppointmentCommand(
                    appointment_id=args.appointment_id, new_slot_id=args.new_slot_id,
                    note=args.note, displayed_policy_version=args.displayed_policy_version,
                    displayed_recommendation_id=args.displayed_recommendation_id,
                ),
                idempotency_key=f"chat-{thread_id}-reschedule-{args.appointment_id}-{args.new_slot_id}",
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", "RESCHEDULE_APPOINTMENT_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def escalate_exception_tool(**kwargs: Any) -> str:
        args = EscalateExceptionArgs.model_validate(kwargs)
        try:
            result = await escalate_exception(
                session, ctx,
                EscalateExceptionCommand(
                    shipment_id=args.shipment_id, escalation_type=args.escalation_type,
                    payload={"reason": args.reason, "source": "driver_chat"},
                ),
            )
            return _json(result)
        except Exception as exc:  # noqa: BLE001
            return _json({"code": getattr(exc, "code", "ESCALATION_FAILED"), "message": str(exc)})

    async def get_appointment_request_status_tool(**kwargs: Any) -> str:
        args = AppointmentRequestStatusArgs.model_validate(kwargs)
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

    async def cancel_appointment_tool(**kwargs: Any) -> str:
        args = CancelAppointmentArgs.model_validate(kwargs)
        command = CancelAppointmentCommand(
            appointment_id=args.appointment_id,
            cancellation_reason=args.cancellation_reason,
            client_message_id=None,
        )
        try:
            result = await cancel_appointment(
                session,
                ctx,
                shipment_id=args.shipment_id,
                command=command,
                idempotency_key=(
                    f"chat-{thread_id}-cancel-appointment-{args.shipment_id}-"
                    f"{args.appointment_id}"
                ),
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "CANCEL_APPOINTMENT_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def scheduling_capability_disabled(**kwargs: Any) -> str:
        args = SchedulingArgs.model_validate(kwargs)
        return _json(
            {
                "code": "CAPABILITY_NOT_ENABLED",
                "message": (
                    "Rescheduling and appointment confirmation are not enabled for the Driver "
                    "assistant. Confirmation remains an operations/warehouse action."
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
            coroutine=get_conversation_memory,
            name="get_conversation_memory",
            description=(
                "Return bounded Upstash Redis conversation/session memory for this authenticated "
                "user, browser session, and thread — including rolling summaries of older turns when present. "
                "This is ephemeral, 24-hour, non-authoritative context only; "
                "never use it as shipment, ETA, appointment, dock, or facility truth."
            ),
            args_schema=ConversationMemoryArgs,
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
            coroutine=cancel_appointment_tool,
            name="cancel_appointment",
            description=(
                "Cancel the exact current active appointment for an in-scope shipment after the "
                "driver explicitly asks to cancel and provides a reason. This releases the slot "
                "for fresh scheduling searches; it never reschedules or confirms another slot."
            ),
            args_schema=CancelAppointmentArgs,
        ),
        StructuredTool.from_function(
            coroutine=reschedule_appointment_tool,
            name="reschedule_appointment",
            description=(
                "Replace the driver's current active appointment with an explicitly selected fresh "
                "slot option. It revalidates capacity and creates PENDING_CONFIRMATION only."
            ),
            args_schema=RescheduleAppointmentArgs,
        ),
        StructuredTool.from_function(
            coroutine=escalate_exception_tool,
            name="escalate_exception",
            description="Create a durable human operations escalation for an in-scope shipment.",
            args_schema=EscalateExceptionArgs,
        ),
        StructuredTool.from_function(
            coroutine=scheduling_capability_disabled,
            name="scheduling_capability_disabled",
            description=(
                "Return CAPABILITY_NOT_ENABLED for reschedule or driver confirmation mutations."
            ),
            args_schema=SchedulingArgs,
        ),
    ]
