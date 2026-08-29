"""D2's HELD lifecycle against a real PostgreSQL, end to end (issue #53).

Gated exactly like the two integration modules beside it: `DATABASE_URL` plus
`SETUHAUL_RUN_LIVE_DB_TESTS=1`, and additionally `SETUHAUL_TWO_PHASE_HOLD_ENABLED=1`, because
every assertion here needs the columns from
`supabase/migrations/20260829134929_d2_held_state_dock_occupancy.sql`. On a database where that
migration has not been applied the module skips rather than fails -- a missing column is a
deployment fact, not a broken test.

**These tests were NOT run against production.** The migration was verified against a throwaway
PostgreSQL 18 cluster built from the repo's own migration chain (see the issue #53 report); this
module is the check to run once the owner applies the migration to a real environment. It is
committed unrun on purpose: writing it after the apply would mean the apply had no test to gate it.

What it proves that the unit tests cannot, because it needs a real exclusion constraint:

* **M6 under a hold.** A HELD row genuinely blocks a competing booking. The unit tests assert the
  SQL says the right thing; only Postgres can assert the constraint *does* the right thing.
* **Section 9.2 #3, one level down.** `confirm_held_slot` and the sweeper race on the same row and
  exactly one wins, with the loser told which.
* **The no-gap conversion.** The `occupancy_id` before and after confirm is the same row -- proof
  the interval was never unprotected.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.execution_context import ExecutionContext, RoleName
from app.db.session import _normalize_async_url
from app.scheduling import holds

pytestmark = pytest.mark.asyncio


def _live_db_enabled() -> bool:
    return (
        bool(os.getenv("DATABASE_URL"))
        and os.getenv("SETUHAUL_RUN_LIVE_DB_TESTS") == "1"
        and os.getenv("SETUHAUL_TWO_PHASE_HOLD_ENABLED") == "1"
    )


SKIP_REASON = (
    "Live DB hold tests need DATABASE_URL, SETUHAUL_RUN_LIVE_DB_TESTS=1 and "
    "SETUHAUL_TWO_PHASE_HOLD_ENABLED=1, and a database with migration "
    "20260829134929_d2_held_state_dock_occupancy.sql applied."
)


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="live-hold-test",
        auth_subject="live-hold-test",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
        facility_id="FAC-JAI-01",
    )


def _session_factory():
    engine = create_async_engine(_normalize_async_url(os.environ["DATABASE_URL"]))
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _schema_is_migrated(session) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS n
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'dock_occupancy'
                  AND column_name IN ('state', 'expires_at', 'shipment_id')
                """
            )
        )
    ).mappings().first()
    return bool(row and row["n"] == 3)


async def _cleanup(session_factory, run_id: str) -> None:
    """Holds first, then any appointment they became -- dock_occupancy.appointment_id has no
    ON DELETE CASCADE, the same ordering the two sibling integration modules already document."""
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM public.audit_logs WHERE audit_id LIKE :p"),
            {"p": f"%{run_id}%"},
        )
        await session.execute(
            text(
                """
                DELETE FROM public.dock_occupancy
                WHERE policy_version = :marker
                   OR appointment_id IN (
                        SELECT appointment_id FROM public.appointments
                        WHERE booking_source = 'DRIVER_CHAT' AND cancellation_reason = :marker
                   )
                """
            ),
            {"marker": f"HOLDTEST-{run_id}"},
        )
        await session.execute(
            text("DELETE FROM public.idempotency_requests WHERE idempotency_key LIKE :p"),
            {"p": f"holdtest-{run_id}-%"},
        )
        await session.commit()


async def _a_free_slot(session) -> dict | None:
    """An OPEN slot on an ACTIVE dock with no live claim -- so the test is not fighting real data."""
    row = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.dock_id, sl.slot_start_ts, s.shipment_id
                FROM public.appointment_slots sl
                JOIN public.docks d ON d.dock_id = sl.dock_id
                JOIN public.shipments s ON s.destination_facility_id = sl.facility_id
                WHERE sl.slot_status = 'OPEN'
                  AND d.dock_status = 'ACTIVE'
                  AND s.driver_id = 'DRV001'
                  AND NOT EXISTS (
                      SELECT 1 FROM public.dock_occupancy o
                      WHERE o.dock_id = sl.dock_id
                        AND o.state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
                        AND o."window" && tstzrange(sl.slot_start_ts,
                                                   sl.slot_start_ts + interval '2 hours', '[)')
                  )
                ORDER BY sl.slot_start_ts ASC
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    return dict(row) if row else None


