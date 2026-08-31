"""E3.6 (issue #30) tests for the SS7.5.2 gate/yard writes.

Same `_session_with(...)` sequential-mock shape as `test_planner_service.py` -- see that file's
module docstring for the reasoning. `classify_arrival` gets direct coverage of its own since it is
the one calibrated business rule in this module (`ON_TIME_WINDOW_MIN`, derived from five live
Layer A rows per `gate_yard_service.py`'s own comment).
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.routers import gate as gate_router
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


@pytest.mark.asyncio
async def test_a_gate_officer_can_record_gate_in_for_its_own_facility():
    """Issue #79: the kiosk's own role, not a borrowed WAREHOUSE_PLANNER credential.

    Exercised through `record_gate_in` rather than the scope predicate alone because the point of
    the issue is end-to-end reachability: before this, `RoleName` had no GATE_OFFICER at all, so
    such a token could not be minted, and had one existed it would have failed
    `assert_facility_write_scope` at `_shipment_in_scope`.
    """
    slot_start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    session = _session_with(
        _shipment_row(),
        _appointment_row(slot_start=slot_start),
        None,   # no existing checkin
        None,   # early_limit rule lookup
        None,   # INSERT facility_checkins
        None,   # _project_shipment_status UPDATE
        None,   # audit INSERT
    )

    result = await gate_yard_service.record_gate_in(
        session,
        _gate_ctx(role=RoleName.GATE_OFFICER),
        shipment_id=SHIPMENT,
        ts=slot_start,
        idempotency_key="gk-officer-1",
    )

    assert result.code == "GATE_IN_RECORDED"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_a_gate_officer_cannot_record_gate_in_for_another_facility():
    session = _session_with(_shipment_row(facility_id=OTHER_FACILITY))
    with pytest.raises(AppError) as exc:
        await gate_yard_service.record_gate_in(
            session,
            _gate_ctx(facility_id=FACILITY, role=RoleName.GATE_OFFICER),
            shipment_id=SHIPMENT,
            ts=None,
            idempotency_key="gk-officer-2",
        )
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_an_ops_console_role_still_cannot_reach_the_gate_writes():
    """The gate write tier is not "any facility-scoped role".

    OPERATIONS_EXECUTIVE clears `is_operator` and so *would* pass the shared
    `assert_facility_write_scope`; it is refused at the router's `GATE_KIOSK_ROLES` gate, not
    here. This asserts the router gate is the real boundary by showing the service tier alone is
    intentionally permissive for ops roles -- so that nobody later "tightens" the service and
    breaks the 2026-08-24 planner mapping without noticing.
    """
    session = _session_with(_shipment_row())
    from app.core.deps import GATE_KIOSK_ROLES

    assert RoleName.OPERATIONS_EXECUTIVE not in GATE_KIOSK_ROLES
    # Service tier alone lets it through; only the router keeps it out.
    row = await gate_yard_service._shipment_in_scope(
        session, _gate_ctx(role=RoleName.OPERATIONS_EXECUTIVE), SHIPMENT
    )
    assert row["facility_id"] == FACILITY


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


# =============================================================================================
# Officer attribution -- U111 / FR-GATE-001, issue #68.
#
# The gap this closes: the officer name was captured and displayed by the kiosk and then sent
# nowhere, so every event any officer wrote on a shared device was indistinguishable in the audit
# trail. These tests assert three separate things, and the third is the one that matters most:
#   1. the label now reaches `audit_logs`, on every write, in one fixed shape;
#   2. an absent label never costs an event, and is never quietly replaced by a real name;
#   3. **the label decides nothing** -- it is attribution, never authorisation.
# =============================================================================================

OFFICER_RAW = "  Ramesh   K. "
OFFICER_NORMALISED = "Ramesh K."


def _audit_params(session) -> dict:
    """Bound parameters of the single `audit_logs` INSERT this session recorded."""
    inserts = [
        call.args[1]
        for call in session.execute.await_args_list
        if "public.audit_logs" in str(call.args[0])
    ]
    assert len(inserts) == 1, f"expected exactly one audit insert, got {len(inserts)}"
    return inserts[0]


def _attribution(session) -> dict:
    return json.loads(_audit_params(session)["new_value_json"])[
        gate_yard_service.OFFICER_ATTRIBUTION_KEY
    ]


# Each builder returns (session, unawaited coroutine) for one audit-writing branch. There are
# exactly seven `_audit` call sites in the module and exactly seven builders here, one per site --
# an eighth event added without a case would leave that site unexercised by this suite.

def _b_gate_in(officer):
    slot_start = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    session = _session_with(
        _shipment_row(), _appointment_row(slot_start=slot_start),
        None, None, None, None, None,
    )
    return session, gate_yard_service.record_gate_in(
        session, _gate_ctx(), shipment_id=SHIPMENT,
        ts=slot_start - timedelta(minutes=25), idempotency_key="ofc-gi", officer_name=officer,
    )


def _b_queue_state(officer):
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="WAITING_EARLY")
    session = _session_with(_shipment_row(), checkin, None, None, None)
    return session, gate_yard_service.update_queue_state(
        session, _gate_ctx(), shipment_id=SHIPMENT, queue_state="CALLED_TO_DOCK",
        officer_name=officer,
    )


def _b_dock_in(officer):
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="CALLED_TO_DOCK")
    session = _session_with(
        _shipment_row(),
        {"dock_id": "DOCK-JAI-D1", "facility_id": FACILITY, "dock_code": "D1"},
        checkin, None, _appointment_row(dock_id="DOCK-JAI-D1"), None, None, None,
    )
    return session, gate_yard_service.record_dock_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, dock_id="DOCK-JAI-D1", officer_name=officer,
    )


def _b_dock_in_refused(officer):
    """DOCK_OCCUPIED still writes an audit row, so it still needs the stamp (edge-cases.md #4)."""
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="CALLED_TO_DOCK")
    session = _session_with(
        _shipment_row(),
        {"dock_id": "DOCK-JAI-D1", "facility_id": FACILITY, "dock_code": "D1"},
        checkin, {"shipment_id": "SHP-OTHER"}, None, None,
    )
    return session, gate_yard_service.record_dock_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, dock_id="DOCK-JAI-D1", officer_name=officer,
    )


