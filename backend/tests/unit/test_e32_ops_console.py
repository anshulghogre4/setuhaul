"""E3.2 (issue #26, M3) tests for the SS7.5.5 ops console.

Covers the six functions this epic added or rebuilt in `escalation_service.py`:
`get_exception_queue`'s owner filter/stepper/SLA enrichment, `acknowledge_escalation`'s race
resolution, `reassign_escalation`, `cancel_escalation`, `take_over_thread`/`hand_back_thread`, and
the issue #48 facility-scope fix inside the rebuilt `resolve_escalation`. Same sequential
`session.execute` mocking shape `test_planner_service.py`/`test_gate_yard_service.py` already use.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services import escalation_service

FACILITY = "FAC-JAI-01"
OTHER_FACILITY = "FAC-GGN-01"


def _ops_ctx(*, facility_id: str = FACILITY, role: RoleName = RoleName.OPERATIONS_EXECUTIVE, user_id: str = "USR-OPS-1") -> ExecutionContext:
    return ExecutionContext(
        request_id="req-ops-1",
        auth_subject="sub-ops-1",
        user_id=user_id,
        email="ops@setuhaul.com",
        full_name="Ops Coordinator",
        role_id="ROL002",
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


@pytest.fixture(autouse=True)
def _no_idempotency_replay(monkeypatch):
    monkeypatch.setattr(escalation_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(escalation_service, "store_idempotency", AsyncMock())


# ---------------------------------------------------------------------------------------------
# get_exception_queue -- owner filter, stepper position, SLA remaining, affected_shipments.
# ---------------------------------------------------------------------------------------------


def _escalation_row(**overrides) -> dict:
    base = {
        "escalation_id": "ESC-1", "shipment_id": "SHP1", "facility_id": FACILITY, "driver_id": "DRV1",
        "escalation_type": "NO_FEASIBLE_SLOT", "escalation_status": "OPEN", "severity_code": "HIGH",
        "policy_version": None, "recommendation_id": None,
        "payload_json": "{}", "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(), "owner_user_id": None, "owner_name": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_get_exception_queue_rejects_an_unsupported_owner_filter():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await escalation_service.get_exception_queue(session, _ops_ctx(), owner="theirs")
    assert exc.value.code == "INVALID_OWNER_FILTER"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_exception_queue_computes_stepper_position_from_status():
    rows = [_escalation_row(escalation_status="ACKNOWLEDGED"), _escalation_row(escalation_id="ESC-2", escalation_status="OPEN")]
    session = _session_with(rows)
    result = await escalation_service.get_exception_queue(session, _ops_ctx())
    by_id = {i["escalation_id"]: i for i in result["items"]}
    assert by_id["ESC-1"]["stepper_position"] == 1
    assert by_id["ESC-2"]["stepper_position"] == 0


@pytest.mark.asyncio
async def test_get_exception_queue_pins_unowned_above_owned_regardless_of_sla():
    owned = _escalation_row(
        escalation_id="ESC-OWNED", owner_user_id="USR-X",
        severity_code="LOW", created_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    unowned = _escalation_row(
        escalation_id="ESC-UNOWNED", owner_user_id=None,
        severity_code="HIGH", created_at=(datetime.now(timezone.utc) - timedelta(minutes=110)).isoformat(),
    )
    # Owned row has far more SLA budget remaining than the unowned row, so a pure SLA sort would
    # rank it first -- unowned-first must still win.
    session = _session_with([owned, unowned])
    result = await escalation_service.get_exception_queue(session, _ops_ctx())
    assert [i["escalation_id"] for i in result["items"]] == ["ESC-UNOWNED", "ESC-OWNED"]


@pytest.mark.asyncio
async def test_get_exception_queue_surfaces_affected_shipments_only_for_capacity_cascade():
    cascade = _escalation_row(
        escalation_type="CAPACITY_EVENT_CASCADE",
        payload_json='{"affected_appointments": [{"appointment_id": "APT1"}]}',
    )
    other = _escalation_row(escalation_id="ESC-2", escalation_type="NO_FEASIBLE_SLOT", payload_json='{"reason": "x"}')
    session = _session_with([cascade, other])
    result = await escalation_service.get_exception_queue(session, _ops_ctx())
    by_id = {i["escalation_id"]: i for i in result["items"]}
    assert by_id["ESC-1"]["affected_shipments"] == [{"appointment_id": "APT1"}]
    assert by_id["ESC-2"]["affected_shipments"] is None


@pytest.mark.asyncio
async def test_get_exception_queue_mine_filter_binds_the_callers_own_user_id():
    session = _session_with([])
    await escalation_service.get_exception_queue(session, _ops_ctx(user_id="USR-MINE"), owner="mine")
    params = session.execute.call_args.args[1]
    assert params["caller_id"] == "USR-MINE"


# ---------------------------------------------------------------------------------------------
# acknowledge_escalation -- the confirm_request-style race.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledge_escalation_claims_an_open_escalation():
    session = _session_with(
        {"facility_id": FACILITY},  # _escalation_facility_id
        {"escalation_id": "ESC-1", "shipment_id": "SHP1", "escalation_status": "ACKNOWLEDGED", "owner_user_id": "USR-OPS-1"},
    )
    result = await escalation_service.acknowledge_escalation(session, _ops_ctx(), "ESC-1", "idem-1")
    assert result["code"] == "ACKNOWLEDGED"
    assert result["owner_user_id"] == "USR-OPS-1"


@pytest.mark.asyncio
async def test_acknowledge_escalation_reports_already_actioned_when_the_race_is_lost():
    session = _session_with(
        {"facility_id": FACILITY},  # _escalation_facility_id
        None,  # UPDATE ... WHERE escalation_status='OPEN' -- someone else already won
        {"escalation_id": "ESC-1", "shipment_id": "SHP1", "escalation_status": "ACKNOWLEDGED", "owner_user_id": "USR-OTHER"},
    )
    result = await escalation_service.acknowledge_escalation(session, _ops_ctx(), "ESC-1", "idem-2")
    assert result["code"] == "ALREADY_ACTIONED"
    assert result["owner_user_id"] == "USR-OTHER"


@pytest.mark.asyncio
async def test_acknowledge_escalation_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await escalation_service.acknowledge_escalation(session, _ops_ctx(), "ESC-1", "")
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_acknowledge_escalation_refuses_a_facility_outside_the_callers_scope():
    session = _session_with({"facility_id": OTHER_FACILITY})
    with pytest.raises(AppError) as exc:
        await escalation_service.acknowledge_escalation(session, _ops_ctx(facility_id=FACILITY), "ESC-1", "idem-3")
    assert exc.value.code == "FORBIDDEN"


# ---------------------------------------------------------------------------------------------
# reassign_escalation
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reassign_escalation_moves_ownership_to_a_known_user():
    session = _session_with(
        {"escalation_id": "ESC-1", "shipment_id": "SHP1", "facility_id": FACILITY, "owner_user_id": "USR-OLD"},
        {"user_id": "USR-NEW"},  # owner existence check
        {"escalation_id": "ESC-1", "shipment_id": "SHP1", "escalation_status": "ACKNOWLEDGED", "owner_user_id": "USR-NEW"},
    )
    result = await escalation_service.reassign_escalation(session, _ops_ctx(), "ESC-1", "USR-NEW")
    assert result["code"] == "REASSIGNED"
    assert result["owner_user_id"] == "USR-NEW"


@pytest.mark.asyncio
async def test_reassign_escalation_refuses_nothing_to_reassign_when_unowned():
    session = _session_with({"escalation_id": "ESC-1", "shipment_id": "SHP1", "facility_id": FACILITY, "owner_user_id": None})
    result = await escalation_service.reassign_escalation(session, _ops_ctx(), "ESC-1", "USR-NEW")
    assert result["code"] == "NOT_ACKNOWLEDGED"


@pytest.mark.asyncio
async def test_reassign_escalation_rejects_an_unknown_new_owner():
    session = _session_with(
        {"escalation_id": "ESC-1", "shipment_id": "SHP1", "facility_id": FACILITY, "owner_user_id": "USR-OLD"},
        None,  # owner existence check fails
    )
    with pytest.raises(AppError) as exc:
        await escalation_service.reassign_escalation(session, _ops_ctx(), "ESC-1", "USR-GHOST")
    assert exc.value.code == "INVALID_OWNER"


# ---------------------------------------------------------------------------------------------
# cancel_escalation
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_escalation_cancels_with_a_controlled_reason():
    session = _session_with(
        {"facility_id": FACILITY},  # _escalation_facility_id
        {"escalation_id": "ESC-1", "shipment_id": "SHP1", "escalation_type": "NO_FEASIBLE_SLOT",
         "escalation_status": "CANCELLED", "resolution_note": "Cancelled: DUPLICATE"},
    )
    result = await escalation_service.cancel_escalation(session, _ops_ctx(), "ESC-1", "DUPLICATE", idempotency_key="idem-c1")
    assert result["code"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_escalation_rejects_an_uncontrolled_reason_code():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await escalation_service.cancel_escalation(session, _ops_ctx(), "ESC-1", "BECAUSE", idempotency_key="idem-c2")
    assert exc.value.code == "INVALID_REASON_CODE"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_escalation_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await escalation_service.cancel_escalation(session, _ops_ctx(), "ESC-1", "DUPLICATE", idempotency_key=None)
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"


# ---------------------------------------------------------------------------------------------
# resolve_escalation -- the issue #48 facility-scope fix, directly.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_escalation_refuses_a_cross_facility_operator_issue_48():
    """Issue #48: the pre-E3.2 version checked only the caller's role, never the escalation's own
    facility -- any facility-scoped operator could resolve another facility's case."""
    session = _session_with({"facility_id": OTHER_FACILITY})
    with pytest.raises(AppError) as exc:
        await escalation_service.resolve_escalation(session, _ops_ctx(facility_id=FACILITY), "ESC-1")
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_resolve_escalation_rejects_an_uncontrolled_reason_code():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await escalation_service.resolve_escalation(session, _ops_ctx(), "ESC-1", reason_code="BECAUSE")
    assert exc.value.code == "INVALID_REASON_CODE"
    session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------------------------
