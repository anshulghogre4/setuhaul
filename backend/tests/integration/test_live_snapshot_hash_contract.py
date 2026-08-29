"""The producer/consumer `snapshot_hash` contract, checked against live rows (issue #61).

`tests/unit/test_planner_write_tools.py` already guards the *function* -- that
`snapshot.planner_snapshot_hash` and `planner_service._snapshot_hash` produce the same digest for
the same kwargs. That is necessary and not sufficient: the real divergence risk is that the two
*queries* feeding those functions disagree -- a different interval `COALESCE`, a different
`interval_source`, a different conflict set. Only live data can catch that, because it is a
property of two SQL statements read against one schema, not of two Python functions.

`get_planner_queue` (issue #60, `services/planner_service.py` + `repositories/operations.py`) is the
producer; `scheduling/snapshot.load_appointment_snapshots` is what `confirm_request`,
`counter_offer` and `bulk_confirm` recompute with under the row lock. If these ever disagree, every
confirm returns `SNAPSHOT_STALE` and no planner can action anything -- a total outage of the
throughput path that no mock-based test would see.

Read-only: one queue read plus one snapshot read per active facility, then a rollback.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.execution_context import ExecutionContext, RoleName
from app.db.session import _normalize_async_url
from app.scheduling import snapshot
from app.services import planner_service

pytestmark = pytest.mark.asyncio


def _live_db_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL")) and os.getenv("SETUHAUL_RUN_LIVE_DB_TESTS") == "1"


def _planner_ctx(facility_id: str) -> ExecutionContext:
    return ExecutionContext(
        request_id="live-snapshot-contract",
        auth_subject="live-snapshot-contract",
        user_id="USR101",
        email="planner@setuhaul.example",
        full_name="Live Contract Check",
        role_id="ROL002",
        role_name=RoleName.WAREHOUSE_PLANNER,
        facility_id=facility_id,
    )


@pytest.mark.skipif(
    not _live_db_enabled(), reason="requires DATABASE_URL and SETUHAUL_RUN_LIVE_DB_TESTS=1"
)
async def test_live_queue_snapshot_hash_equals_the_write_path_recomputation():
    engine = create_async_engine(
        _normalize_async_url(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    compared = 0
    try:
        async with session_factory() as session:
            facilities = [
                str(row[0])
                for row in (
                    await session.execute(
                        text("SELECT facility_id FROM public.facilities WHERE active_flag = 1")
                    )
                ).all()
            ]
            assert facilities, "no active facilities -- the check would pass vacuously"

            for facility_id in facilities:
                queue = await planner_service.get_planner_queue(
                    session, _planner_ctx(facility_id), facility_id=facility_id, limit=200
                )
                if not queue.items:
                    continue
                recomputed = await snapshot.load_appointment_snapshots(
                    session, [item.appointment_id for item in queue.items]
                )
                for item in queue.items:
                    mine = recomputed.get(item.appointment_id)
                    assert mine is not None, (
                        f"{item.appointment_id} is in the planner queue but the write path's "
                        "snapshot read returns no row for it -- confirm would 404 on a row the "
                        "planner can see."
                    )
                    assert mine["snapshot_hash"] == item.snapshot_hash, (
                        f"{item.appointment_id}: producer and consumer disagree. "
                        f"interval={mine['interval_start']}..{mine['interval_end']} "
                        f"source={mine['interval_source']} "
                        f"conflicts={[c['appointment_id'] for c in mine['conflicts']]}"
                    )
                    compared += 1

            await session.rollback()
    finally:
        await engine.dispose()

    # Not an assertion that the fixture has rows -- a queue can legitimately be empty -- but the
    # count is reported so a run that compared nothing is visible rather than silently green.
    print(f"compared {compared} live planner-queue rows")
