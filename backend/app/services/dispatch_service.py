from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.scheduling.allocation import RequestSlotCommand, request_slot
from app.scheduling.feasibility import find_feasible_slots
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

DISPATCH_CREATE_ROUTE = "POST /api/v1/dispatch/shipments"


class CreateDispatchShipmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str | None = Field(default=None, max_length=60)
    order_reference: str | None = Field(default=None, max_length=100)
    driver_id: str = Field(..., max_length=60)
    destination_facility_id: str = Field(..., max_length=60)
    customer_name: str = Field(default="Retail Hub Customer", max_length=120)
    product_category: str = Field(default="GENERAL_LOAD", max_length=60)
    load_weight_kg: int = Field(default=12000, ge=100, le=50000)
    pallet_count: int = Field(default=18, ge=1, le=100)
    required_dock_type: str = Field(default="ANY", max_length=60)
    priority_code: str = Field(default="NORMAL", max_length=20)
    original_eta_ts: str = Field(..., description="ISO timestamp for planned ETA")
    expected_unload_min: int = Field(default=30, ge=10, le=360)


async def list_dispatch_drivers(session: AsyncSession, available_only: bool = True) -> list[dict[str, Any]]:
    query = """
        SELECT d.driver_id, d.driver_name, d.phone, d.home_base_city, d.driver_status,
               COUNT(s.shipment_id)::int AS active_shipments
        FROM public.drivers d
        LEFT JOIN public.shipments s
          ON s.driver_id = d.driver_id
         AND s.current_status NOT IN ('COMPLETED', 'CANCELLED')
        GROUP BY d.driver_id, d.driver_name, d.phone, d.home_base_city, d.driver_status
    """
    if available_only:
        query += " HAVING COUNT(s.shipment_id) = 0"
    query += " ORDER BY d.driver_name ASC"

    rows = (await session.execute(text(query))).mappings().all()
    return [dict(r) for r in rows]