def _b_unload_start(officer):
    checkin = _checkin_row(gate_in_ts=datetime.now(timezone.utc), queue_state="IN_DOCK")
    session = _session_with(_shipment_row(), checkin, None, None)
    return session, gate_yard_service.record_unload_start_end(
        session, _gate_ctx(), shipment_id=SHIPMENT, phase="START", officer_name=officer,
    )


def _b_unload_end(officer):
    unload_start = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    checkin = _checkin_row(
        gate_in_ts=unload_start, queue_state="IN_DOCK", dock_in_ts=unload_start,
        unload_start_ts=unload_start,
    )
    session = _session_with(_shipment_row(), checkin, None, None)
    return session, gate_yard_service.record_unload_start_end(
        session, _gate_ctx(), shipment_id=SHIPMENT, phase="END",
        ts=unload_start + timedelta(minutes=60), officer_name=officer,
    )


def _b_gate_out(officer):
    gate_in = datetime(2026, 8, 24, 7, 35, tzinfo=timezone.utc)
    checkin = _checkin_row(gate_in_ts=gate_in, queue_state="IN_DOCK")
    session = _session_with(_shipment_row(), checkin, None, None, None)
    return session, gate_yard_service.record_gate_out(
        session, _gate_ctx(), shipment_id=SHIPMENT, ts=gate_in + timedelta(minutes=75),
        officer_name=officer,
    )


# The paired `event` verb is not decoration: it is what proves each builder actually lands on a
# *different* `_audit` call site. Without it a drifted mock sequence could send two builders down
# the same branch and the suite would still be green while a site went unexercised.
ALL_AUDITED_WRITES = [
    pytest.param(_b_gate_in, "GATE_IN", id="gate_in"),
    pytest.param(_b_queue_state, "QUEUE_STATE", id="queue_state"),
    pytest.param(_b_dock_in, "DOCK_IN", id="dock_in"),
    pytest.param(_b_dock_in_refused, "DOCK_IN_REFUSED", id="dock_in_occupied"),
    pytest.param(_b_unload_start, "UNLOAD_START", id="unload_start"),
    pytest.param(_b_unload_end, "UNLOAD_END", id="unload_end"),
    pytest.param(_b_gate_out, "GATE_OUT", id="gate_out"),
]


def test_the_builder_table_covers_every_audit_call_site_in_the_module():
    """Seven builders, seven `_audit(...)` call sites. An eighth event must add an eighth case."""
    import ast

    source = inspect.getsource(gate_yard_service)
    sites = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_audit"
    ]
    assert len(sites) == len(ALL_AUDITED_WRITES)