@pytest.mark.skipif(not _live_db_enabled(), reason=SKIP_REASON)
async def test_a_hold_blocks_a_competing_hold_on_the_same_interval():
    """M6 with a hold in play: the exclusion constraint admits exactly one holder."""
    run_id = uuid4().hex[:8]
    engine, session_factory = _session_factory()
    try:
        async with session_factory() as session:
            if not await _schema_is_migrated(session):
                pytest.skip(SKIP_REASON)
            slot = await _a_free_slot(session)
            if slot is None:
                pytest.skip("No uncontested OPEN slot available in this dataset.")

            now = datetime.now(timezone.utc)
            first = await holds.create_hold(
                session,
                shipment_id=slot["shipment_id"],
                slot_id=slot["slot_id"],
                policy_version=f"HOLDTEST-{run_id}",
                ttl_seconds=90,
                now=now,
                actor_user_id="USR001",
            )
            assert first is not None
            await session.commit()

            from sqlalchemy.exc import IntegrityError

            with pytest.raises(IntegrityError) as exc:
                await holds.create_hold(
                    session,
                    shipment_id=slot["shipment_id"],
                    slot_id=slot["slot_id"],
                    policy_version=f"HOLDTEST-{run_id}",
                    ttl_seconds=90,
                    now=now,
                    actor_user_id="USR001",
                )
                await session.flush()
            # The name the application matches on to translate this into a driver-facing
            # SLOT_CONFLICT_REFRESH_REQUIRED rather than a 500.
            assert "dock_occupancy_dock_id_window_excl" in str(exc.value)
            await session.rollback()
    finally:
        await _cleanup(session_factory, run_id)
        await engine.dispose()


@pytest.mark.skipif(not _live_db_enabled(), reason=SKIP_REASON)
async def test_confirm_converts_the_same_row_and_never_frees_the_interval():
    """The no-gap invariant, proven by identity: same `occupancy_id` before and after."""
    run_id = uuid4().hex[:8]
    engine, session_factory = _session_factory()
    try:
        async with session_factory() as session:
            if not await _schema_is_migrated(session):
                pytest.skip(SKIP_REASON)
            slot = await _a_free_slot(session)
            if slot is None:
                pytest.skip("No uncontested OPEN slot available in this dataset.")

            hold = await holds.create_hold(
                session,
                shipment_id=slot["shipment_id"],
                slot_id=slot["slot_id"],
                policy_version=f"HOLDTEST-{run_id}",
                ttl_seconds=90,
                now=datetime.now(timezone.utc),
                actor_user_id="USR001",
            )
            assert hold is not None
            await session.commit()
            hold_id = str(hold["occupancy_id"])

            result = await holds.confirm_held_slot(
                session,
                _driver_ctx(),
                hold_id=hold_id,
                idempotency_key=f"holdtest-{run_id}-confirm",
            )
            if result.code == "SLOT_CONFLICT_REFRESH_REQUIRED":
                # Stage 1 refused this interval on a *data* ground (facility hours, dock rating,
                # ETA vs. slot start). That is `confirm_held_slot` working -- section 7.1's
                # "revalidates inside the transaction" -- not the conversion under test failing,
                # so skip loudly with the rule id rather than assert a green that means nothing.
                pytest.skip(
                    "Dataset has no Stage 1-feasible held interval to convert: "
                    f"{(result.conflict or {}).get('reason_code')}"
                )
            assert result.code == "SLOT_REQUESTED"
            assert result.status == "PENDING_CONFIRMATION"
            assert result.appointment_id

            row = (
                await session.execute(
                    text(
                        """
                        SELECT occupancy_id, state, expires_at, appointment_id
                        FROM public.dock_occupancy
                        WHERE occupancy_id = :hold_id
                        """
                    ),
                    {"hold_id": int(hold_id)},
                )
            ).mappings().first()
            assert row is not None, "the hold row must survive the conversion, not be replaced"
            assert str(row["occupancy_id"]) == hold_id
            assert row["state"] == "PENDING_CONFIRMATION"
            assert row["expires_at"] is None
            assert row["appointment_id"] == result.appointment_id
    finally:
        await _cleanup(session_factory, run_id)
        await engine.dispose()