async def list_dispatch_facilities(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT facility_id, facility_name, city, state, timezone
                FROM public.facilities
                ORDER BY facility_name ASC
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def create_dispatch_shipment(
    session: AsyncSession,
    ctx: ExecutionContext,
    cmd: CreateDispatchShipmentCommand,
    *,
    idempotency_key: str,
) -> dict[str, Any]:
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions for dispatch operations.", code="FORBIDDEN", status_code=403)

    # This route creates a shipment AND consumes dock capacity via request_slot, so a bare retry
    # (double-click, network timeout-and-resend) previously produced a second shipment and a second
    # booking. Same lookup/store ledger every other mutating route uses (M9 / services/idempotency.py).
    req_hash = payload_hash(cmd.model_dump())
    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=DISPATCH_CREATE_ROUTE,
        request_hash=req_hash,
    )
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    # 1. Verify driver exists and fetch carrier_id & home city
    driver_row = (
        await session.execute(
            text("SELECT driver_id, carrier_id, driver_name, home_base_city FROM public.drivers WHERE driver_id = :did"),
            {"did": cmd.driver_id},
        )
    ).mappings().first()
    if driver_row is None:
        raise AppError(f"Driver '{cmd.driver_id}' not found.", code="NOT_FOUND", status_code=404)

    carrier_id = driver_row["carrier_id"] if driver_row and driver_row["carrier_id"] else "CAR001"
    origin_city = driver_row["home_base_city"] if driver_row and driver_row["home_base_city"] else "Gurugram"
    origin_name = f"{origin_city} Logistics Hub"

    # Find active vehicle for carrier
    veh_row = (
        await session.execute(
            text("SELECT vehicle_id FROM public.vehicles WHERE carrier_id = :cid AND active_flag = 1 LIMIT 1"),
            {"cid": carrier_id},
        )
    ).mappings().first()
    if veh_row and veh_row["vehicle_id"]:
        vehicle_id = veh_row["vehicle_id"]
    else:
        any_veh = (
            await session.execute(text("SELECT vehicle_id FROM public.vehicles WHERE active_flag = 1 LIMIT 1"))
        ).mappings().first()
        vehicle_id = any_veh["vehicle_id"] if any_veh else "D16-VEH-001"

    # 2. Verify facility exists
    facility_row = (
        await session.execute(
            text("SELECT facility_id, facility_name FROM public.facilities WHERE facility_id = :fid"),
            {"fid": cmd.destination_facility_id},
        )
    ).mappings().first()
    if facility_row is None:
        raise AppError(f"Facility '{cmd.destination_facility_id}' not found.", code="NOT_FOUND", status_code=404)

    shipment_id = cmd.shipment_id or f"SHP-DISP-{uuid.uuid4().hex[:8].upper()}"
    order_ref = cmd.order_reference or f"ORD-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    temp_control = 1 if cmd.product_category == "PERISHABLE_FOOD" else 0

    # 3. Create shipment in public.shipments.
    # The INSERT is inside the try, not just the commit: asyncpg reports a unique violation when
    # the statement executes, so catching only around commit() would let the 500 through. Mirrors
    # allocation.py's IntegrityError handling, which wraps execute()+flush() for the same reason.
    try:
        await session.execute(
            text(
                """
            INSERT INTO public.shipments (
                shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                origin_name, origin_city, destination_facility_id,
                customer_name, product_category, load_weight_kg, pallet_count,
                required_dock_type, temperature_control_required, priority_code,
                planned_departure_ts, original_eta_ts, latest_eta_ts,
                expected_unload_min, current_status, created_at, updated_at
            ) VALUES (
                :shipment_id, :order_reference, :carrier_id, :driver_id, :vehicle_id,
                :origin_name, :origin_city, :destination_facility_id,
                :customer_name, :product_category, :load_weight_kg, :pallet_count,
                :required_dock_type, :temp_control, :priority_code,
                :now_iso, :original_eta_ts, :original_eta_ts,
                :expected_unload_min, 'IN_TRANSIT', :now_iso, :now_iso
            )
            """
            ),
            {
                "shipment_id": shipment_id,
                "order_reference": order_ref,
                "carrier_id": carrier_id,
                "driver_id": cmd.driver_id,
                "vehicle_id": vehicle_id,
                "origin_name": origin_name,
                "origin_city": origin_city,
                "destination_facility_id": cmd.destination_facility_id,
                "customer_name": cmd.customer_name,
                "product_category": cmd.product_category,
                "load_weight_kg": cmd.load_weight_kg,
                "pallet_count": cmd.pallet_count,
                "required_dock_type": cmd.required_dock_type,
                "temp_control": temp_control,
                "priority_code": cmd.priority_code,
                "original_eta_ts": cmd.original_eta_ts,
                "expected_unload_min": cmd.expected_unload_min,
                "now_iso": now_iso,
            },
        )
        await session.commit()
    except IntegrityError as exc:
        # A caller-supplied shipment_id that already exists used to surface as an unhandled 500.
        # Retries with the same Idempotency-Key never reach here (the replay guard above returns
        # first); this is the genuine "different key, same shipment_id" collision.
        await session.rollback()
        raise AppError(
            f"Shipment '{shipment_id}' already exists.",
            code="SHIPMENT_ALREADY_EXISTS",
            status_code=409,
        ) from exc

    # 4. Search feasible slots for this new shipment at planned ETA
    initial_appointment = None
    booking_result = None
    try:
        options_result = await find_feasible_slots(session, ctx, shipment_id, limit=3)
        if options_result.options:
            best_slot = options_result.options[0]
            req_cmd = RequestSlotCommand(
                note=f"Initial pre-booking by dispatch {ctx.full_name}",
                displayed_policy_version=options_result.policy_version,
                displayed_recommendation_id=options_result.recommendation_id,
            )
            # Derived from the caller's key, not uuid4(): a random key can never match a prior
            # attempt, so request_slot's own idempotency guard could never see the duplicate.
            # The suffix keeps it distinct from the outer key, whose ledger row has a different
            # route (lookup_idempotency raises IDEMPOTENCY_SCOPE_MISMATCH on a route mismatch).
            idem_key = f"{idempotency_key}:dispatch-initial-slot"
            booking_res = await request_slot(
                session,
                ctx,
                shipment_id=shipment_id,
                slot_id=best_slot.slot_id,
                command=req_cmd,
                idempotency_key=idem_key,
            )
            booking_result = booking_res.model_dump()
            initial_appointment = booking_result.get("appointment")
    except Exception as e:
        # Initial appointment booking failed gracefully; shipment remains created
        booking_result = {"status": "NO_INITIAL_SLOT", "note": str(e)}

    result = {
        "as_of": now_iso,
        "shipment_id": shipment_id,
        "order_reference": order_ref,
        "driver_id": cmd.driver_id,
        "driver_name": driver_row["driver_name"],
        "facility_id": cmd.destination_facility_id,
        "facility_name": facility_row["facility_name"],
        "planned_eta": cmd.original_eta_ts,
        "priority_code": cmd.priority_code,
        "appointment": initial_appointment,
        "booking_result": booking_result,
        "idempotency_key": idempotency_key,
    }
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=DISPATCH_CREATE_ROUTE,
        request_hash=req_hash,
        response=result,
        status_code=200,
    )
    await session.commit()
    return {**result, "idempotent_replay": False}
