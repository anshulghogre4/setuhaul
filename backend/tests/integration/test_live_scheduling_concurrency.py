import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.execution_context import ExecutionContext, RoleName
from app.db.session import _normalize_async_url
from app.scheduling.allocation import RequestSlotCommand, request_slot


pytestmark = pytest.mark.asyncio


def _live_db_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL")) and os.getenv("SETUHAUL_RUN_LIVE_DB_TESTS") == "1"


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="live-concurrency-test",
        auth_subject="live-concurrency-test",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
        facility_id="FAC-JAI-01",
    )


async def _cleanup(session_factory, run_id: str) -> None:
    slot_id = f"SLOT-CODX-{run_id}"
    shipment_prefix = f"SHP-CODX-{run_id}-%"
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM public.idempotency_requests WHERE idempotency_key LIKE :prefix"),
            {"prefix": f"codx-{run_id}-%"},
        )
        await session.execute(
            text(
                """
                DELETE FROM public.audit_logs
                WHERE entity_name = 'appointments'
                  AND entity_id IN (
                    SELECT appointment_id
                    FROM public.appointments
                    WHERE slot_id = :slot_id
                       OR shipment_id LIKE :shipment_prefix
                  )
                """
            ),
            {
                "slot_id": slot_id,
                "shipment_prefix": shipment_prefix,
            },
        )
        # dock_occupancy.appointment_id has no ON DELETE CASCADE, so the D1 capacity claims
        # written by request_slot must go before the appointments they reference.
        await session.execute(
            text(
                """
                DELETE FROM public.dock_occupancy
                WHERE appointment_id IN (
                    SELECT appointment_id
                    FROM public.appointments
                    WHERE slot_id = :slot_id
                       OR shipment_id LIKE :shipment_prefix
                )
                """
            ),
            {
                "slot_id": slot_id,
                "shipment_prefix": shipment_prefix,
            },
        )
        await session.execute(
            text(
                """
                DELETE FROM public.appointments
                WHERE slot_id = :slot_id
                   OR shipment_id LIKE :shipment_prefix
                """
            ),
            {
                "slot_id": slot_id,
                "shipment_prefix": shipment_prefix,
            },
        )
        await session.execute(
            text("DELETE FROM public.appointment_slots WHERE slot_id = :slot_id"),
            {"slot_id": slot_id},
        )
        await session.execute(
            text("DELETE FROM public.shipments WHERE shipment_id LIKE :prefix"),
            {"prefix": shipment_prefix},
        )
        await session.commit()


async def _seed_competing_shipments(session_factory, run_id: str) -> tuple[list[str], str]:
    now = "2026-08-10T20:30:00+05:30"
    slot_id = f"SLOT-CODX-{run_id}"
    shipment_ids = [f"SHP-CODX-{run_id}-A", f"SHP-CODX-{run_id}-B"]
    slot_start = datetime(2099, 1, 1, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))) + timedelta(
        minutes=int(run_id[:6], 16) % 240
    )
    slot_end = slot_start + timedelta(hours=1)
    eta = slot_start - timedelta(minutes=15)
    async with session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO public.appointment_slots (
                  slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts,
                  slot_status, block_reason, created_at
                ) VALUES (
                  :slot_id, 'FAC-JAI-01', 'DOCK-JAI-D1',
                  :slot_start_ts, :slot_end_ts,
                  'OPEN', NULL, :now
                )
                """
            ),
            {
                "slot_id": slot_id,
                "slot_start_ts": slot_start.isoformat(),
                "slot_end_ts": slot_end.isoformat(),
                "now": now,
            },
        )
        for shipment_id in shipment_ids:
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
                      :shipment_id, :order_reference, 'CAR001', 'DRV001', 'VEH001',
                      'Codex Test Origin', 'Jaipur', 'FAC-JAI-01', 'Codex Test Customer',
                      'GENERAL', 10000, 10, 'STANDARD',
                      0, 'HIGH', :planned_departure_ts,
                      :actual_departure_ts, :eta_ts,
                      :eta_ts, 45, 'IN_TRANSIT', :now, :now
                    )
                    """
                ),
                {
                    "shipment_id": shipment_id,
                    "order_reference": f"ORD-CODX-{run_id}-{shipment_id[-1]}",
                    "planned_departure_ts": (eta - timedelta(hours=4)).isoformat(),
                    "actual_departure_ts": (eta - timedelta(hours=3, minutes=30)).isoformat(),
                    "eta_ts": eta.isoformat(),
                    "now": now,
                },
            )
        await session.commit()
    return shipment_ids, slot_id


async def _request(session_factory, shipment_id: str, slot_id: str, key: str):
    async with session_factory() as session:
        return await request_slot(
            session,
            _driver_ctx(),
            shipment_id=shipment_id,
            slot_id=slot_id,
            command=RequestSlotCommand(
                note="Live concurrency proof request.",
                displayed_policy_version="sprint3_constraints_v1",
            ),
            idempotency_key=key,
        )


@pytest.mark.skipif(not _live_db_enabled(), reason="requires DATABASE_URL and SETUHAUL_RUN_LIVE_DB_TESTS=1")
async def test_live_same_slot_competition_has_one_winner_and_conflict_refresh():
    engine = create_async_engine(
        _normalize_async_url(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id = uuid4().hex[:10].upper()
    await _cleanup(session_factory, run_id)
    try:
        shipment_ids, slot_id = await _seed_competing_shipments(session_factory, run_id)
        results = await asyncio.gather(
            _request(session_factory, shipment_ids[0], slot_id, f"codx-{run_id}-a"),
            _request(session_factory, shipment_ids[1], slot_id, f"codx-{run_id}-b"),
        )

        winners = [result for result in results if result.code == "SLOT_REQUESTED"]
        conflicts = [result for result in results if result.code == "SLOT_CONFLICT_REFRESH_REQUIRED"]
        assert len(winners) == 1
        assert len(conflicts) == 1
        assert winners[0].appointment_writes == 1
        assert conflicts[0].appointment_writes == 0
        assert conflicts[0].refreshed_options is not None

        async with session_factory() as session:
            active_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM public.appointments
                    WHERE slot_id = :slot_id
                      AND appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                    """
                ),
                {"slot_id": slot_id},
            )
            audit_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM public.audit_logs
                    WHERE entity_id = :appointment_id
                      AND action_type = 'BOOK_APPOINTMENT'
                    """
                ),
                {"appointment_id": winners[0].appointment_id},
            )
            idempotency_count = await session.scalar(
                text("SELECT count(*) FROM public.idempotency_requests WHERE idempotency_key LIKE :prefix"),
                {"prefix": f"codx-{run_id}-%"},
            )

        assert active_count == 1
        assert audit_count == 1
        assert idempotency_count == 2
    finally:
        await _cleanup(session_factory, run_id)
        await engine.dispose()