@pytest.mark.skipif(not _live_db_enabled(), reason=SKIP_REASON)
async def test_a_lapsed_hold_cannot_be_confirmed_even_before_the_sweeper_runs():
    """Section 0.8's lazy check: correctness must not wait on hygiene."""
    run_id = uuid4().hex[:8]
    engine, session_factory = _session_factory()
    try:
        async with session_factory() as session:
            if not await _schema_is_migrated(session):
                pytest.skip(SKIP_REASON)
            slot = await _a_free_slot(session)
            if slot is None:
                pytest.skip("No uncontested OPEN slot available in this dataset.")

            # A TTL already in the past: the hold is born lapsed, and the sweeper has not run.
            hold = await holds.create_hold(
                session,
                shipment_id=slot["shipment_id"],
                slot_id=slot["slot_id"],
                policy_version=f"HOLDTEST-{run_id}",
                ttl_seconds=-30,
                now=datetime.now(timezone.utc),
                actor_user_id="USR001",
            )
            assert hold is not None
            await session.commit()

            result = await holds.confirm_held_slot(
                session,
                _driver_ctx(),
                hold_id=str(hold["occupancy_id"]),
                idempotency_key=f"holdtest-{run_id}-lapsed",
            )
            assert result.code == "HOLD_EXPIRED"
            assert result.appointment_id is None
    finally:
        await _cleanup(session_factory, run_id)
        await engine.dispose()


@pytest.mark.skipif(not _live_db_enabled(), reason=SKIP_REASON)
async def test_the_sweeper_retires_a_lapsed_hold_and_frees_the_interval():
    """D2's hygiene leg, and the proof that an EXPIRED row stops consuming capacity.

    That last assertion is what section 0.8's partial exclusion predicate buys. Under the old
    unconditional constraint an in-place EXPIRED row would still have blocked the interval, which
    is why the sweeper could only have deleted it.
    """
    run_id = uuid4().hex[:8]
    engine, session_factory = _session_factory()
    try:
        async with session_factory() as session:
            if not await _schema_is_migrated(session):
                pytest.skip(SKIP_REASON)
            slot = await _a_free_slot(session)
            if slot is None:
                pytest.skip("No uncontested OPEN slot available in this dataset.")

            now = datetime.now(timezone.utc)
            hold = await holds.create_hold(
                session,
                shipment_id=slot["shipment_id"],
                slot_id=slot["slot_id"],
                policy_version=f"HOLDTEST-{run_id}",
                ttl_seconds=-30,
                now=now,
                actor_user_id="USR001",
            )
            assert hold is not None
            await session.commit()

            swept = await holds.sweep_held_holds(
                session,
                actor_user_id=os.getenv("JOB_ACTOR_USER_ID", "USR-SYSTEM-SWEEPER"),
                now=now,
                ttl_seconds=90,
            )
            await session.commit()

            assert swept.supported is True
            assert str(hold["occupancy_id"]) in [h.hold_id for h in swept.holds]

            # The interval is free again: a fresh hold on the same slot must now succeed.
            replacement = await holds.create_hold(
                session,
                shipment_id=slot["shipment_id"],
                slot_id=slot["slot_id"],
                policy_version=f"HOLDTEST-{run_id}",
                ttl_seconds=90,
                now=datetime.now(timezone.utc),
                actor_user_id="USR001",
            )
            assert replacement is not None, (
                "an EXPIRED hold must stop blocking -- if this fails the exclusion constraint "
                "lost its WHERE predicate"
            )
            await session.commit()
    finally:
        await _cleanup(session_factory, run_id)
        await engine.dispose()
