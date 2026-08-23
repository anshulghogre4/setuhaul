"""Live Sprint 3 gate proofs: 10x scarce-slot load + demo-day cast smoke.

Requires DATABASE_URL and SETUHAUL_RUN_LIVE_DB_TESTS=1.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.execution_context import ExecutionContext, RoleName
from app.db.session import _normalize_async_url
from app.scheduling.allocation import (
    CancelAppointmentCommand,
    ConfirmAppointmentCommand,
    RejectAppointmentCommand,
    RequestSlotCommand,
    cancel_appointment,
    confirm_appointment,
    get_appointment_request_status,
    reject_appointment,
    request_slot,
)
from app.scheduling.feasibility import find_feasible_slots
from app.services.escalation_service import (
    EscalateExceptionCommand,
    escalate_exception,
    get_exception_queue,
)


pytestmark = pytest.mark.asyncio

IST = timezone(timedelta(hours=5, minutes=30))


def _live_db_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL")) and os.getenv("SETUHAUL_RUN_LIVE_DB_TESTS") == "1"


def _driver_ctx(*, user_id: str, driver_id: str, email: str | None = None) -> ExecutionContext:
    return ExecutionContext(
        request_id="live-d16-load",
        auth_subject=f"live-{driver_id}",
        user_id=user_id,
        email=email or f"{driver_id.lower()}@setuhaul.com",
        full_name=driver_id,
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id=driver_id,
        facility_id="FAC-JAI-01",
    )


def _ops_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="live-d16-ops",
        auth_subject="live-ops",
        user_id="USR101",
        email="priya.mehta@setuhaul.com",
        full_name="Priya Mehta",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-JAI-01",
    )


async def _cleanup_load(session_factory, run_id: str) -> None:
    prefix = f"SHP-LOAD-{run_id}-%"
    slot_prefix = f"SLT-LOAD-{run_id}-%"
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM public.idempotency_requests WHERE idempotency_key LIKE :prefix"),
            {"prefix": f"d16load-{run_id}-%"},
        )
        await session.execute(
            text(
                """
                DELETE FROM public.audit_logs
                WHERE entity_name = 'appointments'
                  AND entity_id IN (
                    SELECT appointment_id FROM public.appointments
                    WHERE shipment_id LIKE :prefix OR slot_id LIKE :slot_prefix
                  )
                """
            ),
            {"prefix": prefix, "slot_prefix": slot_prefix},
        )
        # dock_occupancy.appointment_id has no ON DELETE CASCADE, so the D1 capacity claims
        # written by request_slot must go before the appointments they reference.
        await session.execute(
            text(
                """
                DELETE FROM public.dock_occupancy
                WHERE appointment_id IN (
                    SELECT appointment_id FROM public.appointments
                    WHERE shipment_id LIKE :prefix OR slot_id LIKE :slot_prefix
                )
                """
            ),
            {"prefix": prefix, "slot_prefix": slot_prefix},
        )
        await session.execute(
            text(
                "DELETE FROM public.appointments WHERE shipment_id LIKE :prefix OR slot_id LIKE :slot_prefix"
            ),
            {"prefix": prefix, "slot_prefix": slot_prefix},
        )
        await session.execute(
            text("DELETE FROM public.appointment_slots WHERE slot_id LIKE :slot_prefix"),
            {"slot_prefix": slot_prefix},
        )
        await session.execute(
            text("DELETE FROM public.shipments WHERE shipment_id LIKE :prefix"),
            {"prefix": prefix},
        )
        await session.commit()


async def _seed_scarce_load(
    session_factory, run_id: str
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Seed 10 DRIVER-scoped shipments racing 4 OPEN STANDARD evening slots."""
    now = datetime.now(IST).isoformat()
    base = datetime(2099, 6, 1, 18, 0, tzinfo=IST)
    docks = ["DOCK-JAI-D1", "DOCK-JAI-D2", "DOCK-JAI-D3", "DOCK-JAI-D4"]
    slot_ids = [f"SLT-LOAD-{run_id}-{index:02d}" for index in range(4)]
    # Reuse live Auth-mapped contention drivers DRV004..DRV013 / USR201..USR210.
    drivers = [(f"DRV{index:03d}", f"USR{200 + index - 3:03d}") for index in range(4, 14)]
    shipment_ids = [f"SHP-LOAD-{run_id}-{index:02d}" for index in range(1, 11)]
    async with session_factory() as session:
        for index, slot_id in enumerate(slot_ids):
            start = base + timedelta(minutes=30 * index)
            end = start + timedelta(minutes=30)
            await session.execute(
                text(
                    """
                    INSERT INTO public.appointment_slots (
                      slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts,
                      slot_status, block_reason, created_at
                    ) VALUES (
                      :slot_id, 'FAC-JAI-01', :dock_id, :start_ts, :end_ts, 'OPEN', NULL, :now
                    )
                    """
                ),
                {
                    "slot_id": slot_id,
                    "dock_id": docks[index],
                    "start_ts": start.isoformat(),
                    "end_ts": end.isoformat(),
                    "now": now,
                },
            )
        for index, (shipment_id, (driver_id, _user_id)) in enumerate(zip(shipment_ids, drivers)):
            eta = base - timedelta(minutes=15) + timedelta(minutes=5 * index)
            await session.execute(
                text(
                    """
                    INSERT INTO public.shipments (
                      shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                      origin_name, origin_city, destination_facility_id, customer_name,
                      product_category, load_weight_kg, pallet_count, required_dock_type,
                      temperature_control_required, priority_code, planned_departure_ts,
                      actual_departure_ts, original_eta_ts, latest_eta_ts,
                      expected_unload_min, current_status, created_at, updated_at
                    ) VALUES (
                      :shipment_id, :order_reference, 'CAR001', :driver_id, 'VEH001',
                      'Load Test Origin', 'Jaipur', 'FAC-JAI-01', 'Load Test Customer',
                      'GENERAL', 10000, 10, 'STANDARD',
                      0, 'HIGH', :planned_departure_ts,
                      :actual_departure_ts, :eta_ts, :eta_ts,
                      25, 'IN_TRANSIT', :now, :now
                    )
                    """
                ),
                {
                    "shipment_id": shipment_id,
                    "order_reference": f"ORD-LOAD-{run_id}-{index:02d}",
                    "driver_id": driver_id,
                    "planned_departure_ts": (eta - timedelta(hours=4)).isoformat(),
                    "actual_departure_ts": (eta - timedelta(hours=3)).isoformat(),
                    "eta_ts": eta.isoformat(),
                    "now": now,
                },
            )
        await session.commit()
    shipments = [
        (shipment_id, driver_id, user_id)
        for shipment_id, (driver_id, user_id) in zip(shipment_ids, drivers)
    ]
    return shipments, slot_ids


