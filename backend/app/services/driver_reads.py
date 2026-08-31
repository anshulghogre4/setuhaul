from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories.drivers import load_driver_operational_snapshot
from app.repositories.facilities import driver_serves_facility, get_facility, list_facility_contacts
from app.repositories.scope import assert_facility_visible, assert_shipment_visible
from app.scheduling import holds


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


async def _snapshot_with_promise(session: AsyncSession, driver_id: str) -> dict[str, Any]:
    """The driver snapshot plus the promise its `current_appointment` alone cannot express (#86).

    `repositories.drivers.load_driver_operational_snapshot` reads `appointments`, and §4 is
    explicit that a hold has no appointment row at all -- so the snapshot's `current_appointment`
    is structurally blind to one. #83 fixed the two *tool-facing* driver reads
    (`get_current_appointment`, `allocation.get_appointment_request_status`) and left this, the
    third: the payload behind `GET /api/v1/driver/context` **and** the prefetch
    `run_assistant.py` hands the model at the top of every turn. Left alone, the chat's opening
    context would say "no appointment" about a shipment the very next tool call reports as HELD --
    same driver, same shipment, two different answers inside one turn.

    Composed here in the service rather than inside the repository on purpose. The repository is
    persistence; "which of two tables holds the stronger promise" is the business rule §4 defines,
    and it already lives in this layer as `resolve_promise_state`. Pushing it down would also mean
    `repositories/` importing `scheduling/`, inverting the layering `AGENTS.md` states. Both
    callers of the snapshot go through this helper, so there is no third shape to drift.

    Cost with the flag **off** is exactly zero: `live_hold_for_shipment` returns `None` without
    touching the session, so no statement changes and none is added. With the flag on it is one
    additional indexed single-row lookup, and only when the driver actually has a primary shipment
    -- the same guard the snapshot's own three per-shipment reads already sit behind.
    """
    snapshot = await load_driver_operational_snapshot(session, driver_id)
    primary = snapshot["primary_shipment"]
    hold = (
        await holds.live_hold_for_shipment(
            session, shipment_id=primary["shipment_id"], now=datetime.now(timezone.utc)
        )
        if primary
        else None
    )
    promise_state, promise_state_source = resolve_promise_state(
        snapshot["current_appointment"], hold
    )
    return {
        **snapshot,
        "current_hold": hold,
        "promise_state": promise_state,
        "promise_state_source": promise_state_source,
    }


async def get_driver_operational_context(
    session: AsyncSession, ctx: ExecutionContext
) -> dict[str, Any]:
    if not ctx.is_driver or not ctx.driver_id:
        raise AppError("Driver mapping missing.", code="DRIVER_UNMAPPED", status_code=403)

    snapshot = await _snapshot_with_promise(session, ctx.driver_id)
    # Key order is load-bearing *for this payload only*, and it is not a style preference.
    # `run_assistant.py` embeds `json.dumps(this)[:4000]` in the turn's system prompt, so whatever
    # sits past 4000 characters is silently cut. Measured against the live database 2026-08-31
    # for the busiest real driver (13 shipments): the payload serialises to 7468 characters and
    # the old ordering put `current_appointment` at offset 6616 -- already truncated away today,
    # before #86 added anything. Putting the single-value promise fields ahead of the two
    # shipment *lists* moves them to roughly offset 400 and lets the cut land on the long,
    # repetitive tail instead of the one fact the model most needs. No consumer depends on key
    # order (JSON objects are unordered; FastAPI re-serialises the REST payload anyway), so this
    # costs nothing and is not a substitute for fixing the 4000 cap itself, which lives in
    # `run_assistant.py` and is filed separately.
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "driver": snapshot["driver"],
        "profile": _driver_profile(ctx),
        "primary_shipment": snapshot["primary_shipment"],
        "current_appointment": snapshot["current_appointment"],
        # The three #86 fields. `current_hold` is its own key rather than being flattened into
        # `current_appointment` for the reason `get_current_appointment` states below: a hold has
        # no `appointment_id`, no `booked_at` and no D9 clock, and faking an appointment shape for
        # it would push §4's "held is not booked" distinction onto every consumer.
        "current_hold": snapshot["current_hold"],
        "promise_state": snapshot["promise_state"],
        "promise_state_source": snapshot["promise_state_source"],
        "latest_eta": snapshot["latest_eta"],
        "facility": snapshot["facility"],
        "active_shipments": snapshot["active_shipments"],
        "shipments": snapshot["shipments"],
        "freshness": "live",
    }


def _driver_profile(ctx: ExecutionContext) -> dict[str, Any]:
    """Identity fields echoed back to the driver surface, all from the trusted context."""
    return {
        "user_id": ctx.user_id,
        "full_name": ctx.full_name,
        "email": ctx.email,
        "facility_id": ctx.facility_id,
    }


