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


class VehicleCarrierArgs(BaseModel):
    shipment_id: str | None = Field(
        default=None,
        description="Shipment ID to query vehicle, payload capacity, and carrier details for.",
    )


class GateQueueArgs(BaseModel):
    shipment_id: str | None = Field(
        default=None,
        description="Shipment ID to check yard queue position and gate check-in status.",
    )


class FacilityRulesArgs(BaseModel):
    facility_id: str | None = Field(
        default=None,
        description="Facility ID to query safety rules, grace periods, and procedures for.",
    )
    shipment_id: str | None = Field(
        default=None,
        description="Optional shipment ID to derive destination facility ID.",
    )


class ReportIncidentArgs(BaseModel):
    shipment_id: str | None = Field(
        default=None,
        description="Shipment ID associated with the breakdown or vehicle incident.",
    )
    incident_type: str = Field(
        default="BREAKDOWN",
        description="Incident type: BREAKDOWN, TRAFFIC, WEATHER, DELAY, ACCIDENT, OTHER.",
    )
    description: str = Field(
        default="",
        description="Detailed description of the breakdown or vehicle incident.",
    )
    reported_delay_min: int | None = Field(
        default=None,
        description="Optional estimated delay in minutes caused by the breakdown.",
    )


class DockMaintenanceArgs(BaseModel):
    facility_id: str | None = Field(
        default=None,
        description="Facility ID to check active dock maintenance alerts for.",
    )
    dock_id: str | None = Field(
        default=None,
        description="Optional dock ID to filter specific dock maintenance alerts.",
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


def chat_mutation_idempotency_key(
    *,
    thread_id: str,
    action: str,
    parts: list[str],
    client_message_id: str | None,
) -> str:
    """Per-turn chat mutation key so cancel→rebook is not a sticky replay."""
    suffix = (client_message_id or "").strip() or uuid4().hex[:16]
    joined = "-".join(part for part in parts if part)
    return f"chat-{thread_id}-{action}-{joined}-{suffix}"


def build_driver_tools(
    *,
    session: AsyncSession,
    ctx: ExecutionContext,
    thread_id: str,
    session_id: str | None = None,
    memory: ConversationMemory | None = None,
    client_message_id: str | None = None,
) -> list[StructuredTool]:
    """Role-scoped POC tools for ChatOpenAI.bind_tools (driver allowlist)."""

    def _displayed_recommendation_id(explicit: str | None, shipment_id: str) -> str | None:
        if explicit:
            return explicit
        if memory is None:
            return None
        return memory.get_active_recommendation(user_id=ctx.user_id, shipment_id=shipment_id)

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

    async def get_shipment_details(args: ShipmentIdArgs | None = None, **kwargs: Any) -> str:
        try:
            parsed = args if isinstance(args, ShipmentIdArgs) else ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_shipment_details(session, ctx, parsed.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_latest_eta(args: ShipmentIdArgs | None = None, **kwargs: Any) -> str:
        try:
            parsed = args if isinstance(args, ShipmentIdArgs) else ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_latest_eta(session, ctx, parsed.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_eta_history(args: ShipmentIdArgs | None = None, **kwargs: Any) -> str:
        try:
            parsed = args if isinstance(args, ShipmentIdArgs) else ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_eta_history(session, ctx, parsed.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_current_appointment(args: ShipmentIdArgs | None = None, **kwargs: Any) -> str:
        try:
            parsed = args if isinstance(args, ShipmentIdArgs) else ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_current_appointment(session, ctx, parsed.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_facility_details(args: FacilityIdArgs | None = None, **kwargs: Any) -> str:
        try:
            parsed = args if isinstance(args, FacilityIdArgs) else FacilityIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_facility_details(session, ctx, parsed.facility_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_exception_status(args: ExceptionArgs | None = None, **kwargs: Any) -> str:
        parsed = args if isinstance(args, ExceptionArgs) else ExceptionArgs.model_validate(kwargs)
        return _json(await driver_reads.get_exception_status(session, ctx, parsed.shipment_id))

    async def report_delay_or_update_eta(args: ReportDelayArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, ReportDelayArgs) else ReportDelayArgs.model_validate(kwargs)
        context = await driver_reads.get_driver_operational_context(session, ctx)
        active = context.get("active_shipments") or []
        shipment_id = parsed_args.shipment_id
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

        if parsed_args.repair_duration_min is not None and not parsed_args.declared_eta_ts:
            return _json(
                {
                    "code": "REPAIR_IS_NOT_ETA",
                    "message": (
                        f"Repair duration ({parsed_args.repair_duration_min} min) is not a revised ETA. "
                        "Ask for the expected arrival date/time with timezone."
                    ),
                    "repair_duration_min": parsed_args.repair_duration_min,
                }
            )

        if not parsed_args.declared_eta_ts:
            return _json(
                {
                    "code": "CLARIFICATION_REQUIRED",
                    "message": "Need an explicit revised arrival timestamp with timezone.",
                }
            )

        cmd = EtaUpdateCommand(
            declared_eta_ts=parsed_args.declared_eta_ts,
            delay_reason_code=parsed_args.delay_reason_code,
            confidence_code=parsed_args.confidence_code,
            note=parsed_args.note,
            reported_delay_min=parsed_args.reported_delay_min,
            repair_duration_min=parsed_args.repair_duration_min,
            confirmed=parsed_args.confirmed,
            confirmation_eta_ts=parsed_args.confirmation_eta_ts,
            description=parsed_args.description,
            thread_id=thread_id,
            client_message_id=None,
        )

        if not parsed_args.confirmed:
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

    async def find_feasible_slots_tool(args: FindFeasibleSlotsArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, FindFeasibleSlotsArgs) else FindFeasibleSlotsArgs.model_validate(kwargs)
        context = await driver_reads.get_driver_operational_context(session, ctx)
        active = context.get("active_shipments") or []
        shipment_id = parsed_args.shipment_id
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
            result = await find_feasible_slots(session, ctx, shipment_id, limit=parsed_args.limit)
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

    async def request_slot_tool(args: RequestSlotArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, RequestSlotArgs) else RequestSlotArgs.model_validate(kwargs)
        rec_id = _displayed_recommendation_id(
            parsed_args.displayed_recommendation_id, parsed_args.shipment_id
        )
        command = RequestSlotCommand(
            note=parsed_args.note,
            displayed_policy_version=parsed_args.displayed_policy_version,
            displayed_recommendation_id=rec_id,
            client_message_id=client_message_id,
        )
        try:
            result = await request_slot(
                session,
                ctx,
                shipment_id=parsed_args.shipment_id,
                slot_id=parsed_args.slot_id,
                command=command,
                idempotency_key=chat_mutation_idempotency_key(
                    thread_id=thread_id,
                    action="request-slot",
                    parts=[parsed_args.shipment_id, parsed_args.slot_id],
                    client_message_id=client_message_id,
                ),
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "REQUEST_SLOT_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def reschedule_appointment_tool(args: RescheduleAppointmentArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, RescheduleAppointmentArgs) else RescheduleAppointmentArgs.model_validate(kwargs)
        rec_id = _displayed_recommendation_id(
            parsed_args.displayed_recommendation_id, parsed_args.shipment_id
        )
        try:
            result = await reschedule_appointment(
                session,
                ctx,
                shipment_id=parsed_args.shipment_id,
                command=RescheduleAppointmentCommand(
                    appointment_id=parsed_args.appointment_id,
                    new_slot_id=parsed_args.new_slot_id,
                    note=parsed_args.note,
                    displayed_policy_version=parsed_args.displayed_policy_version,
                    displayed_recommendation_id=rec_id,
                    client_message_id=client_message_id,
                ),
                idempotency_key=chat_mutation_idempotency_key(
                    thread_id=thread_id,
                    action="reschedule",
                    parts=[parsed_args.appointment_id, parsed_args.new_slot_id],
                    client_message_id=client_message_id,
                ),
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", "RESCHEDULE_APPOINTMENT_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def escalate_exception_tool(args: EscalateExceptionArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, EscalateExceptionArgs) else EscalateExceptionArgs.model_validate(kwargs)
        try:
            result = await escalate_exception(
                session,
                ctx,
                EscalateExceptionCommand(
                    shipment_id=parsed_args.shipment_id,
                    escalation_type=parsed_args.escalation_type,
                    payload={"reason": parsed_args.reason, "source": "driver_chat"},
                ),
            )
            return _json(result)
        except Exception as exc:  # noqa: BLE001
            return _json({"code": getattr(exc, "code", "ESCALATION_FAILED"), "message": str(exc)})

    async def get_appointment_request_status_tool(args: AppointmentRequestStatusArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, AppointmentRequestStatusArgs) else AppointmentRequestStatusArgs.model_validate(kwargs)
        context = await driver_reads.get_driver_operational_context(session, ctx)
        active = context.get("active_shipments") or []
        shipment_id = parsed_args.shipment_id
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
                appointment_id=parsed_args.appointment_id,
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "APPOINTMENT_REQUEST_STATUS_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def cancel_appointment_tool(args: CancelAppointmentArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, CancelAppointmentArgs) else CancelAppointmentArgs.model_validate(kwargs)
        command = CancelAppointmentCommand(
            appointment_id=parsed_args.appointment_id,
            cancellation_reason=parsed_args.cancellation_reason,
            client_message_id=None,
        )
        try:
            result = await cancel_appointment(
                session,
                ctx,
                shipment_id=parsed_args.shipment_id,
                command=command,
                idempotency_key=(
                    f"chat-{thread_id}-cancel-appointment-{parsed_args.shipment_id}-"
                    f"{parsed_args.appointment_id}"
                ),
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "CANCEL_APPOINTMENT_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def scheduling_capability_disabled(args: SchedulingArgs | None = None, **kwargs: Any) -> str:
        parsed = args if isinstance(args, SchedulingArgs) else SchedulingArgs.model_validate(kwargs)
        return _json(
            {
                "code": "CAPABILITY_NOT_ENABLED",
                "message": (
                    "Rescheduling and appointment confirmation are not enabled for the Driver "
                    "assistant. Confirmation remains an operations/warehouse action."
                ),
                "intent": parsed.intent,
                "shipment_id": parsed.shipment_id,
                "appointment_writes": 0,
            }
        )

    async def get_vehicle_and_carrier_details(args: VehicleCarrierArgs | None = None, **kwargs: Any) -> str:
        parsed = args if isinstance(args, VehicleCarrierArgs) else VehicleCarrierArgs.model_validate(kwargs)
        return _json(await driver_reads.get_vehicle_and_carrier_details(session, ctx, parsed.shipment_id))

    async def get_gate_and_queue_status(args: GateQueueArgs | None = None, **kwargs: Any) -> str:
        parsed = args if isinstance(args, GateQueueArgs) else GateQueueArgs.model_validate(kwargs)
        return _json(await driver_reads.get_gate_and_queue_status(session, ctx, parsed.shipment_id))

    async def get_facility_rules_and_restrictions(args: FacilityRulesArgs | None = None, **kwargs: Any) -> str:
        parsed = args if isinstance(args, FacilityRulesArgs) else FacilityRulesArgs.model_validate(kwargs)
        return _json(await driver_reads.get_facility_rules_and_restrictions(session, ctx, parsed.facility_id, parsed.shipment_id))

    async def report_vehicle_breakdown_or_incident(args: ReportIncidentArgs | None = None, **kwargs: Any) -> str:
        parsed = args if isinstance(args, ReportIncidentArgs) else ReportIncidentArgs.model_validate(kwargs)
        return _json(
            await driver_reads.report_vehicle_breakdown_or_incident(
                session, ctx, parsed.shipment_id, parsed.incident_type, parsed.description, parsed.reported_delay_min, thread_id=thread_id
            )
        )

    async def get_dock_maintenance_alerts(args: DockMaintenanceArgs | None = None, **kwargs: Any) -> str:
        parsed = args if isinstance(args, DockMaintenanceArgs) else DockMaintenanceArgs.model_validate(kwargs)
        return _json(await driver_reads.get_dock_maintenance_alerts(session, ctx, parsed.facility_id, parsed.dock_id))

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
            coroutine=get_vehicle_and_carrier_details,
            name="get_vehicle_and_carrier_details",
            description="Get assigned vehicle registration, payload capacity kg, refrigeration capability, and carrier contact details.",
            args_schema=VehicleCarrierArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_gate_and_queue_status,
            name="get_gate_and_queue_status",
            description="Get gate check-in status, yard queue position, arrival state, and dock assignment.",
            args_schema=GateQueueArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_facility_rules_and_restrictions,
            name="get_facility_rules_and_restrictions",
            description="Get facility safety rules, policies, gate procedures, and check-in grace periods.",
            args_schema=FacilityRulesArgs,
        ),
        StructuredTool.from_function(
            coroutine=report_vehicle_breakdown_or_incident,
            name="report_vehicle_breakdown_or_incident",
            description="Report a roadside vehicle breakdown, accident, or emergency incident to dispatch.",
            args_schema=ReportIncidentArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_dock_maintenance_alerts,
            name="get_dock_maintenance_alerts",
            description="Get active dock maintenance alerts, outages, or capacity reduction events for a facility.",
            args_schema=DockMaintenanceArgs,
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

