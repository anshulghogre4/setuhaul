from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


async def get_driver_operational_context(
    session: AsyncSession, ctx: ExecutionContext
) -> dict[str, Any]:
    if not ctx.is_driver or not ctx.driver_id:
        raise AppError("Driver mapping missing.", code="DRIVER_UNMAPPED", status_code=403)

    driver = (
        await session.execute(
            text(
                """
                SELECT driver_id, driver_name, phone, licence_number, home_base_city, driver_status
                FROM public.drivers WHERE driver_id = :driver_id
                """
            ),
            {"driver_id": ctx.driver_id},
        )
    ).mappings().first()
    if driver is None:
        raise AppError("Driver not found.", code="NOT_FOUND", status_code=404)

    shipments = (
        await session.execute(
            text(
                """
                SELECT shipment_id, order_reference, destination_facility_id, current_status,
                       latest_eta_ts, original_eta_ts, priority_code, updated_at
                FROM public.shipments
                WHERE driver_id = :driver_id
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 20
                """
            ),
            {"driver_id": ctx.driver_id},
        )
    ).mappings().all()

    active = [s for s in shipments if s["current_status"] not in ("COMPLETED", "CANCELLED")]
    primary = active[0] if active else (shipments[0] if shipments else None)

    appointment = None
    facility = None
    latest_eta = None
    if primary is not None:
        appointment = (
            await session.execute(
                text(
                    """
                    SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                           a.is_current, a.booked_at, a.confirmed_at, a.updated_at,
                           s.dock_id, s.facility_id, s.slot_start_ts, s.slot_end_ts, s.slot_status
                    FROM public.appointments a
                    LEFT JOIN public.appointment_slots s ON s.slot_id = a.slot_id
                    WHERE a.shipment_id = :shipment_id
                    ORDER BY a.is_current DESC, a.updated_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"shipment_id": primary["shipment_id"]},
            )
        ).mappings().first()
        facility = (
            await session.execute(
                text(
                    """
                    SELECT facility_id, facility_name, city, state, timezone, open_time, close_time
                    FROM public.facilities WHERE facility_id = :facility_id
                    """
                ),
                {"facility_id": primary["destination_facility_id"]},
            )
        ).mappings().first()
        latest_eta = (
            await session.execute(
                text(
                    """
                    SELECT eta_update_id, shipment_id, source_type, declared_eta_ts,
                           delay_reason_code, confidence_code, created_at
                    FROM public.eta_updates
                    WHERE shipment_id = :shipment_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"shipment_id": primary["shipment_id"]},
            )
        ).mappings().first()

    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "driver": dict(driver),
        "profile": {
            "user_id": ctx.user_id,
            "full_name": ctx.full_name,
            "email": ctx.email,
            "facility_id": ctx.facility_id,
        },
        "shipments": [dict(s) for s in shipments],
        "active_shipments": [dict(s) for s in active],
        "primary_shipment": dict(primary) if primary else None,
        "current_appointment": _serialize_row(appointment),
        "latest_eta": _serialize_row(latest_eta),
        "facility": _serialize_row(facility),
        "freshness": "live",
    }


