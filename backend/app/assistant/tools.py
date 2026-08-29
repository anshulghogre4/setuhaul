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
    cancel_appointment,
    get_appointment_request_status,
    request_slot,
)
from app.scheduling.feasibility import explain_slot_eligibility, find_feasible_slots
from app.scheduling.holds import confirm_held_slot
from app.services import driver_reads
from app.services.eta_service import EtaUpdateCommand, confirmation_preview, record_eta_update
from app.services.escalation_service import (
    EscalateExceptionCommand,
    escalate_exception,
    persist_noslot_escalation,
)
from app.services.redis_memory import ConversationMemory

# E3.1 (issue #25): SOLUTION_DESIGN.md section 7.5.4's 12-tool driver allowlist, enumerated
# there because "Appendix A argues for shrinking the driver tool surface... that claim is only
# actionable if the list is named."
#
# Issue #53 closed the last gap: `confirm_held_slot` is now bound, so this is 12 of 12. Section
# 7.5.4's own note on why the list is 12 rather than 9 -- "`confirm_held_slot` and
# `explain_slot_eligibility` are new and both are load-bearing" -- is now satisfied by both.
#
# The tool is bound unconditionally, not behind `TWO_PHASE_HOLD_ENABLED`. That is deliberate: with
# the flag off no hold can exist, so every call returns HOLD_NOT_FOUND -- a truthful refusal the
# model can narrate. Varying the *tool surface* by config would instead make the assistant's
# schema differ between deploys, which is the thing Appendix A's token/selection-accuracy argument
# is about keeping stable.
DRIVER_ALLOWLIST = frozenset(
    {
        "get_driver_operational_context",
        "list_active_shipments",
        "get_latest_eta",
        "get_current_appointment",
        "report_delay_or_update_eta",
        "find_feasible_slots",
        "request_slot",
        "confirm_held_slot",
        "get_appointment_request_status",
        "explain_slot_eligibility",
        "cancel_appointment",
        "escalate_exception",
    }
)


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ShipmentIdArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str = Field(description="Shipment identifier, e.g. SHP1017")


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


class ConfirmHeldSlotArgs(BaseModel):
    """Section 7.1: "takes the hold id, revalidates inside the transaction, and produces
    PENDING_CONFIRMATION" (issue #53).

    One argument, deliberately. Section 7.5's first principle is that scope is derived from the
    authenticated identity and never from an argument (M15); `hold_id` selects *within* the
    caller's scope and is validated against it server-side. Adding a `shipment_id` here "for
    convenience" would reintroduce exactly the hole that principle exists to close.
    """

    model_config = ConfigDict(extra="ignore")
    hold_id: str = Field(description="hold_id returned by request_slot's HELD outcome")
    note: str | None = Field(default=None, description="Optional driver note for the request")


class SlotEligibilityArgs(BaseModel):
    """E3.1 (issue #25), FR-DRV-006: browse-only, no exception created."""

    model_config = ConfigDict(extra="ignore")
    shipment_id: str = Field(description="Shipment the slot is being considered for")
    slot_id: str = Field(description="Exact slot_id to explain eligibility for")


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


class EscalateExceptionArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shipment_id: str
    escalation_type: str = Field(default="NO_FEASIBLE_SLOT")
    reason: str | None = None
    confirmed: bool = Field(
        default=False,
        description=(
            "Leave false on the first call to get a CONFIRMATION_REQUIRED preview with no write. "
            "Only set true after the driver has explicitly confirmed they want this shipment "
            "escalated to human operations."
        ),
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
    """Role-scoped POC tools for ChatOpenAI.bind_tools (driver allowlist).

    E3.1 (issue #25): binds `DRIVER_ALLOWLIST` -- 11 of SOLUTION_DESIGN.md section 7.5.4's
    12-tool allowlist (`confirm_held_slot` deferred, its own build). Previously bound 23 tools,
    essentially the whole multi-role catalog; the other 12 either fold into the pre-fetched
    `get_driver_operational_context` payload or are deferred to a second-tier catalog per
    section 7.5.4's own reasoning (schema tokens on every call, degraded selection accuracy --
    TECH_STACK.md section 10 latency lever 2). `reschedule_appointment` is removed entirely,
    not folded: D1 collapses a reschedule into two interval operations (cancel_appointment then
    request_slot on a fresh slot), both of which are already in this allowlist, so no stub tool
    is needed for the LLM to accomplish the same outcome -- see prompts.py's matching update.
    """

    def _displayed_recommendation_id(explicit: str | None, shipment_id: str) -> str | None:
        if explicit:
            return explicit
        if memory is None:
            return None
        return memory.get_active_recommendation(user_id=ctx.user_id, shipment_id=shipment_id)

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

    async def get_latest_eta(args: ShipmentIdArgs | None = None, **kwargs: Any) -> str:
        try:
            parsed = args if isinstance(args, ShipmentIdArgs) else ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_latest_eta(session, ctx, parsed.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

    async def get_current_appointment(args: ShipmentIdArgs | None = None, **kwargs: Any) -> str:
        try:
            parsed = args if isinstance(args, ShipmentIdArgs) else ShipmentIdArgs.model_validate(kwargs)
            return _json(await driver_reads.get_current_appointment(session, ctx, parsed.shipment_id))
        except Exception as exc:  # noqa: BLE001
            return _tool_error(exc)

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
                        "dedupe_key": f"{shipment_id}:{persisted.get('created_at', '')[:10]}:NO_FEASIBLE_SLOT",
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

    async def confirm_held_slot_tool(args: ConfirmHeldSlotArgs | None = None, **kwargs: Any) -> str:
        parsed_args = (
            args if isinstance(args, ConfirmHeldSlotArgs) else ConfirmHeldSlotArgs.model_validate(kwargs)
        )
        try:
            result = await confirm_held_slot(
                session,
                ctx,
                # `hold_id` is the *only* identifier this tool accepts, and that is M15, not
                # minimalism: shipment, slot, dock and facility are all read off the held row
                # server-side. A `shipment_id` argument here would let a caller pair someone
                # else's hold id with their own shipment id and pass the scope check.
                hold_id=parsed_args.hold_id,
                note=parsed_args.note,
                idempotency_key=chat_mutation_idempotency_key(
                    thread_id=thread_id,
                    action="confirm-held-slot",
                    parts=[parsed_args.hold_id],
                    client_message_id=client_message_id,
                ),
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model
            code = getattr(exc, "code", "CONFIRM_HELD_SLOT_FAILED")
            return _json({"code": code, "message": str(exc), "appointment_writes": 0})

    async def explain_slot_eligibility_tool(args: SlotEligibilityArgs | None = None, **kwargs: Any) -> str:
        parsed_args = args if isinstance(args, SlotEligibilityArgs) else SlotEligibilityArgs.model_validate(kwargs)
        try:
            result = await explain_slot_eligibility(
                session, ctx, parsed_args.shipment_id, parsed_args.slot_id
            )
            return _json(result.model_dump())
        except Exception as exc:  # noqa: BLE001 - return stable tool error to the model, browse-only
            return _tool_error(exc)

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
                    confirmed=parsed_args.confirmed,
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

    tools = [
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
            coroutine=get_latest_eta,
            name="get_latest_eta",
            description="Get the latest ETA update for a shipment.",
            args_schema=ShipmentIdArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_current_appointment,
            name="get_current_appointment",
            description="Get the current appointment observation for a shipment.",
            args_schema=ShipmentIdArgs,
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
                "chooses a slot_id. Revalidates transactionally. Returns either SLOT_HELD with a "
                "hold_id reserved for ~90 seconds (then call confirm_held_slot to commit it) or "
                "SLOT_REQUESTED at PENDING_CONFIRMATION, depending on deployment. It never confirms "
                "the appointment. A hold is NOT a booking -- never tell the driver a held slot is "
                "booked or confirmed."
            ),
            args_schema=RequestSlotArgs,
        ),
        StructuredTool.from_function(
            coroutine=confirm_held_slot_tool,
            name="confirm_held_slot",
            description=(
                "Commit a slot the driver is already holding, using the hold_id returned by "
                "request_slot. Revalidates transactionally and produces PENDING_CONFIRMATION; it "
                "never confirms the appointment (a human does that). Refuses with HOLD_EXPIRED if "
                "the 90-second reservation lapsed. Do not call this without a hold_id from this "
                "conversation."
            ),
            args_schema=ConfirmHeldSlotArgs,
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
            coroutine=explain_slot_eligibility_tool,
            name="explain_slot_eligibility",
            description=(
                "Explain, per invariant, why one specific slot_id is or is not eligible for a "
                "shipment. Browse-only: never books, holds, or creates an exception/escalation."
            ),
            args_schema=SlotEligibilityArgs,
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
            coroutine=escalate_exception_tool,
            name="escalate_exception",
            description="Create a durable human operations escalation for an in-scope shipment.",
            args_schema=EscalateExceptionArgs,
        ),
    ]
    assert {t.name for t in tools} == DRIVER_ALLOWLIST, (
        "build_driver_tools drifted from DRIVER_ALLOWLIST -- keep the two in sync, "
        "the allowlist constant is what E3.1's own tests assert against."
    )
    return tools