# take_over_thread / hand_back_thread
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_over_thread_escalates_and_posts_a_system_notice():
    session = _session_with(
        {"facility_id": FACILITY},  # _escalation_facility_id
        {"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "OPEN"},  # chat_threads lookup
        None,  # UPDATE chat_threads
        None,  # INSERT chat_messages
    )
    result = await escalation_service.take_over_thread(session, _ops_ctx(), "THR-1", "ESC-1", "idem-t1")
    assert result["code"] == "TAKEN_OVER"
    assert result["thread_status"] == "ESCALATED"


@pytest.mark.asyncio
async def test_take_over_thread_reports_already_taken_over():
    session = _session_with(
        {"facility_id": FACILITY},
        {"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "ESCALATED"},
    )
    result = await escalation_service.take_over_thread(session, _ops_ctx(), "THR-1", "ESC-1", "idem-t2")
    assert result["code"] == "ALREADY_TAKEN_OVER"


@pytest.mark.asyncio
async def test_hand_back_thread_reverses_an_acknowledged_takeover():
    session = _session_with(
        {"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "ESCALATED"},  # chat_threads
        {"escalation_id": "ESC-1", "facility_id": FACILITY, "owner_user_id": "USR-OPS-1"},  # linked escalation
        None,  # UPDATE chat_threads
        None,  # INSERT chat_messages
    )
    result = await escalation_service.hand_back_thread(session, _ops_ctx(), "THR-1")
    assert result["code"] == "HANDED_BACK"
    assert result["thread_status"] == "OPEN"


@pytest.mark.asyncio
async def test_hand_back_thread_refuses_a_thread_that_was_never_escalated():
    session = _session_with({"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "OPEN"})
    result = await escalation_service.hand_back_thread(session, _ops_ctx(), "THR-1")
    assert result["code"] == "NOT_IN_PROGRESS"


@pytest.mark.asyncio
async def test_hand_back_thread_refuses_when_the_linked_escalation_is_unacknowledged():
    session = _session_with(
        {"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "ESCALATED"},
        None,  # no ACKNOWLEDGED/IN_PROGRESS escalation found for this shipment
    )
    result = await escalation_service.hand_back_thread(session, _ops_ctx(), "THR-1")
    assert result["code"] == "NOT_IN_PROGRESS"