@pytest.mark.parametrize(("builder", "event"), ALL_AUDITED_WRITES)
@pytest.mark.asyncio
async def test_every_gate_event_stamps_the_officer_label_on_its_audit_row(builder, event):
    """FR-GATE-001: "stamped on every event that shift" -- every event, not just gate-in."""
    session, coro = builder(OFFICER_RAW)
    result = await coro

    recorded = json.loads(_audit_params(session)["new_value_json"])
    assert recorded["event"] == event  # this builder reached the branch it claims to
    assert recorded[gate_yard_service.OFFICER_ATTRIBUTION_KEY] == {
        "officer_name": OFFICER_NORMALISED,
        "verified": False,
        "source": "KIOSK_SHIFT_SESSION",
    }
    # Echoed back so the kiosk can see what was actually stored, not what it hoped was.
    assert result.officer_name == OFFICER_NORMALISED


@pytest.mark.parametrize(("builder", "event"), ALL_AUDITED_WRITES)
@pytest.mark.asyncio
async def test_an_event_with_no_officer_still_records_and_is_never_reattributed(builder, event):
    """The mid-shift-change case: a kiosk with no active shift must not lose an arrival.

    And the label must not be *invented*. `_gate_ctx()` deliberately carries a plausible
    `full_name` ("Test Gate Officer") -- the shared device account's own name -- which is exactly
    the value a well-meaning fallback would reach for. Asserting it appears nowhere in the row is
    what makes "no fallback" a property rather than a comment.
    """
    session, coro = builder(None)
    result = await coro

    params = _audit_params(session)
    assert json.loads(params["new_value_json"])["event"] == event
    assert _attribution(session)["officer_name"] is None
    assert result.officer_name is None
    assert "Test Gate Officer" not in params["new_value_json"]
    # The *verified* principal is still recorded, in the column that means exactly that.
    assert params["user_id"] == "USR-GATE-1"


# The last case is U+00A0 (non-breaking space), written as an escape because it is invisible
# in source. Python does not consider it printable, so the normaliser has to handle it.
# NBSP is written as chr(0xA0) rather than a literal, because a literal one is
# invisible in source. Python does not consider it printable, so it is exactly the
# class of character the normaliser has to map to a separator rather than drop.
@pytest.mark.parametrize("blank", ["", "   ", "\n\t ", chr(0xA0)])
@pytest.mark.asyncio
async def test_a_blank_label_is_recorded_as_no_officer_rather_than_as_an_empty_name(blank):
    session, coro = _b_gate_in(blank)
    result = await coro
    assert _attribution(session)["officer_name"] is None
    assert result.officer_name is None


# ---------------------------------------------------------------------------------------------
# The trust boundary. The label is attribution; the token is authorisation.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "officer_name",
    [
        None,
        "Ramesh K.",
        # Shaped to look like an identity a careless implementation might honour.
        "ADMIN",
        "USR-GATE-1",
        "FACILITY_MANAGER",
        '{"role": "ADMIN"}',
    ],
)
@pytest.mark.asyncio
async def test_officer_name_cannot_influence_the_scope_decision(officer_name):
    """Whatever the officer types, the facility check is the one made against the verified token.

    This is the test the module's `OFFICER_ATTRIBUTION_KEY` comment points at. If someone ever
    threads `officer_name` into `_shipment_in_scope`, `assert_gate_write_scope` or a row filter,
    this stops being green.
    """
    session = _session_with(_shipment_row(facility_id=OTHER_FACILITY))
    with pytest.raises(AppError) as exc:
        await gate_yard_service.record_gate_in(
            session, _gate_ctx(facility_id=FACILITY), shipment_id=SHIPMENT, ts=None,
            idempotency_key="ofc-scope", officer_name=officer_name,
        )
    assert exc.value.code == "FORBIDDEN"
    # A refused write leaves no audit row -- so a rejected label cannot be used to write anything.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_the_audit_row_keeps_the_verified_principal_and_the_unverified_label_apart():
    session, coro = _b_gate_in("ADMIN")
    await coro
    params = _audit_params(session)
    assert params["user_id"] == "USR-GATE-1"  # verified, FK to public.users
    assert _attribution(session) == {
        "officer_name": "ADMIN",
        "verified": False,  # and it says so, on the row, for whoever reads it later
        "source": "KIOSK_SHIFT_SESSION",
    }