async def get_shipment_details(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                       origin_name, origin_city, destination_facility_id, customer_name,
                       product_category, load_weight_kg, pallet_count, required_dock_type,
                       temperature_control_required, priority_code, planned_departure_ts,
                       actual_departure_ts, original_eta_ts, latest_eta_ts, expected_unload_min,
                       current_status, created_at, updated_at
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    if ctx.is_driver and row["driver_id"] != ctx.driver_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    if ctx.is_operator and row["destination_facility_id"] != ctx.facility_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    if not (ctx.is_driver or ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)
    return {"as_of": _as_of(), "source": "postgresql", "shipment": dict(row), "freshness": "live"}


async def get_latest_eta(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    await get_shipment_details(session, ctx, shipment_id)
    row = (
        await session.execute(
            text(
                """
                SELECT eta_update_id, shipment_id, source_type, reported_by_driver_id,
                       declared_eta_ts, confidence_code, delay_reason_code, note, created_at
                FROM public.eta_updates
                WHERE shipment_id = :shipment_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "latest_eta": _serialize_row(row),
        "freshness": "live",
    }


async def get_eta_history(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    await get_shipment_details(session, ctx, shipment_id)
    rows = (
        await session.execute(
            text(
                """
                SELECT eta_update_id, shipment_id, source_type, reported_by_driver_id,
                       declared_eta_ts, confidence_code, delay_reason_code, note, created_at
                FROM public.eta_updates
                WHERE shipment_id = :shipment_id
                ORDER BY created_at DESC
                LIMIT 50
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().all()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "items": [dict(r) for r in rows],
        "freshness": "live",
    }


async def get_current_appointment(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    await get_shipment_details(session, ctx, shipment_id)
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.is_current, a.booked_at, a.confirmed_at, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts, sl.slot_status
                FROM public.appointments a
                LEFT JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.shipment_id = :shipment_id AND a.is_current = 1
                ORDER BY a.updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "appointment": _serialize_row(row),
        "freshness": "live",
        "label": "current_appointment_observation",
    }


async def get_facility_details(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str
) -> dict[str, Any]:
    if ctx.is_driver:
        owned = (
            await session.execute(
                text(
                    """
                    SELECT 1 FROM public.shipments
                    WHERE driver_id = :driver_id AND destination_facility_id = :facility_id
                    LIMIT 1
                    """
                ),
                {"driver_id": ctx.driver_id, "facility_id": facility_id},
            )
        ).first()
        if owned is None:
            raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    elif ctx.is_operator and ctx.facility_id != facility_id:
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    elif not (ctx.is_driver or ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)

    facility = (
        await session.execute(
            text(
                """
                SELECT facility_id, facility_name, city, state, timezone, open_time, close_time,
                       checkin_grace_min, default_unload_min, active_flag
                FROM public.facilities WHERE facility_id = :facility_id
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().first()
    if facility is None:
        raise AppError("Facility not found.", code="NOT_FOUND", status_code=404)
    contacts = (
        await session.execute(
            text(
                """
                SELECT contact_id, facility_id, contact_name, contact_role, phone, email
                FROM public.facility_contacts WHERE facility_id = :facility_id
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().all()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "facility": dict(facility),
        "contacts": [dict(c) for c in contacts],
        "freshness": "live",
    }


async def get_exception_status(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str | None = None
) -> dict[str, Any]:
    if not ctx.is_driver or not ctx.driver_id:
        raise AppError("Driver mapping missing.", code="DRIVER_UNMAPPED", status_code=403)
    params: dict[str, Any] = {"driver_id": ctx.driver_id}
    where = "WHERE e.driver_id = :driver_id"
    if shipment_id:
        where += " AND e.shipment_id = :shipment_id"
        params["shipment_id"] = shipment_id
    rows = (
        await session.execute(
            text(
                f"""
                SELECT e.exception_id, e.shipment_id, e.driver_id, e.thread_id, e.exception_type,
                       e.reported_at, e.reported_delay_min, e.declared_eta_ts, e.severity_code,
                       e.exception_status, e.description, e.dedupe_key
                FROM public.driver_exceptions e
                {where}
                ORDER BY e.reported_at DESC
                LIMIT 20
                """
            ),
            params,
        )
    ).mappings().all()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "items": [dict(r) for r in rows],
        "freshness": "live",
    }


async def get_vehicle_and_carrier_details(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str | None = None
) -> dict[str, Any]:
    context = await get_driver_operational_context(session, ctx)
    active = context.get("active_shipments") or []
    target_id = shipment_id
    if not target_id:
        if len(active) == 0:
            raise AppError("No active shipment found.", code="NO_ACTIVE_SHIPMENT", status_code=404)
        target_id = active[0]["shipment_id"]

    row = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.carrier_id, s.driver_id, s.vehicle_id, s.load_weight_kg,
                       v.registration_number, v.capacity_kg, v.refrigeration_capable, v.vehicle_type_code,
                       vt.description AS vehicle_type_description, vt.typical_dock_type,
                       c.carrier_name, c.contact_email, c.contact_phone
                FROM public.shipments s
                JOIN public.vehicles v ON s.vehicle_id = v.vehicle_id
                JOIN public.vehicle_types vt ON v.vehicle_type_code = vt.vehicle_type_code
                JOIN public.carriers c ON s.carrier_id = c.carrier_id
                WHERE s.shipment_id = :shipment_id
                """
            ),
            {"shipment_id": target_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Shipment vehicle details not found.", code="NOT_FOUND", status_code=404)
    if ctx.is_driver and row["driver_id"] != ctx.driver_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "vehicle_and_carrier": dict(row),
        "freshness": "live",
    }


async def get_gate_and_queue_status(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str | None = None
) -> dict[str, Any]:
    context = await get_driver_operational_context(session, ctx)
    active = context.get("active_shipments") or []
    target_id = shipment_id
    if not target_id:
        if len(active) == 0:
            raise AppError("No active shipment found.", code="NO_ACTIVE_SHIPMENT", status_code=404)
        target_id = active[0]["shipment_id"]

    await get_shipment_details(session, ctx, target_id)

    row = (
        await session.execute(
            text(
                """
                SELECT fc.checkin_id, fc.shipment_id, fc.facility_id, fc.gate_in_ts,
                       fc.yard_queue_enter_ts, fc.dock_in_ts, fc.unload_start_ts, fc.unload_end_ts,
                       fc.gate_out_ts, fc.arrival_state, fc.queue_state, fc.queue_position,
                       fc.actual_dock_id, fc.notes, f.facility_name, f.city
                FROM public.facility_checkins fc
                JOIN public.facilities f ON fc.facility_id = f.facility_id
                WHERE fc.shipment_id = :shipment_id
                """
            ),
            {"shipment_id": target_id},
        )
    ).mappings().first()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "shipment_id": target_id,
        "checkin_status": dict(row) if row else None,
        "freshness": "live",
    }


async def get_facility_rules_and_restrictions(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None = None, shipment_id: str | None = None
) -> dict[str, Any]:
    target_facility_id = facility_id
    if not target_facility_id and shipment_id:
        details = await get_shipment_details(session, ctx, shipment_id)
        target_facility_id = details.get("shipment", {}).get("destination_facility_id")
    if not target_facility_id:
        context = await get_driver_operational_context(session, ctx)
        active = context.get("active_shipments") or []
        if active:
            target_facility_id = active[0].get("destination_facility_id")
    if not target_facility_id:
        target_facility_id = ctx.facility_id

    if not target_facility_id:
        raise AppError("Facility ID required.", code="FACILITY_REQUIRED", status_code=400)

    rules = (
        await session.execute(
            text(
                """
                SELECT rule_id, facility_id, rule_type, rule_value, description, effective_from, effective_to
                FROM public.facility_rules
                WHERE facility_id = :facility_id AND active_flag = 1
                ORDER BY rule_type ASC
                """
            ),
            {"facility_id": target_facility_id},
        )
    ).mappings().all()

    facility = (
        await session.execute(
            text(
                """
                SELECT facility_id, facility_name, city, state, open_time, close_time, checkin_grace_min, default_unload_min
                FROM public.facilities WHERE facility_id = :facility_id
                """
            ),
            {"facility_id": target_facility_id},
        )
    ).mappings().first()

    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "facility": dict(facility) if facility else None,
        "rules": [dict(r) for r in rules],
        "freshness": "live",
    }


async def report_vehicle_breakdown_or_incident(
    session: AsyncSession,
    ctx: ExecutionContext,
    shipment_id: str | None = None,
    incident_type: str = "BREAKDOWN",
    description: str = "",
    reported_delay_min: int | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    if not ctx.is_driver or not ctx.driver_id:
        raise AppError("Driver mapping missing.", code="DRIVER_UNMAPPED", status_code=403)

    context = await get_driver_operational_context(session, ctx)
    active = context.get("active_shipments") or []
    target_id = shipment_id
    if not target_id and len(active) > 0:
        target_id = active[0]["shipment_id"]

    if target_id:
        await get_shipment_details(session, ctx, target_id)

    exception_id = f"EXP-{uuid4().hex[:12].upper()}"
    now_ts = datetime.now(timezone.utc).isoformat()
    target_thread_id = thread_id or f"THR-{ctx.driver_id}-{uuid4().hex[:6]}"
    dedupe = f"breakdown-{ctx.driver_id}-{target_id or 'none'}-{now_ts[:13]}"

    valid_types = ("DELAY", "BREAKDOWN", "TRAFFIC", "WEATHER", "EARLY_ARRIVAL", "DOCK_UNAVAILABLE", "UNKNOWN")
    exc_type = incident_type.upper() if incident_type.upper() in valid_types else "BREAKDOWN"
    severity = "CRITICAL" if exc_type == "BREAKDOWN" else "HIGH"

    # Ensure parent chat_threads row exists for foreign key constraint
    await session.execute(
        text(
            """
            INSERT INTO public.chat_threads (thread_id, driver_id, shipment_id, opened_at, thread_status, thread_intent)
            VALUES (:thread_id, :driver_id, :shipment_id, :opened_at, 'OPEN', 'REPORT_DELAY')
            ON CONFLICT (thread_id) DO NOTHING
            """
        ),
        {
            "thread_id": target_thread_id,
            "driver_id": ctx.driver_id,
            "shipment_id": target_id,
            "opened_at": now_ts,
        },
    )

    await session.execute(
        text(
            """
            INSERT INTO public.driver_exceptions (
                exception_id, shipment_id, driver_id, thread_id, exception_type,
                reported_at, reported_delay_min, severity_code, exception_status,
                description, dedupe_key
            ) VALUES (
                :exception_id, :shipment_id, :driver_id, :thread_id, :exception_type,
                :reported_at, :reported_delay_min, :severity_code, 'OPEN',
                :description, :dedupe_key
            )
            """
        ),
        {
            "exception_id": exception_id,
            "shipment_id": target_id,
            "driver_id": ctx.driver_id,
            "thread_id": target_thread_id,
            "exception_type": exc_type,
            "reported_at": now_ts,
            "reported_delay_min": reported_delay_min,
            "severity_code": severity,
            "description": description or f"Driver reported {exc_type.lower()} incident.",
            "dedupe_key": dedupe,
        },
    )

    return {
        "status": "PERSISTED",
        "code": "INCIDENT_REPORTED",
        "exception_id": exception_id,
        "shipment_id": target_id,
        "driver_id": ctx.driver_id,
        "incident_type": exc_type,
        "severity_code": severity,
        "description": description,
        "reported_at": now_ts,
        "message": f"Incident {exc_type} for shipment {target_id or 'general'} has been logged and dispatched to Ops.",
    }


async def get_dock_maintenance_alerts(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None = None, dock_id: str | None = None
) -> dict[str, Any]:
    target_facility_id = facility_id
    if not target_facility_id:
        context = await get_driver_operational_context(session, ctx)
        active = context.get("active_shipments") or []
        if active:
            target_facility_id = active[0].get("destination_facility_id")
    if not target_facility_id:
        target_facility_id = ctx.facility_id

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}
    if target_facility_id:
        where_clauses.append("d.facility_id = :facility_id")
        params["facility_id"] = target_facility_id
    if dock_id:
        where_clauses.append("e.dock_id = :dock_id")
        params["dock_id"] = dock_id

    where_sql = " AND ".join(where_clauses)
    rows = (
        await session.execute(
            text(
                f"""
                SELECT e.dock_event_id, e.dock_id, d.dock_code, d.facility_id, e.event_type,
                       e.event_start_ts, e.event_end_ts, e.reason, e.created_at
                FROM public.dock_status_events e
                JOIN public.docks d ON e.dock_id = d.dock_id
                WHERE {where_sql}
                ORDER BY e.created_at DESC
                LIMIT 20
                """
            ),
            params,
        )
    ).mappings().all()

    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "facility_id": target_facility_id,
        "dock_id": dock_id,
        "alerts": [dict(r) for r in rows],
        "freshness": "live",
    }

