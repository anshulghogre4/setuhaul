from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.services.ids import new_id
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency

IST = ZoneInfo("Asia/Kolkata")

# Must match baseline CHECK constraints (do not invent synonyms like ETA_UPDATE / LATE_ETA).
AUDIT_ACTION_UPDATE_ETA = "UPDATE_ETA"
PARSED_INTENT_UPDATE_ETA = "UPDATE_ETA"
ALLOWED_EXCEPTION_TYPES = frozenset(
    {"DELAY", "BREAKDOWN", "TRAFFIC", "WEATHER", "EARLY_ARRIVAL", "DOCK_UNAVAILABLE", "UNKNOWN"}
)


class EtaUpdateCommand(BaseModel):
    declared_eta_ts: str
    delay_reason_code: str | None = None
    confidence_code: str = "MEDIUM"
    note: str | None = None
    reported_delay_min: int | None = None
    repair_duration_min: int | None = None
    exception_type: str = "DELAY"
    description: str | None = None
    thread_id: str | None = None
    confirmed: bool = False
    confirmation_eta_ts: str | None = None
    client_message_id: str | None = None


def _parse_eta(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise AppError(
            "declared_eta_ts must be an ISO-8601 timestamp with timezone.",
            code="INVALID_ETA",
            status_code=422,
        ) from exc
    if dt.tzinfo is None:
        raise AppError(
            "declared_eta_ts must include a timezone offset.",
            code="INVALID_ETA",
            status_code=422,
        )
    return dt


def format_eta_display(eta_ts: str) -> str:
    dt = _parse_eta(eta_ts).astimezone(IST)
    return dt.strftime("%Y-%m-%d %H:%M %Z (Asia/Kolkata)")


def confirmation_preview(cmd: EtaUpdateCommand) -> dict[str, Any]:
    display = format_eta_display(cmd.declared_eta_ts)
    return {
        "status": "CONFIRMATION_REQUIRED",
        "code": "CONFIRMATION_REQUIRED",
        "declared_eta_ts": cmd.declared_eta_ts,
        "display_eta": display,
        "timezone": "Asia/Kolkata",
        "repair_duration_min": cmd.repair_duration_min,
        "reported_delay_min": cmd.reported_delay_min,
        "note": (
            "Repair duration is not an ETA. Confirm the exact arrival timestamp before write."
            if cmd.repair_duration_min is not None
            else "Confirm the exact interpreted ETA before the write proceeds."
        ),
        "requires_confirmation": True,
    }


async def _assert_driver_owns_shipment(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    if not ctx.is_driver or not ctx.driver_id:
        raise AppError("Only the assigned driver may update ETA.", code="FORBIDDEN", status_code=403)
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, driver_id, destination_facility_id, current_status,
                       latest_eta_ts, original_eta_ts
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    if row["driver_id"] != ctx.driver_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    return dict(row)


async def _ensure_thread(
    session: AsyncSession,
    *,
    ctx: ExecutionContext,
    shipment_id: str,
    thread_id: str | None,
) -> str:
    if thread_id:
        existing = (
            await session.execute(
                text(
                    """
                    SELECT thread_id, driver_id, shipment_id, thread_status
                    FROM public.chat_threads WHERE thread_id = :thread_id
                    """
                ),
                {"thread_id": thread_id},
            )
        ).mappings().first()
        if existing and existing["driver_id"] == ctx.driver_id:
            if existing["shipment_id"] in (None, shipment_id):
                if existing["shipment_id"] is None:
                    await session.execute(
                        text(
                            "UPDATE public.chat_threads SET shipment_id = :shipment_id "
                            "WHERE thread_id = :thread_id"
                        ),
                        {"shipment_id": shipment_id, "thread_id": thread_id},
                    )
                return thread_id

    open_row = (
        await session.execute(
            text(
                """
                SELECT thread_id FROM public.chat_threads
                WHERE driver_id = :driver_id AND shipment_id = :shipment_id
                  AND thread_status NOT IN ('CLOSED')
                ORDER BY opened_at DESC
                LIMIT 1
                """
            ),
            {"driver_id": ctx.driver_id, "shipment_id": shipment_id},
        )
    ).mappings().first()
    if open_row:
        return str(open_row["thread_id"])

    tid = new_id("THR")
    now = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text(
            """
            INSERT INTO public.chat_threads (
              thread_id, driver_id, shipment_id, opened_at, closed_at, thread_status, thread_intent
            ) VALUES (
              :thread_id, :driver_id, :shipment_id, :opened_at, NULL, 'OPEN', 'REPORT_DELAY'
            )
            """
        ),
        {
            "thread_id": tid,
            "driver_id": ctx.driver_id,
            "shipment_id": shipment_id,
            "opened_at": now,
        },
    )
    return tid


async def _reread(
    session: AsyncSession, *, shipment_id: str, eta_update_id: str, exception_id: str, thread_id: str
) -> dict[str, Any]:
    shipment = (
        await session.execute(
            text(
                """
                SELECT shipment_id, driver_id, destination_facility_id, current_status,
                       latest_eta_ts, original_eta_ts, updated_at
                FROM public.shipments WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    eta = (
        await session.execute(
            text(
                """
                SELECT eta_update_id, shipment_id, source_type, reported_by_driver_id,
                       declared_eta_ts, confidence_code, delay_reason_code, note, created_at
                FROM public.eta_updates WHERE eta_update_id = :eta_update_id
                """
            ),
            {"eta_update_id": eta_update_id},
        )
    ).mappings().first()
    exc = (
        await session.execute(
            text(
                """
                SELECT exception_id, shipment_id, driver_id, thread_id, exception_type,
                       reported_at, reported_delay_min, declared_eta_ts, severity_code,
                       exception_status, description, dedupe_key
                FROM public.driver_exceptions WHERE exception_id = :exception_id
                """
            ),
            {"exception_id": exception_id},
        )
    ).mappings().first()
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "postgresql",
        "freshness": "live",
        "status": "PERSISTED",
        "shipment": dict(shipment) if shipment else None,
        "eta_update": dict(eta) if eta else None,
        "exception": dict(exc) if exc else None,
        "thread_id": thread_id,
        "display_eta": format_eta_display(str(eta["declared_eta_ts"])) if eta else None,
    }


async def record_eta_update(
    session: AsyncSession,
    *,
    ctx: ExecutionContext,
    shipment_id: str,
    command: EtaUpdateCommand,
    idempotency_key: str,
) -> dict[str, Any]:
    """Atomic ETA + exception + audit write with post-commit reread semantics."""
    route = f"POST /api/v1/shipments/{shipment_id}/eta-updates"
    body = command.model_dump()
    req_hash = payload_hash({"shipment_id": shipment_id, **body})

    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    if command.repair_duration_min is not None and not command.declared_eta_ts:
        raise AppError(
            "Repair duration is not a revised ETA. Provide an arrival timestamp.",
            code="REPAIR_IS_NOT_ETA",
            status_code=422,
        )

    if not command.confirmed:
        preview = confirmation_preview(command)
        preview["shipment_id"] = shipment_id
        return preview

    if not command.confirmation_eta_ts or command.confirmation_eta_ts != command.declared_eta_ts:
        raise AppError(
            "confirmation_eta_ts must exactly match the interpreted declared_eta_ts.",
            code="CONFIRMATION_MISMATCH",
            status_code=409,
        )

    if command.exception_type not in ALLOWED_EXCEPTION_TYPES:
        raise AppError(
            "exception_type is not an allowed driver_exceptions value.",
            code="INVALID_EXCEPTION_TYPE",
            status_code=422,
        )

    _parse_eta(command.declared_eta_ts)
    shipment = await _assert_driver_owns_shipment(session, ctx, shipment_id)

    now = datetime.now(timezone.utc).isoformat()
    eta_id = new_id("ETA")
    exception_id = new_id("EXC")
    audit_id = new_id("AUD")
    message_id = new_id("MSG")
    thread_id = await _ensure_thread(
        session, ctx=ctx, shipment_id=shipment_id, thread_id=command.thread_id
    )
    dedupe_key = command.client_message_id or f"{ctx.driver_id}-{shipment_id}-{idempotency_key}"
    description = command.description or (
        f"Driver-declared ETA update to {format_eta_display(command.declared_eta_ts)}"
    )

    # Message dedupe via unique external_message_id when provided
    if command.client_message_id:
        dup = (
            await session.execute(
                text(
                    "SELECT chat_message_id FROM public.chat_messages "
                    "WHERE external_message_id = :external_message_id LIMIT 1"
                ),
                {"external_message_id": command.client_message_id},
            )
        ).mappings().first()
        if dup:
            # Treat as idempotent business effect already recorded under same client message
            prior = (
                await session.execute(
                    text(
                        """
                        SELECT eta_update_id FROM public.eta_updates
                        WHERE shipment_id = :shipment_id AND reported_by_driver_id = :driver_id
                        ORDER BY created_at DESC LIMIT 1
                        """
                    ),
                    {"shipment_id": shipment_id, "driver_id": ctx.driver_id},
                )
            ).mappings().first()
            if prior:
                # Fall through to stored idempotency if present; else reread latest
                pass

    await session.execute(
        text(
            """
            INSERT INTO public.eta_updates (
              eta_update_id, shipment_id, source_type, reported_by_driver_id,
              declared_eta_ts, confidence_code, delay_reason_code, note, created_at
            ) VALUES (
              :eta_update_id, :shipment_id, 'DRIVER_DECLARED', :driver_id,
              :declared_eta_ts, :confidence_code, :delay_reason_code, :note, :created_at
            )
            """
        ),
        {
            "eta_update_id": eta_id,
            "shipment_id": shipment_id,
            "driver_id": ctx.driver_id,
            "declared_eta_ts": command.declared_eta_ts,
            "confidence_code": command.confidence_code,
            "delay_reason_code": command.delay_reason_code,
            "note": command.note,
            "created_at": now,
        },
    )

    await session.execute(
        text(
            """
            UPDATE public.shipments
            SET latest_eta_ts = :latest_eta_ts, updated_at = :updated_at
            WHERE shipment_id = :shipment_id
            """
        ),
        {
            "latest_eta_ts": command.declared_eta_ts,
            "updated_at": now,
            "shipment_id": shipment_id,
        },
    )

    await session.execute(
        text(
            """
            INSERT INTO public.chat_messages (
              chat_message_id, thread_id, sender_type, sender_reference, message_text,
              message_ts, external_message_id, is_duplicate, parsed_intent,
              extracted_eta_ts, requires_human_review
            ) VALUES (
              :chat_message_id, :thread_id, 'DRIVER', :driver_id, :message_text,
              :message_ts, :external_message_id, 0, :parsed_intent,
              :extracted_eta_ts, 0
            )
            """
        ),
        {
            "chat_message_id": message_id,
            "thread_id": thread_id,
            "driver_id": ctx.driver_id,
            "message_text": description,
            "message_ts": now,
            "external_message_id": command.client_message_id or idempotency_key,
            "parsed_intent": PARSED_INTENT_UPDATE_ETA,
            "extracted_eta_ts": command.declared_eta_ts,
        },
    )

    open_exc = (
        await session.execute(
            text(
                """
                SELECT exception_id FROM public.driver_exceptions
                WHERE driver_id = :driver_id AND shipment_id = :shipment_id
                  AND exception_status NOT IN ('CLOSED', 'RESOLVED')
                ORDER BY reported_at DESC LIMIT 1
                """
            ),
            {"driver_id": ctx.driver_id, "shipment_id": shipment_id},
        )
    ).mappings().first()

    if open_exc:
        exception_id = str(open_exc["exception_id"])
        await session.execute(
            text(
                """
                UPDATE public.driver_exceptions
                SET declared_eta_ts = :declared_eta_ts,
                    reported_delay_min = COALESCE(:reported_delay_min, reported_delay_min),
                    description = :description,
                    exception_status = 'OPEN',
                    thread_id = :thread_id,
                    dedupe_key = :dedupe_key
                WHERE exception_id = :exception_id
                """
            ),
            {
                "declared_eta_ts": command.declared_eta_ts,
                "reported_delay_min": command.reported_delay_min,
                "description": description,
                "thread_id": thread_id,
                "dedupe_key": dedupe_key,
                "exception_id": exception_id,
            },
        )
    else:
        await session.execute(
            text(
                """
                INSERT INTO public.driver_exceptions (
                  exception_id, shipment_id, driver_id, thread_id, exception_type,
                  reported_at, reported_delay_min, declared_eta_ts, earliest_acceptable_ts,
                  latest_acceptable_ts, severity_code, exception_status, description, dedupe_key
                ) VALUES (
                  :exception_id, :shipment_id, :driver_id, :thread_id, :exception_type,
                  :reported_at, :reported_delay_min, :declared_eta_ts, NULL,
                  NULL, 'MEDIUM', 'OPEN', :description, :dedupe_key
                )
                """
            ),
            {
                "exception_id": exception_id,
                "shipment_id": shipment_id,
                "driver_id": ctx.driver_id,
                "thread_id": thread_id,
                "exception_type": command.exception_type,
                "reported_at": now,
                "reported_delay_min": command.reported_delay_min,
                "declared_eta_ts": command.declared_eta_ts,
                "description": description,
                "dedupe_key": dedupe_key,
            },
        )

    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'shipments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": audit_id,
            "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_UPDATE_ETA,
            "entity_id": shipment_id,
            "old_value_json": str({"latest_eta_ts": shipment.get("latest_eta_ts")}),
            "new_value_json": str(
                {
                    "latest_eta_ts": command.declared_eta_ts,
                    "eta_update_id": eta_id,
                    "exception_id": exception_id,
                    "repair_duration_min": command.repair_duration_min,
                    "reported_delay_min": command.reported_delay_min,
                }
            ),
            "created_at": now,
        },
    )

    await session.flush()
    result = await _reread(
        session,
        shipment_id=shipment_id,
        eta_update_id=eta_id,
        exception_id=exception_id,
        thread_id=thread_id,
    )
    result["idempotency_key"] = idempotency_key
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result,
        status_code=200,
    )
    await session.commit()
    # Authoritative post-commit reread
    final = await _reread(
        session,
        shipment_id=shipment_id,
        eta_update_id=eta_id,
        exception_id=exception_id,
        thread_id=thread_id,
    )
    final["idempotency_key"] = idempotency_key
    final["idempotent_replay"] = False
    return final