def test_audit_requires_the_officer_argument_so_a_new_event_cannot_forget_it():
    """`_audit` has no default for `officer_name`; omitting it is a TypeError, not a silent null.

    Passing `None` is legal and meaningful. *Not passing it* is the mistake this guards.
    """
    param = inspect.signature(gate_yard_service._audit).parameters["officer_name"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


# ---------------------------------------------------------------------------------------------
# normalise_officer_name -- the single authority, and the reason there is no router-side rule.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("Ramesh K.", "Ramesh K."),
        ("  Ramesh   K. ", "Ramesh K."),
        # OWASP Logging Cheat Sheet: CR/LF sanitised. Mapped to a space, not deleted, so a
        # smuggled newline cannot silently fuse two words into one plausible-looking name.
        ("Ramesh\r\nK.", "Ramesh K."),
        ("Ramesh\tK.", "Ramesh K."),
        ("Ramesh" + chr(0xA0) + "K.", "Ramesh K."),  # U+00A0 non-breaking space
        ("Ramesh\x00K.", "Ramesh K."),
        # Non-Latin names are not "unprintable" and must survive intact.
        ("रमेश क.", "रमेश क."),
    ],
)
def test_normalise_officer_name(raw, expected):
    assert gate_yard_service.normalise_officer_name(raw) == expected


def test_an_overlong_label_is_truncated_rather_than_refused():
    """FR-GATE-001 may not defeat FR-GATE-004..008.

    The same label is replayed on every write of a whole shift, so a length rule that *rejects*
    would not lose one arrival -- it would lose the shift's. Hence: no `max_length` on the router
    body field, and truncation here instead. The truncated value is echoed back on the result, so
    the difference is visible rather than silent.
    """
    long_name = "R" * (gate_yard_service.OFFICER_NAME_MAX_LEN * 3)
    normalised = gate_yard_service.normalise_officer_name(long_name)
    assert normalised is not None
    assert len(normalised) == gate_yard_service.OFFICER_NAME_MAX_LEN


@pytest.mark.parametrize(
    ("model", "required"),
    [
        (gate_router.GateInBody, {}),
        (gate_router.QueueStateBody, {"queue_state": "CALLED_TO_DOCK"}),
        (gate_router.DockInBody, {"dock_id": "DOCK-JAI-D1"}),
        (gate_router.UnloadPhaseBody, {"phase": "START"}),
        (gate_router.GateOutBody, {}),
    ],
)
def test_all_five_write_bodies_carry_the_label_and_none_of_them_rejects_one(model, required):
    """Issue #68's actual subject: before this, none of the five body models had the field at all."""
    assert "officer_name" in model.model_fields
    assert model.model_validate(required).officer_name is None  # optional, per the absent case

    long_name = "R" * (gate_yard_service.OFFICER_NAME_MAX_LEN * 3)
    accepted = model.model_validate({**required, "officer_name": long_name})
    assert accepted.officer_name == long_name  # the router bounds nothing; the service does


# ---------------------------------------------------------------------------------------------
# Idempotency. The label is not part of the command's identity.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_officer_label_is_not_part_of_the_idempotency_request_hash():
    """A shift-boundary retry must not become IDEMPOTENCY_PAYLOAD_MISMATCH.

    Officer A taps gate-in, the link drops, officer B retries the queued key. The truck, the time
    and the facility are identical -- it is the same command. If the label were hashed, that retry
    would be refused outright and a real arrival would be lost.
    """
    hashes = set()
    for name in ("Ramesh K.", "Priya S.", None):
        _session, coro = _b_gate_in(name)
        await coro
        hashes.add(gate_yard_service.lookup_idempotency.await_args.kwargs["request_hash"])
    assert len(hashes) == 1


@pytest.mark.asyncio
async def test_an_idempotent_replay_returns_the_first_officers_label_not_the_retriers(monkeypatch):
    """The event was written by whoever wrote it. A replay restates that; it does not re-sign it."""
    stored = {
        "as_of": "2026-08-31T09:00:00+00:00",
        "code": "GATE_IN_RECORDED",
        "shipment_id": SHIPMENT,
        "facility_id": FACILITY,
        "officer_name": "Ramesh K.",
    }
    monkeypatch.setattr(
        gate_yard_service,
        "lookup_idempotency",
        AsyncMock(return_value={"response": stored, "status_code": 200, "replayed": True}),
    )
    session = _session_with()

    result = await gate_yard_service.record_gate_in(
        session, _gate_ctx(), shipment_id=SHIPMENT, ts=None, idempotency_key="ofc-replay",
        officer_name="Priya S.",
    )

    assert result.idempotent_replay is True
    assert result.officer_name == "Ramesh K."
    session.execute.assert_not_awaited()