async def get_driver_context_payload(session: AsyncSession, ctx: ExecutionContext) -> dict[str, Any]:
    """The `/api/v1/driver/context` REST payload.

    Deliberately *not* `get_driver_operational_context`: that one additionally exposes
    `active_shipments`, which the assistant tools consume but the REST response has never
    returned. Keeping them as two compositions over one shared query set (E2.2) removes the
    duplicated SQL without changing either caller's response shape.

    Issue #86 added `current_hold`/`promise_state`/`promise_state_source` to *both* compositions
    rather than only this one. The asymmetry was the defect: the REST payload and the assistant's
    prefetch describe the same driver's same shipment, and only one of them being able to see a
    hold is precisely how the surface and the model end up disagreeing.
    """
    if not ctx.driver_id:
        raise AppError("Driver mapping missing.", code="DRIVER_UNMAPPED", status_code=403)

    snapshot = await _snapshot_with_promise(session, ctx.driver_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "driver": snapshot["driver"],
        "profile": _driver_profile(ctx),
        "shipments": snapshot["shipments"],
        "primary_shipment": snapshot["primary_shipment"],
        "current_appointment": snapshot["current_appointment"],
        "current_hold": snapshot["current_hold"],
        "promise_state": snapshot["promise_state"],
        "promise_state_source": snapshot["promise_state_source"],
        "latest_eta": snapshot["latest_eta"],
        "facility": snapshot["facility"],
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
    assert_shipment_visible(
        ctx,
        shipment_driver_id=row["driver_id"],
        shipment_facility_id=row["destination_facility_id"],
    )
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


ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")


def resolve_promise_state(
    appointment: dict[str, Any] | None, hold: dict[str, Any] | None
) -> tuple[str | None, str | None]:
    """Which promise this shipment actually has right now, and which table said so (issue #83).

    D2's lifecycle is `SHOWN -> HELD -> PENDING_CONFIRMATION -> CONFIRMED` (§4), but only the last
    two live in `appointments`; a hold is a `dock_occupancy` row and nothing else. So the answer has
    to be composed from two tables, and the precedence between them is a real decision rather than
    an ordering accident:

    1. **An active appointment wins.** If the shipment already has a PENDING_CONFIRMATION /
       CONFIRMED / IN_PROGRESS appointment, that is the stronger promise and it is what the driver
       must be shown -- even if a hold row also exists. That combination is reachable, not
       hypothetical: `confirm_held_slot` has an `IntegrityError` branch for exactly the case where a
       driver acquired a hold and then got an appointment for the same shipment by another route
       inside the 90-second window.
    2. **Otherwise a live hold wins**, including over a CANCELLED or EXPIRED current appointment.
       A driver who cancelled and then took a fresh hold is HELD, not CANCELLED.
    3. **Otherwise whatever the current appointment says**, unchanged from before this issue.

    Returned as a pair so no caller has to re-derive the source from the value; a UI that renders a
    HELD countdown needs to know it came from `dock_occupancy` and not from a status column that
    cannot express it.
    """
    status = (appointment or {}).get("appointment_status")
    if status is not None and str(status) in ACTIVE_APPOINTMENT_STATUSES:
        return str(status), holds.PROMISE_STATE_SOURCE_APPOINTMENT
    if hold is not None:
        return holds.HOLD_PROMISE_STATE, holds.PROMISE_STATE_SOURCE_HOLD
    if status is not None:
        return str(status), holds.PROMISE_STATE_SOURCE_APPOINTMENT
    return None, None


async def get_current_appointment(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    """The driver's current promise -- appointment *or* D2 hold (issue #83).

    Before this, the payload derived everything from `appointments.appointment_status`, so a driver
    who had just taken a hold saw `appointment: null` -- indistinguishable from having no promise at
    all, moments after the system told them a slot was "reserved for you for 90 seconds" (§0.8).
    E5.1's four flag-gated HELD screens are blocked on precisely this field.

    The hold is returned as its own key rather than being flattened into `appointment`, because it
    genuinely is not one: it has no `appointment_id`, no `booked_at`, and no D9 clock. Faking an
    appointment shape for it would push the "held is not booked" distinction §4 insists on back onto
    every consumer.
    """
    await get_shipment_details(session, ctx, shipment_id)
    now = datetime.now(timezone.utc)
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
    appointment = _serialize_row(row)
    # Costs zero queries with the flag off -- `live_hold_for_shipment` returns None without
    # touching the session, so this path is exactly what it was on an unmigrated database.
    hold = await holds.live_hold_for_shipment(session, shipment_id=shipment_id, now=now)
    promise_state, promise_state_source = resolve_promise_state(appointment, hold)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "appointment": appointment,
        "hold": hold,
        "promise_state": promise_state,
        "promise_state_source": promise_state_source,
        "freshness": "live",
        "label": "current_appointment_observation",
    }


async def get_facility_details(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str
) -> dict[str, Any]:
    # The driver branch is the only one that needs a database answer, so the probe runs first and
    # only for drivers -- keeping the extra round-trip off the operator/global paths, exactly as
    # the previous inline version did.
    serves = await driver_serves_facility(session, ctx.driver_id, facility_id) if ctx.is_driver else False
    assert_facility_visible(ctx, facility_id, driver_serves_facility=serves)

    facility = await get_facility(session, facility_id)
    if facility is None:
        raise AppError("Facility not found.", code="NOT_FOUND", status_code=404)
    contacts = await list_facility_contacts(session, facility_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "facility": facility,
        "contacts": contacts,
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
                       e.exception_status, e.description, e.dedupe_key, e.resolution_note
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

    # get_db_session (core/deps.py) yields a bare session with no auto-commit, and neither the
    # tools.py wrapper nor run_assistant.py commits on this function's behalf. Without this call
    # SQLAlchemy rolls the transaction back when the session closes, so the driver's incident
    # report is silently discarded while the assistant still replies "PERSISTED". Do not remove.
    await session.commit()

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