async def _cleanup_cast_writes(session_factory, run_id: str) -> None:
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM public.idempotency_requests WHERE idempotency_key LIKE :prefix"),
            {"prefix": f"d16cast-{run_id}-%"},
        )
        # Claims first: dock_occupancy.appointment_id has no ON DELETE CASCADE.
        await session.execute(
            text(
                """
                DELETE FROM public.dock_occupancy
                WHERE appointment_id IN (
                    SELECT appointment_id FROM public.appointments
                    WHERE shipment_id IN ('SHP-D16-RAVI', 'SHP-D16-NOSLOT')
                      AND booking_source = 'DRIVER_CHAT'
                      AND appointment_id NOT LIKE 'D16-APT-%'
                )
                """
            )
        )
        await session.execute(
            text(
                """
                DELETE FROM public.appointments
                WHERE shipment_id IN ('SHP-D16-RAVI', 'SHP-D16-NOSLOT')
                  AND booking_source = 'DRIVER_CHAT'
                  AND appointment_id NOT LIKE 'D16-APT-%'
                """
            )
        )
        await session.commit()


@pytest.mark.skipif(not _live_db_enabled(), reason="requires DATABASE_URL and SETUHAUL_RUN_LIVE_DB_TESTS=1")
async def test_live_ten_driver_scarce_evening_load_has_no_double_books():
    engine = create_async_engine(
        _normalize_async_url(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id = uuid4().hex[:10].upper()
    await _cleanup_load(session_factory, run_id)
    try:
        shipments, slot_ids = await _seed_scarce_load(session_factory, run_id)
        assert len(shipments) == 10
        assert len(slot_ids) == 4

        async def _one(shipment_id: str, driver_id: str, user_id: str, slot_id: str, key: str):
            async with session_factory() as session:
                return await request_slot(
                    session,
                    _driver_ctx(user_id=user_id, driver_id=driver_id),
                    shipment_id=shipment_id,
                    slot_id=slot_id,
                    command=RequestSlotCommand(
                        note="D16-style 10x load proof",
                        displayed_policy_version="sprint3_constraints_v1",
                    ),
                    idempotency_key=key,
                )

        results = await asyncio.gather(
            *[
                _one(
                    shipment_id,
                    driver_id,
                    user_id,
                    slot_ids[index % len(slot_ids)],
                    f"d16load-{run_id}-{index:02d}",
                )
                for index, (shipment_id, driver_id, user_id) in enumerate(shipments)
            ]
        )

        winners = [result for result in results if result.code == "SLOT_REQUESTED"]
        conflicts = [
            result
            for result in results
            if result.code in {"SLOT_CONFLICT_REFRESH_REQUIRED", "SLOT_OPTIONS_STALE"}
        ]
        assert len(winners) == 4
        assert len(conflicts) == 6
        assert all(result.appointment_writes == 1 for result in winners)
        assert all(result.appointment_writes == 0 for result in conflicts)
        assert len({result.slot_id for result in winners}) == 4

        async with session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT slot_id, count(*)::int AS n
                        FROM public.appointments
                        WHERE slot_id = ANY(:slot_ids)
                          AND appointment_status IN
                            ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                        GROUP BY slot_id
                        """
                    ),
                    {"slot_ids": slot_ids},
                )
            ).mappings().all()
        counts = {row["slot_id"]: row["n"] for row in rows}
        assert all(count == 1 for count in counts.values())
        assert sum(counts.values()) == 4
    finally:
        await _cleanup_load(session_factory, run_id)
        await engine.dispose()


@pytest.mark.skipif(not _live_db_enabled(), reason="requires DATABASE_URL and SETUHAUL_RUN_LIVE_DB_TESTS=1")
async def test_live_d16_cast_smoke_options_request_cancel_noslot_reject_stale():
    engine = create_async_engine(
        _normalize_async_url(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id = uuid4().hex[:10].upper()
    await _cleanup_cast_writes(session_factory, run_id)
    ravi = _driver_ctx(user_id="USR001", driver_id="DRV001", email="ravi.kumar@setuhaul.com")
    vikas = _driver_ctx(user_id="USR003", driver_id="DRV003", email="vikas.sharma@setuhaul.com")
    ops = _ops_ctx()
    try:
        async with session_factory() as session:
            # Cast reset now leaves D16-APT-RAVI-OLD cancelled/not current. This
            # UPDATE is a no-op after a correct reset and still defends leftover CONFIRMED rows.
            await session.execute(
                text(
                    """
                    UPDATE public.appointments
                    SET appointment_status = 'CANCELLED', is_current = 0,
                        cancelled_at = :now, cancellation_reason = 'Cast smoke precondition',
                        updated_at = :now
                    WHERE appointment_id = 'D16-APT-RAVI-OLD'
                      AND appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                    """
                ),
                {"now": datetime.now(IST).isoformat()},
            )
            # This precondition cancels in raw SQL rather than through cancel_appointment, so
            # it has to release the D1 claim itself -- otherwise the old appointment's dock
            # interval stays claimed and the reschedule under test loses to a ghost.
            await session.execute(
                text(
                    """
                    DELETE FROM public.dock_occupancy
                    WHERE appointment_id = 'D16-APT-RAVI-OLD'
                    """
                )
            )
            await session.commit()

            options = await find_feasible_slots(session, ravi, "SHP-D16-RAVI", limit=5)
            assert options.options, "Ravi cast must have feasible options"
            recommendation_id = options.recommendation_id
            slot_id = options.options[0].slot_id
            # Clear any prior Redis stale marker from ETA demos before proving a fresh request.
            try:
                from app.core.settings import get_settings
                from app.services.redis_memory import ConversationMemory

                memory = ConversationMemory(get_settings())
                memory.store_active_recommendation(
                    user_id=ravi.user_id,
                    shipment_id="SHP-D16-RAVI",
                    recommendation_id=recommendation_id,
                )
            except Exception:  # noqa: BLE001
                pass

            requested = await request_slot(
                session,
                ravi,
                shipment_id="SHP-D16-RAVI",
                slot_id=slot_id,
                command=RequestSlotCommand(
                    note="cast smoke request",
                    displayed_policy_version=options.policy_version,
                    displayed_recommendation_id=recommendation_id,
                ),
                idempotency_key=f"d16cast-{run_id}-ravi-req",
            )
            assert requested.code == "SLOT_REQUESTED"
            appointment_id = requested.appointment_id
            assert appointment_id

            status = await get_appointment_request_status(
                session, ravi, shipment_id="SHP-D16-RAVI", appointment_id=appointment_id
            )
            assert status.code == "APPOINTMENT_PENDING_CONFIRMATION"

            stale = await request_slot(
                session,
                ravi,
                shipment_id="SHP-D16-RAVI",
                slot_id=slot_id,
                command=RequestSlotCommand(
                    note="stale after active exists",
                    displayed_recommendation_id="REC-stale-not-current",
                ),
                idempotency_key=f"d16cast-{run_id}-ravi-stale",
            )
            assert stale.code in {"SLOT_OPTIONS_STALE", "SLOT_CONFLICT_REFRESH_REQUIRED"}

            cancelled = await cancel_appointment(
                session,
                ravi,
                shipment_id="SHP-D16-RAVI",
                command=CancelAppointmentCommand(
                    appointment_id=appointment_id,
                    cancellation_reason="Cast smoke capacity release",
                ),
                idempotency_key=f"d16cast-{run_id}-ravi-cancel",
            )
            assert cancelled.code == "APPOINTMENT_CANCELLED"

            after_cancel = await find_feasible_slots(session, ravi, "SHP-D16-RAVI", limit=5)
            assert any(option.slot_id == slot_id for option in after_cancel.options)

            noslot = await find_feasible_slots(session, vikas, "SHP-D16-NOSLOT", limit=5)
            assert noslot.options == []
            assert noslot.escalation is not None
            persisted = await escalate_exception(
                session,
                vikas,
                EscalateExceptionCommand(
                    shipment_id="SHP-D16-NOSLOT",
                    escalation_type="NO_SLOT",
                    payload=noslot.escalation,
                    policy_version=noslot.policy_version,
                    recommendation_id=noslot.recommendation_id,
                ),
            )
            assert persisted["escalation_status"] == "OPEN"

            queue = await get_exception_queue(session, ops, facility_id="FAC-JAI-01")
            assert any(item["shipment_id"] == "SHP-D16-NOSLOT" for item in queue["items"])

            refreshed = await find_feasible_slots(session, ravi, "SHP-D16-RAVI", limit=5)
            assert refreshed.options, "need free feasible options for reject/confirm smoke"
            free = [option.slot_id for option in refreshed.options[:2]]

            reject_req = await request_slot(
                session,
                ravi,
                shipment_id="SHP-D16-RAVI",
                slot_id=str(free[0]),
                command=RequestSlotCommand(
                    note="cast smoke reject target",
                    displayed_recommendation_id=refreshed.recommendation_id,
                    displayed_policy_version=refreshed.policy_version,
                ),
                idempotency_key=f"d16cast-{run_id}-ravi-reject-req",
            )
            assert reject_req.code == "SLOT_REQUESTED"
            rejected = await reject_appointment(
                session,
                ops,
                shipment_id="SHP-D16-RAVI",
                command=RejectAppointmentCommand(
                    appointment_id=reject_req.appointment_id or "",
                    rejection_reason="Cast smoke warehouse reject",
                ),
                idempotency_key=f"d16cast-{run_id}-ops-reject",
            )
            assert rejected.code == "APPOINTMENT_REJECTED"

            if len(free) > 1:
                confirm_options = await find_feasible_slots(session, ravi, "SHP-D16-RAVI", limit=5)
                assert confirm_options.options
                confirm_req = await request_slot(
                    session,
                    ravi,
                    shipment_id="SHP-D16-RAVI",
                    slot_id=confirm_options.options[0].slot_id,
                    command=RequestSlotCommand(
                        note="cast smoke confirm target",
                        displayed_recommendation_id=confirm_options.recommendation_id,
                        displayed_policy_version=confirm_options.policy_version,
                    ),
                    idempotency_key=f"d16cast-{run_id}-ravi-confirm-req",
                )
                if confirm_req.code == "SLOT_REQUESTED" and confirm_req.appointment_id:
                    confirmed = await confirm_appointment(
                        session,
                        ops,
                        shipment_id="SHP-D16-RAVI",
                        command=ConfirmAppointmentCommand(
                            appointment_id=confirm_req.appointment_id,
                            warehouse_confirmation_ref=f"WH-D16-{run_id}",
                        ),
                        idempotency_key=f"d16cast-{run_id}-ops-confirm",
                    )
                    assert confirmed.code == "APPOINTMENT_CONFIRMED"
                    await cancel_appointment(
                        session,
                        ops,
                        shipment_id="SHP-D16-RAVI",
                        command=CancelAppointmentCommand(
                            appointment_id=confirm_req.appointment_id,
                            cancellation_reason="Cleanup after cast confirm smoke",
                        ),
                        idempotency_key=f"d16cast-{run_id}-ops-cleanup-confirm",
                    )
    finally:
        await _cleanup_cast_writes(session_factory, run_id)
        await engine.dispose()
