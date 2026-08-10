from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.services.ids import new_id
from app.services.scheduling.schemas import EscalationCommand


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def escalate_exception_service(
    session: AsyncSession,
    ctx: ExecutionContext,
    command: EscalationCommand,
) -> dict[str, Any]:
    # 1. Fetch Shipment
    shipment = (
        await session.execute(
            text(
                """
                SELECT shipment_id, driver_id, destination_facility_id
                FROM public.shipments WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": command.shipment_id},
        )
    ).mappings().first()

    if not shipment:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)

    if ctx.is_driver and shipment["driver_id"] != ctx.driver_id:
        raise AppError("Access denied to shipment.", code="FORBIDDEN", status_code=403)

    now = _now_iso()
    exc_id = new_id("EXC")

    # 2. Find or create chat_thread for foreign key compliance
    thread_row = (
        await session.execute(
            text("SELECT thread_id FROM public.chat_threads WHERE shipment_id = :shipment_id LIMIT 1"),
            {"shipment_id": command.shipment_id},
        )
    ).mappings().first()

    if thread_row:
        thread_id = thread_row["thread_id"]
    else:
        thread_id = new_id("TRD")
        await session.execute(
            text(
                """
                INSERT INTO public.chat_threads (
                    thread_id, driver_id, shipment_id, thread_status, created_at, updated_at
                ) VALUES (
                    :thread_id, :driver_id, :shipment_id, 'ESCALATED', :now, :now
                )
                """
            ),
            {
                "thread_id": thread_id,
                "driver_id": shipment["driver_id"],
                "shipment_id": command.shipment_id,
                "now": now,
            },
        )

    # 3. Insert driver exception
    await session.execute(
        text(
            """
            INSERT INTO public.driver_exceptions (
                exception_id, driver_id, shipment_id, thread_id, exception_type,
                severity_code, description, exception_status, reported_at
            ) VALUES (
                :exc_id, :driver_id, :shipment_id, :thread_id, 'DOCK_UNAVAILABLE',
                :severity, :description, 'ESCALATED', :now
            )
            """
        ),
        {
            "exc_id": exc_id,
            "driver_id": shipment["driver_id"],
            "shipment_id": command.shipment_id,
            "thread_id": thread_id,
            "severity": command.urgency,
            "description": command.reason,
            "now": now,
        },
    )

    # 4. Insert operational message for warehouse / ops review
    msg_id = new_id("OPM")
    await session.execute(
        text(
            """
            INSERT INTO public.operational_messages (
                operational_message_id, shipment_id, channel, sender_address,
                recipient_address, subject, message_body, sent_at, delivery_status
            ) VALUES (
                :msg_id, :shipment_id, 'INTERNAL', :sender,
                'operations@setuhaul.com', 'EXCEPTION_ESCALATION', :content, :now, 'SENT'
            )
            """
        ),
        {
            "msg_id": msg_id,
            "shipment_id": command.shipment_id,
            "sender": ctx.email or ctx.user_id,
            "content": f"Escalation raised: {command.reason}",
            "now": now,
        },
    )

    # 4. Audit Log
    audit_id = new_id("AUD")
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
                audit_id, user_id, action_type, entity_name, entity_id, new_value_json, created_at
            ) VALUES (
                :audit_id, :user_id, 'UPDATE', 'driver_exception', :exc_id, :payload, :now
            )
            """
        ),
        {
            "audit_id": audit_id,
            "user_id": ctx.user_id,
            "exc_id": exc_id,
            "payload": f"Escalated exception for shipment {command.shipment_id}: {command.reason}",
            "now": now,
        },
    )

    await session.commit()
    return {
        "escalation_id": exc_id,
        "shipment_id": command.shipment_id,
        "status": "ESCALATED",
        "urgency": command.urgency,
        "facility_id": shipment["destination_facility_id"],
        "reported_at": now,
        "message": "Exception successfully escalated to operations team for human takeover.",
    }
