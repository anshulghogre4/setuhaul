"""E3.6 (issue #30) tests for the SS7.5.1 planner dock-blocking writes.

`block_dock`/`end_dock_block`/`get_dock_block_impact` each run a short, fixed sequence of raw
`session.execute` calls -- `_session_with(...)` below supplies mock results for that sequence in
call order, the same shape `test_scheduling_feasibility.py`'s `_eligibility_session` already uses
for `explain_slot_eligibility`. `lookup_idempotency`/`store_idempotency` are monkeypatched directly
rather than mocked at the SQL level, since their own behaviour is already covered by
`test_scheduling_allocation.py`'s idempotency tests -- these tests are about `planner_service`'s
own logic, not re-proving the shared idempotency helper.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services import planner_service

FACILITY = "FAC-JAI-01"
OTHER_FACILITY = "FAC-GGN-01"
DOCK = "DOCK-JAI-D1"


def _planner_ctx(*, facility_id: str = FACILITY, role: RoleName = RoleName.WAREHOUSE_PLANNER) -> ExecutionContext:
    return ExecutionContext(
        request_id="req-planner-1",
        auth_subject="sub-planner-1",
        user_id="USR-PLN-1",
        email="planner@setuhaul.com",
        full_name="Test Planner",
        role_id="ROL003",
        role_name=role,
        facility_id=facility_id,
    )


def _session_with(*results) -> AsyncMock:
    """AsyncMock session returning `results` from successive `session.execute()` calls, in order.

    A `dict` becomes a single-row result (`.mappings().first()`/`.one()`); a `list` becomes a
    multi-row result (`.mappings().all()`); `None` is both "no row" and "write with nothing read
    back" -- callers that don't inspect a write's return value don't care which.
    """
    mocks = []
    for r in results:
        m = MagicMock()
        if isinstance(r, list):
            m.mappings.return_value.all.return_value = r
            m.mappings.return_value.first.return_value = r[0] if r else None
        else:
            m.mappings.return_value.first.return_value = r
            m.mappings.return_value.one.return_value = r
            m.mappings.return_value.all.return_value = [r] if r else []
        mocks.append(m)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mocks)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _dock_row(*, dock_id: str = DOCK, facility_id: str = FACILITY) -> dict:
    return {"dock_id": dock_id, "facility_id": facility_id, "dock_code": "D1", "dock_status": "ACTIVE"}


@pytest.fixture(autouse=True)
def _no_idempotency_replay(monkeypatch):
    """Every `block_dock` test starts with "not a replay" unless a test overrides this."""
    monkeypatch.setattr(planner_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(planner_service, "store_idempotency", AsyncMock())


# ---------------------------------------------------------------------------------------------
# get_dock_block_impact -- pure read, the FR-PLN-007 preview.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dock_block_impact_reports_affected_appointments_and_no_conflict():
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    affected = [{"appointment_id": "APT1", "shipment_id": "SHP1", "driver_id": "DRV1"}]
    session = _session_with(_dock_row(), affected, None)

    result = await planner_service.get_dock_block_impact(
        session, _planner_ctx(), dock_id=DOCK, window_start=start, window_end=end
    )

    assert result.affected_count == 1
    assert result.affected_appointments == affected
    assert result.conflicting_event is None


@pytest.mark.asyncio
async def test_dock_block_impact_refuses_a_dock_outside_the_callers_facility():
    session = _session_with(_dock_row(facility_id=OTHER_FACILITY))
    with pytest.raises(AppError) as exc:
        await planner_service.get_dock_block_impact(
            session, _planner_ctx(facility_id=FACILITY), dock_id=DOCK,
            window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_dock_block_impact_rejects_a_window_that_does_not_advance_time():
    session = _session_with(_dock_row())
    now = datetime.now(timezone.utc)
    with pytest.raises(AppError) as exc:
        await planner_service.get_dock_block_impact(
            session, _planner_ctx(), dock_id=DOCK, window_start=now, window_end=now
        )
    assert exc.value.code == "INVALID_WINDOW"


# ---------------------------------------------------------------------------------------------
# block_dock -- FR-PLN-007.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_dock_blocks_and_opens_one_cascade_escalation_for_the_affected_set():
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    affected = [
        {"appointment_id": "APT1", "shipment_id": "SHP1", "driver_id": "DRV1",
         "appointment_status": "CONFIRMED", "window_start": start, "window_end": end},
    ]
    session = _session_with(
        _dock_row(),          # _dock_in_scope
        None,                  # _overlapping_block -> no conflict
        affected,              # _affected_appointments
        None,                  # INSERT dock_status_events
        {"escalation_id": "ESC-1"},  # INSERT escalation_queue ... RETURNING
        None,                  # INSERT audit_logs
    )

    result = await planner_service.block_dock(
        session, _planner_ctx(), dock_id=DOCK, window_start=start, window_end=end,
        reason="Forklift breakdown", idempotency_key="key-1",
    )

    assert result.code == "BLOCKED"
    assert result.affected_count == 1
    assert result.escalation_id == "ESC-1"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_block_dock_opens_no_escalation_when_nothing_is_stranded():
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    session = _session_with(
        _dock_row(), None, [],  # dock, no conflict, nothing affected
        None,  # INSERT dock_status_events
        None,  # INSERT audit_logs (no escalation insert -- affected is empty)
    )

    result = await planner_service.block_dock(
        session, _planner_ctx(), dock_id=DOCK, window_start=start, window_end=end,
        reason="Maintenance", idempotency_key="key-2",
    )

    assert result.code == "BLOCKED"
    assert result.affected_count == 0
    assert result.escalation_id is None


@pytest.mark.asyncio
async def test_block_dock_names_the_conflicting_event_without_writing_anything():
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    conflicting = {"dock_event_id": "DEVT-EXISTING", "event_type": "MAINTENANCE"}
    session = _session_with(_dock_row(), conflicting)

    result = await planner_service.block_dock(
        session, _planner_ctx(), dock_id=DOCK, window_start=start, window_end=end,
        reason="Second block attempt", idempotency_key="key-3",
    )

    assert result.code == "ALREADY_BLOCKED"
    assert result.conflicting_event == conflicting
    # Only the dock check + the overlap check ran -- no INSERT statements were reached.
    assert session.execute.await_count == 2
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_block_dock_replays_a_repeated_idempotency_key_without_touching_the_database(monkeypatch):
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    prior_response = planner_service.DockBlockResult(
        as_of="2026-08-24T09:00:00+00:00", code="BLOCKED", dock_id=DOCK, facility_id=FACILITY,
        dock_status_event_id="DEVT-1", window_start=start, window_end=end, reason="r",
        idempotency_key="key-replay",
    ).model_dump()
    monkeypatch.setattr(
        planner_service, "lookup_idempotency",
        AsyncMock(return_value={"response": prior_response, "status_code": 200, "replayed": True}),
    )
    session = AsyncMock()
    session.execute = AsyncMock()

    result = await planner_service.block_dock(
        session, _planner_ctx(), dock_id=DOCK, window_start=start, window_end=end,
        reason="r", idempotency_key="key-replay",
    )

    assert result.idempotent_replay is True
    assert result.code == "BLOCKED"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_block_dock_refuses_a_dock_outside_the_callers_facility():
    session = _session_with(_dock_row(facility_id=OTHER_FACILITY))
    start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(AppError) as exc:
        await planner_service.block_dock(
            session, _planner_ctx(facility_id=FACILITY), dock_id=DOCK,
            window_start=start, window_end=start + timedelta(hours=1),
            reason="r", idempotency_key="key-4",
        )
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_block_dock_rejects_an_inverted_window_before_any_query_runs():
    session = AsyncMock()
    session.execute = AsyncMock()
    now = datetime.now(timezone.utc)
    with pytest.raises(AppError) as exc:
        await planner_service.block_dock(
            session, _planner_ctx(), dock_id=DOCK, window_start=now, window_end=now - timedelta(minutes=1),
            reason="r", idempotency_key="key-5",
        )
    assert exc.value.code == "INVALID_WINDOW"


# ---------------------------------------------------------------------------------------------
# end_dock_block -- FR-PLN-008.
# ---------------------------------------------------------------------------------------------


def _event_row(*, event_type: str = "MANUAL_BLOCK", start=None, end=None, facility_id: str = FACILITY) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "dock_event_id": "DEVT-1", "dock_id": DOCK, "event_type": event_type,
        "event_start_ts": start or (now - timedelta(hours=1)),
        "event_end_ts": end, "reason": "test", "facility_id": facility_id,
    }


@pytest.mark.asyncio
async def test_end_dock_block_truncates_an_in_progress_block_at_now():
    now = datetime.now(timezone.utc)
    event = _event_row(start=now - timedelta(hours=1), end=None)
    session = _session_with(event, None, None)  # event, UPDATE, audit

    result = await planner_service.end_dock_block(session, _planner_ctx(), dock_status_event_id="DEVT-1")

    assert result.code == "UNBLOCKED"
    assert result.window_end is not None
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_end_dock_block_deletes_a_block_that_has_not_started_yet():
    now = datetime.now(timezone.utc)
    future_start = now + timedelta(hours=1)
    event = _event_row(start=future_start, end=None)
    session = _session_with(event, None, None)  # event, DELETE, audit

    result = await planner_service.end_dock_block(session, _planner_ctx(), dock_status_event_id="DEVT-1")

    assert result.code == "UNBLOCKED"
    assert result.window_end is None


@pytest.mark.asyncio
async def test_end_dock_block_reports_not_blocked_for_an_already_ended_event():
    now = datetime.now(timezone.utc)
    event = _event_row(start=now - timedelta(hours=2), end=now - timedelta(hours=1))
    session = _session_with(event)

    result = await planner_service.end_dock_block(session, _planner_ctx(), dock_status_event_id="DEVT-1")

    assert result.code == "NOT_BLOCKED"
    # Nothing was written -- only the initial SELECT ... FOR UPDATE ran.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_end_dock_block_reports_not_found_for_an_unknown_event():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await planner_service.end_dock_block(session, _planner_ctx(), dock_status_event_id="DEVT-GHOST")
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_end_dock_block_refuses_a_facility_outside_the_callers_scope():
    event = _event_row(facility_id=OTHER_FACILITY)
    session = _session_with(event)
    with pytest.raises(AppError) as exc:
        await planner_service.end_dock_block(
            session, _planner_ctx(facility_id=FACILITY), dock_status_event_id="DEVT-1"
        )
    assert exc.value.code == "FORBIDDEN"
