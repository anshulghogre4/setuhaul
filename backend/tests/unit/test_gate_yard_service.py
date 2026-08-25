"""E3.6 (issue #30) tests for the SS7.5.2 gate/yard writes.

Same `_session_with(...)` sequential-mock shape as `test_planner_service.py` -- see that file's
module docstring for the reasoning. `classify_arrival` gets direct coverage of its own since it is
the one calibrated business rule in this module (`ON_TIME_WINDOW_MIN`, derived from five live
Layer A rows per `gate_yard_service.py`'s own comment).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services import gate_yard_service

FACILITY = "FAC-JAI-01"
OTHER_FACILITY = "FAC-GGN-01"
SHIPMENT = "SHP1017"


def _gate_ctx(*, facility_id: str = FACILITY, role: RoleName = RoleName.WAREHOUSE_PLANNER) -> ExecutionContext:
    return ExecutionContext(
        request_id="req-gate-1",
        auth_subject="sub-gate-1",
        user_id="USR-GATE-1",
        email="gate@setuhaul.com",
        full_name="Test Gate Officer",
        role_id="ROL003",
        role_name=role,
        facility_id=facility_id,
    )


def _session_with(*results) -> AsyncMock:
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


def _shipment_row(*, facility_id: str = FACILITY, expected_unload_min: int = 45) -> dict:
    return {
        "shipment_id": SHIPMENT, "facility_id": facility_id, "driver_id": "DRV001",
        "expected_unload_min": expected_unload_min, "current_status": "IN_TRANSIT",
    }


def _appointment_row(*, dock_id: str = "DOCK-JAI-D1", slot_start: datetime | None = None) -> dict:
    start = slot_start or datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    return {
        "appointment_id": "APT1017", "appointment_status": "CONFIRMED", "slot_id": "SLT1017",
        "dock_id": dock_id, "slot_start_ts": start, "slot_end_ts": start + timedelta(hours=1),
        "dock_code": "D1",
    }


def _checkin_row(**overrides) -> dict:
    base = {
        "checkin_id": "CHK1017", "shipment_id": SHIPMENT, "facility_id": FACILITY,
        "gate_in_ts": None, "yard_queue_enter_ts": None, "dock_in_ts": None,
        "unload_start_ts": None, "unload_end_ts": None, "gate_out_ts": None,
        "arrival_state": None, "queue_state": None, "queue_position": None,
        "actual_dock_id": None, "notes": None, "updated_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _no_idempotency_replay(monkeypatch):
    monkeypatch.setattr(gate_yard_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(gate_yard_service, "store_idempotency", AsyncMock())


# ---------------------------------------------------------------------------------------------
# classify_arrival -- the calibrated EARLY/ON_TIME/LATE boundary.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutes_from_slot_start", "expected"),
    [
        (-25, "EARLY"),   # CHK1001
        (-2, "ON_TIME"),  # CHK1002
        (-40, "EARLY"),   # CHK1003
        (25, "LATE"),     # CHK1004
        (5, "LATE"),      # CHK1005
        (-15, "ON_TIME"),  # exact boundary, inclusive
        (-15.01, "EARLY"),
        (0, "ON_TIME"),
    ],
)
def test_classify_arrival_matches_the_five_live_layer_a_rows(minutes_from_slot_start, expected):
    assert gate_yard_service.classify_arrival(minutes_from_slot_start) == expected


# ---------------------------------------------------------------------------------------------
# record_gate_in -- FR-GATE-004.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_gate_in_records_early_arrival_and_sets_waiting_early():
    slot_start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    event_ts = slot_start - timedelta(minutes=25)
    session = _session_with(
        _shipment_row(),           # _shipment_in_scope
        _appointment_row(slot_start=slot_start),  # _active_appointment
        None,                       # _locked_checkin -- no existing row
        None,                       # early_limit rule lookup
        None,                       # INSERT facility_checkins
        None,                       # _project_shipment_status UPDATE
        None,                       # audit INSERT
    )

    result = await gate_yard_service.record_gate_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, ts=event_ts, idempotency_key="gk-1"
    )

    assert result.code == "GATE_IN_RECORDED"
    assert result.arrival_state == "EARLY"
    assert result.queue_state == "WAITING_EARLY"
    assert result.early_limit_min == gate_yard_service.DEFAULT_EARLY_LIMIT_MIN
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_record_gate_in_flags_beyond_the_facility_early_limit():
    slot_start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    event_ts = slot_start - timedelta(minutes=90)  # beyond the 60-min default limit
    session = _session_with(
        _shipment_row(), _appointment_row(slot_start=slot_start), None, None,
        None, None, None,
    )
    result = await gate_yard_service.record_gate_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, ts=event_ts, idempotency_key="gk-2"
    )
    assert result.beyond_early_limit is True


@pytest.mark.asyncio
async def test_record_gate_in_refuses_a_walk_in_with_no_active_appointment():
    session = _session_with(_shipment_row(), None)  # shipment, no active appointment
    result = await gate_yard_service.record_gate_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, ts=None, idempotency_key="gk-3"
    )
    assert result.code == "NO_ACTIVE_APPOINTMENT"
    # Nothing about a check-in row was ever queried or written.
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_record_gate_in_reports_already_checked_in_without_rewriting():
    existing = _checkin_row(gate_in_ts=datetime.now(timezone.utc), arrival_state="ON_TIME", queue_state="WAITING_EARLY")
    session = _session_with(_shipment_row(), _appointment_row(), existing)
    result = await gate_yard_service.record_gate_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, ts=None, idempotency_key="gk-4"
    )
    assert result.code == "ALREADY_CHECKED_IN"
    assert result.checkin_id == "CHK1017"


@pytest.mark.asyncio
async def test_record_gate_in_refuses_a_shipment_outside_the_callers_facility():
    session = _session_with(_shipment_row(facility_id=OTHER_FACILITY))
    with pytest.raises(AppError) as exc:
        await gate_yard_service.record_gate_in(
            session, _gate_ctx(facility_id=FACILITY), shipment_id=SHIPMENT, ts=None,
            idempotency_key="gk-5",
        )
    assert exc.value.code == "FORBIDDEN"


# ---------------------------------------------------------------------------------------------
# update_queue_state -- FR-GATE-005.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_queue_state_moves_waiting_to_called_to_dock():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="WAITING_EARLY", queue_position=2)
    session = _session_with(_shipment_row(), checkin, None, None, None)  # shipment, checkin, UPDATE, project, audit

    result = await gate_yard_service.update_queue_state(
        session, _gate_ctx(), shipment_id=SHIPMENT, queue_state="CALLED_TO_DOCK"
    )

    assert result.code == "QUEUE_UPDATED"
    assert result.queue_state == "CALLED_TO_DOCK"
    assert result.queue_position is None  # position dropped once no longer queued


@pytest.mark.asyncio
async def test_update_queue_state_refuses_a_transition_the_state_machine_forbids():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="IN_DOCK")
    session = _session_with(_shipment_row(), checkin)

    result = await gate_yard_service.update_queue_state(
        session, _gate_ctx(), shipment_id=SHIPMENT, queue_state="WAITING_EARLY"
    )

    assert result.code == "INVALID_TRANSITION"
    assert result.queue_state == "IN_DOCK"  # current state named, not silently refused


@pytest.mark.asyncio
async def test_update_queue_state_rejects_an_unknown_state_before_any_query_runs():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await gate_yard_service.update_queue_state(
            session, _gate_ctx(), shipment_id=SHIPMENT, queue_state="TELEPORTED"
        )
    assert exc.value.code == "INVALID_QUEUE_STATE"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_queue_state_requires_a_positive_queue_position():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await gate_yard_service.update_queue_state(
            session, _gate_ctx(), shipment_id=SHIPMENT, queue_state="WAITING_EARLY", queue_position=0
        )
    assert exc.value.code == "INVALID_QUEUE_POSITION"


@pytest.mark.asyncio
async def test_update_queue_state_refuses_a_truck_that_was_never_gated_in():
    session = _session_with(_shipment_row(), None)
    with pytest.raises(AppError) as exc:
        await gate_yard_service.update_queue_state(
            session, _gate_ctx(), shipment_id=SHIPMENT, queue_state="WAITING_EARLY"
        )
    assert exc.value.code == "NOT_CHECKED_IN"


# ---------------------------------------------------------------------------------------------
# record_dock_in -- FR-GATE-006.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_dock_in_records_a_clean_arrival_at_the_confirmed_dock():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="CALLED_TO_DOCK")
    session = _session_with(
        _shipment_row(),                       # _shipment_in_scope
        {"dock_id": "DOCK-JAI-D1", "facility_id": FACILITY, "dock_code": "D1"},  # dock lookup
        checkin,                                # _locked_checkin
        None,                                   # _live_dock_occupant -- nobody there
        _appointment_row(dock_id="DOCK-JAI-D1"),  # _active_appointment
        None,                                   # UPDATE facility_checkins
        None,                                   # _project_shipment_status UPDATE
        None,                                   # audit INSERT
    )

    result = await gate_yard_service.record_dock_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, dock_id="DOCK-JAI-D1"
    )

    assert result.code == "DOCK_IN_RECORDED"
    assert result.actual_dock_id == "DOCK-JAI-D1"


@pytest.mark.asyncio
async def test_record_dock_in_flags_a_deviation_from_the_confirmed_dock():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="CALLED_TO_DOCK")
    session = _session_with(
        _shipment_row(),
        {"dock_id": "DOCK-JAI-D9", "facility_id": FACILITY, "dock_code": "D9"},
        checkin,
        None,
        _appointment_row(dock_id="DOCK-JAI-D1"),  # confirmed dock differs from arrival dock
        None, None, None,
    )
    result = await gate_yard_service.record_dock_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, dock_id="DOCK-JAI-D9"
    )
    assert result.code == "DOCK_MISMATCH"
    assert result.expected_dock_id == "DOCK-JAI-D1"
    assert result.actual_dock_id == "DOCK-JAI-D9"


@pytest.mark.asyncio
async def test_record_dock_in_refuses_an_occupied_dock_and_returns_the_truck_to_waiting():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="CALLED_TO_DOCK")
    session = _session_with(
        _shipment_row(),
        {"dock_id": "DOCK-JAI-D1", "facility_id": FACILITY, "dock_code": "D1"},
        checkin,
        {"shipment_id": "SHP-OTHER"},  # _live_dock_occupant -- another shipment is there
        None,         # UPDATE facility_checkins -> WAITING_DOCK_UNAVAILABLE
        None,         # audit INSERT
    )
    result = await gate_yard_service.record_dock_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, dock_id="DOCK-JAI-D1"
    )
    assert result.code == "DOCK_OCCUPIED"
    assert result.queue_state == "WAITING_DOCK_UNAVAILABLE"
    assert result.occupying_shipment_id == "SHP-OTHER"
    assert result.actual_dock_id is None


@pytest.mark.asyncio
async def test_record_dock_in_refuses_a_dock_at_a_different_facility():
    session = _session_with(
        _shipment_row(),
        {"dock_id": "DOCK-GGN-D1", "facility_id": OTHER_FACILITY, "dock_code": "D1"},
    )
    with pytest.raises(AppError) as exc:
        await gate_yard_service.record_dock_in(
            session, _gate_ctx(facility_id=FACILITY), shipment_id=SHIPMENT, dock_id="DOCK-GGN-D1"
        )
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_record_dock_in_refuses_a_truck_not_yet_called_to_dock():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="WAITING_EARLY")
    session = _session_with(
        _shipment_row(),
        {"dock_id": "DOCK-JAI-D1", "facility_id": FACILITY, "dock_code": "D1"},
        checkin,
    )
    result = await gate_yard_service.record_dock_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, dock_id="DOCK-JAI-D1"
    )
    assert result.code == "INVALID_TRANSITION"


# ---------------------------------------------------------------------------------------------
# record_unload_start_end -- FR-GATE-007.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_unload_start_records_the_start_timestamp():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="IN_DOCK")
    session = _session_with(_shipment_row(), checkin, None, None)  # shipment, checkin, UPDATE, audit
    result = await gate_yard_service.record_unload_start_end(
        session, _gate_ctx(), shipment_id=SHIPMENT, phase="start"
    )
    assert result.code == "RECORDED"
    assert result.phase == "START"


@pytest.mark.asyncio
async def test_record_unload_end_computes_a_positive_overrun():
    unload_start = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    unload_end = unload_start + timedelta(minutes=60)  # expected 45 -> overrun 15
    checkin = _checkin_row(
        gate_in_ts=unload_start - timedelta(minutes=10), queue_state="IN_DOCK",
        unload_start_ts=unload_start, unload_end_ts=None,
    )
    session = _session_with(_shipment_row(expected_unload_min=45), checkin, None, None)

    result = await gate_yard_service.record_unload_start_end(
        session, _gate_ctx(), shipment_id=SHIPMENT, phase="END", ts=unload_end
    )

    assert result.code == "RECORDED"
    assert result.actual_unload_min == pytest.approx(60.0)
    assert result.overrun_min == pytest.approx(15.0)
    assert result.queue_state == "COMPLETED"


@pytest.mark.asyncio
async def test_record_unload_start_refuses_a_truck_not_in_a_dock():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="WAITING_EARLY")
    session = _session_with(_shipment_row(), checkin)
    result = await gate_yard_service.record_unload_start_end(
        session, _gate_ctx(), shipment_id=SHIPMENT, phase="START"
    )
    assert result.code == "INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_record_unload_end_refuses_without_a_prior_start():
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="IN_DOCK", unload_start_ts=None)
    session = _session_with(_shipment_row(), checkin)
    result = await gate_yard_service.record_unload_start_end(
        session, _gate_ctx(), shipment_id=SHIPMENT, phase="END"
    )
    assert result.code == "INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_record_unload_start_end_rejects_an_unknown_phase_before_any_query_runs():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await gate_yard_service.record_unload_start_end(
            session, _gate_ctx(), shipment_id=SHIPMENT, phase="MIDDLE"
        )
    assert exc.value.code == "INVALID_PHASE"
    session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------------------------
# record_gate_out -- FR-GATE-008.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_gate_out_computes_dwell_time():
    gate_in = datetime(2026, 8, 24, 7, 35, tzinfo=timezone.utc)
    gate_out = gate_in + timedelta(minutes=75)
    checkin = _checkin_row(gate_in_ts=gate_in, queue_state="COMPLETED", gate_out_ts=None)
    session = _session_with(_shipment_row(), checkin, None, None, None)  # shipment, checkin, UPDATE, project, audit

    result = await gate_yard_service.record_gate_out(
        session, _gate_ctx(), shipment_id=SHIPMENT, ts=gate_out
    )

    assert result.code == "COMPLETED"
    assert result.dwell_min == pytest.approx(75.0)


@pytest.mark.asyncio
async def test_record_gate_out_restates_the_fact_for_an_already_gated_out_truck():
    gate_in = datetime(2026, 8, 24, 7, 35, tzinfo=timezone.utc)
    gate_out = gate_in + timedelta(minutes=75)
    checkin = _checkin_row(gate_in_ts=gate_in, gate_out_ts=gate_out, queue_state="COMPLETED")
    session = _session_with(_shipment_row(), checkin)

    result = await gate_yard_service.record_gate_out(session, _gate_ctx(), shipment_id=SHIPMENT, ts=None)

    assert result.code == "ALREADY_GATED_OUT"
    assert result.dwell_min == pytest.approx(75.0)
    assert session.execute.await_count == 2  # nothing rewritten


@pytest.mark.asyncio
async def test_record_gate_out_refuses_a_truck_that_was_never_gated_in():
    session = _session_with(_shipment_row(), None)
    with pytest.raises(AppError) as exc:
        await gate_yard_service.record_gate_out(session, _gate_ctx(), shipment_id=SHIPMENT, ts=None)
    assert exc.value.code == "NOT_CHECKED_IN"
