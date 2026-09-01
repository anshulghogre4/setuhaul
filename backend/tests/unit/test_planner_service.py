"""Tests for the SS7.5.1 planner tools: the queue read (issue #60) and the dock-blocking writes.

The `get_planner_queue` tests below patch the two repository functions rather than mocking SQL
results in call order: that read is two flat queries whose *assembly* -- receipt terms, the
displacement overlap, the TTL derivation, the composite ordering and the snapshot digest -- is the
behaviour worth pinning, and all of it is pure Python over the rows. Time is a `FrozenClock`
throughout (SS9.1): the TTL column is the point of this read, so a test that read the wall clock
would be asserting against luck.

E3.6 (issue #30) tests for the SS7.5.1 planner dock-blocking writes.

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

from app.core.clock import FrozenClock
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


def _scope_probe_session(*, grants: bool) -> AsyncMock:
    """A session whose only statement is `scope.user_holds_facility_scope`'s probe (issue #106).

    Needed because that probe reads `.first()` off the raw result rather than `.mappings()`, and a
    bare `AsyncMock()` answers *every* attribute with a truthy mock -- so a session that mocked
    nothing would silently report "yes, this user is granted that facility" and turn the M15
    refusal tests below green against a resolver that had stopped refusing. `grants=False` is the
    honest "no `user_scopes` row" answer; `grants=True` is the multi-facility coordinator #72 can
    now create.
    """
    result = MagicMock()
    result.first.return_value = (1,) if grants else None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
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
async def test_block_dock_blocks_and_opens_one_cascade_escalation_for_the_affected_set(
    monkeypatch,
):
    # #94 wired a real notification producer into the cascade (P6); its context lookups
    # would consume this test's scripted mock results. The producer's own behaviour is
    # proof-suite-covered (part 3b); here it is stubbed so the cascade assertions stay
    # about the cascade.
    from app.services import notification_outbox
    async def _noop_enqueue(session, **kwargs):
        return 0
    monkeypatch.setattr(notification_outbox, 'enqueue_option_withdrawn', _noop_enqueue)
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


# ---------------------------------------------------------------------------------------------
# get_planner_queue -- FR-PLN-010, SS7.5.1, SS7.3's seven-field row (issue #60).
# ---------------------------------------------------------------------------------------------

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
CLOCK = FrozenClock(NOW)


def _queue_row(
    *,
    appointment_id: str = "APT1",
    shipment_id: str = "SHP1",
    priority_code: str = "NORMAL",
    booked_at: datetime | None = None,
    dock_id: str = DOCK,
    occupancy: bool = True,
    interval_start: datetime | None = None,
    unload_min: int = 60,
    required_dock_type: str = "STANDARD",
    dock_type: str = "STANDARD",
    original_eta_ts: datetime | None = None,
    effective_eta_ts: datetime | None = None,
    eta_confidence: str = "HIGH",
    queue_state: str | None = None,
    latest_acceptable_ts: str | None = None,
) -> dict:
    start = interval_start or (NOW + timedelta(hours=1))
    end = start + timedelta(minutes=unload_min + 15)
    return {
        "appointment_id": appointment_id,
        "shipment_id": shipment_id,
        "slot_id": f"SLOT-{appointment_id}",
        "appointment_status": "PENDING_CONFIRMATION",
        "booking_source": "DRIVER_CHAT",
        "is_current": 1,
        "booked_at": booked_at or (NOW - timedelta(minutes=5)),
        "order_reference": f"ORD-{shipment_id}",
        "driver_id": "DRV1",
        "carrier_id": "CAR1",
        "priority_code": priority_code,
        "required_dock_type": required_dock_type,
        "expected_unload_min": unload_min,
        "original_eta_ts": original_eta_ts or start,
        "driver_name": "Ravi K.",
        "carrier_name": "Rajasthan Roadways",
        "facility_id": FACILITY,
        "slot_start_ts": start,
        "slot_end_ts": end,
        "dock_id": dock_id,
        "dock_code": "D1",
        "dock_type": dock_type,
        "occupancy_start": start if occupancy else None,
        "occupancy_end": end if occupancy else None,
        "interval_start": start,
        "interval_end": end,
        "effective_eta_ts": effective_eta_ts or start,
        "eta_confidence": eta_confidence,
        "eta_source": "DRIVER_DECLARED",
        "queue_state": queue_state,
        "queue_position": 1 if queue_state else None,
        "gate_in_ts": None,
        "limit_exception_id": "EXC1" if latest_acceptable_ts else None,
        "latest_acceptable_ts": latest_acceptable_ts,
    }


def _occupancy_row(
    *, appointment_id: str, dock_id: str = DOCK, start: datetime, end: datetime
) -> dict:
    return {
        "occupancy_id": 1,
        "dock_id": dock_id,
        "appointment_id": appointment_id,
        "window_start": start,
        "window_end": end,
        "shipment_id": f"SHP-{appointment_id}",
        "order_reference": f"ORD-{appointment_id}",
        "appointment_status": "CONFIRMED",
    }


@pytest.fixture
def queue_repo(monkeypatch):
    """Patch the two repository reads `get_planner_queue` makes, and record their arguments.

    Issue #98 added a third database call to this read -- the lazy expiry of lapsed holds that must
    happen *before* the occupancy query, so the displacement column and `snapshot_hash` cannot be
    built from a hold the constraint no longer counts. It is stubbed here (its own SQL is proved
    against a real cluster in `tests/proof/`, which is the only place it can be) but its arguments
    are recorded, so `test_queue_expires_lapsed_holds_before_reading_displacement` can assert both
    that it ran and that it ran first.

    Issue #88 added a fourth -- `snapshot.load_dock_block_conflicts`, the dock-block leg of the
    displacement column. Stubbed for the same reason and patched on `planner_service` rather than
    on `snapshot`, because the import there is a `from ... import` binding: patching the source
    module would leave this module's own reference pointing at the real coroutine. Its SQL is a
    shared literal with the write path's, so the thing worth proving about it is what it *is*
    (`tests/unit/test_planner_write_tools.py` asserts the fragment is one object, `tests/proof/`
    runs it against a real cluster), not what a stub returns.
    """
    calls: dict[str, list] = {"rows": [], "occupancy": [], "expiry": [], "blocks": []}
    state: dict[str, list | dict] = {"rows": [], "occupancy": [], "blocks": {}}
    order: list[str] = []

    async def _rows(session, **kwargs):
        calls["rows"].append(kwargs)
        order.append("rows")
        return state["rows"]

    async def _occupancy(session, **kwargs):
        calls["occupancy"].append(kwargs)
        order.append("occupancy")
        return state["occupancy"]

    async def _expiry(session, **kwargs):
        calls["expiry"].append(kwargs)
        order.append("expiry")
        return []

    async def _blocks(session, appointment_ids):
        calls["blocks"].append(list(appointment_ids))
        order.append("blocks")
        return state["blocks"]

    monkeypatch.setattr(planner_service.operations_repo, "list_planner_queue_rows", _rows)
    monkeypatch.setattr(planner_service.operations_repo, "list_live_dock_occupancy", _occupancy)
    monkeypatch.setattr(
        planner_service.holds, "expire_lapsed_holds_for_appointments", _expiry
    )
    monkeypatch.setattr(planner_service, "load_dock_block_conflicts", _blocks)
    return {"calls": calls, "state": state, "order": order}


@pytest.mark.asyncio
async def test_queue_row_carries_the_seven_fields_of_section_7_3(queue_repo):
    start = NOW + timedelta(hours=1)
    queue_repo["state"]["rows"] = [
        _queue_row(
            priority_code="CRITICAL",
            interval_start=start,
            original_eta_ts=start - timedelta(minutes=70),
            effective_eta_ts=start,
            eta_confidence="LOW",
            latest_acceptable_ts="2026-08-29T19:00:00+05:30",
        )
    ]

    queue = await planner_service.get_planner_queue(
        AsyncMock(), _planner_ctx(), clock=CLOCK
    )

    row = queue.items[0]
    # 1 -- condensed receipt, in SS7.3's own worked shape.
    assert row.receipt.text == "CRITICAL · 70 min late · exact dock · 0 min wait"
    # 2 -- displacement check.
    assert row.displacement.status == "NONE"
    # 3 -- ETA confidence.
    assert row.eta.confidence == "LOW"
    # 4 -- the driver's own limit.
    assert row.latest_acceptable_ts == "2026-08-29T19:00:00+05:30"
    assert row.latest_acceptable_breached is False
    # 5 -- TTL remaining: booked 5 minutes ago against D9's 15-minute clock.
    assert row.ttl.remaining_seconds == 10 * 60
    assert row.ttl.expired is False
    # 6 -- snapshot_hash. `enforced` is True since #62 landed the consumer half: confirm_request
    # and counter_offer recompute this digest under the row lock and refuse with SNAPSHOT_STALE.
    # Reporting False here would tell a client the argument is advisory when it is load-bearing.
    assert len(row.snapshot_hash) == 64
    assert queue.snapshot.enforced is True
    # ...but the note must not round that up to "every tool refuses": bulk_confirm reports drift
    # without refusing, and apply_schedule_proposal does not exist yet.
    assert "bulk_confirm" in queue.snapshot.note and "does not refuse" in queue.snapshot.note
    # 7 -- the composite-urgency ordering is stated on the payload, not implied.
    assert queue.ordering["rule"] == "composite_urgency"


@pytest.mark.asyncio
async def test_queue_prefers_dock_occupancy_over_the_slot_and_says_which_it_used(queue_repo):
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT-CLAIMED", occupancy=True),
        _queue_row(appointment_id="APT-UNCLAIMED", shipment_id="SHP2", occupancy=False),
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    sources = {item.appointment_id: item.interval_source for item in queue.items}
    assert sources["APT-CLAIMED"] == "dock_occupancy"
    # A pending appointment with no D1 claim is still listed -- dropping it would hide a row the
    # expiry sweeper will nonetheless expire and escalate.
    assert sources["APT-UNCLAIMED"] == "appointment_slot_derived"


@pytest.mark.asyncio
async def test_queue_flags_a_displacement_and_names_the_shipment_it_would_delay(queue_repo):
    start = NOW + timedelta(hours=1)
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT-UNCLAIMED", occupancy=False, interval_start=start)
    ]
    queue_repo["state"]["occupancy"] = [
        _occupancy_row(
            appointment_id="APT-OTHER",
            start=start + timedelta(minutes=30),
            end=start + timedelta(minutes=90),
        )
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    row = queue.items[0]
    assert row.displacement.status == "CONFLICT"
    assert row.displacement.conflicts[0]["shipment_id"] == "SHP-APT-OTHER"


@pytest.mark.asyncio
async def test_queue_does_not_treat_an_abutting_interval_as_a_displacement(queue_repo):
    """Half-open ranges: `[10:00,11:15)` and `[11:15,12:00)` share no instant, so `&&` is false."""
    start = NOW + timedelta(hours=1)
    row = _queue_row(appointment_id="APT-UNCLAIMED", occupancy=False, interval_start=start)
    queue_repo["state"]["rows"] = [row]
    queue_repo["state"]["occupancy"] = [
        _occupancy_row(
            appointment_id="APT-NEXT",
            start=row["interval_end"],
            end=row["interval_end"] + timedelta(hours=1),
        )
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    assert queue.items[0].displacement.status == "NONE"


# =================================================================================================
# Issue #88 -- the dock-block leg of the displacement column
# =================================================================================================
#
# The defect: `DISPLACEMENT_DETECTED` (raised by `confirm_request` via
# `snapshot.displacement_conflicts`) counted overlapping claims **plus** dock blocks, while the
# queue row's own displacement column counted only the first. A planner could be refused for a dock
# taken offline under them that their screen had said nothing about. Section 7.3 calls this column
# "the single most important field", so a preview that under-reports it is not a cosmetic gap.


def _dock_block(dock_event_id: str = "DEVT-1", *, reason: str | None = "Forklift down") -> dict:
    """One `DOCK_BLOCKED` entry in the shape `snapshot._DOCK_BLOCK_CONFLICTS_SQL` emits."""
    return {
        "conflict_type": "DOCK_BLOCKED",
        "dock_event_id": dock_event_id,
        "dock_id": DOCK,
        "event_type": "MANUAL_BLOCK",
        "reason": reason,
    }


@pytest.mark.asyncio
async def test_queue_reports_a_dock_block_as_a_displacement(queue_repo):
    """The row now warns about the dock the write path would refuse it for.

    No overlapping claim at all here: `occupancy` is empty, so pre-#88 this row rendered
    `displacement: NONE` while `confirm_request` refused it `DISPLACEMENT_DETECTED`.
    """
    queue_repo["state"]["rows"] = [_queue_row(appointment_id="APT-BLOCKED", occupancy=False)]
    queue_repo["state"]["blocks"] = {"APT-BLOCKED": [_dock_block()]}

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    row = queue.items[0]
    assert row.displacement.status == "CONFLICT"
    assert [c["conflict_type"] for c in row.displacement.conflicts] == ["DOCK_BLOCKED"]
    assert row.displacement.conflicts[0]["dock_event_id"] == "DEVT-1"


@pytest.mark.asyncio
async def test_a_dock_block_does_not_change_the_snapshot_hash(queue_repo):
    """The hash-exclusion sub-item of #88, and the subtle one.

    Dock blocks are rendered and do refuse, but must stay **out** of the digest. If they were in
    it, blocking one dock would change the `snapshot_hash` of every outstanding row on that dock
    and mass-refuse in-flight confirms with `SNAPSHOT_STALE` -- converting a targeted refusal into
    a facility-wide one, and hiding the specific `DISPLACEMENT_DETECTED` the planner needs to read
    (the write path checks displacement *first* precisely so that code keeps its meaning).

    The identical row is rendered twice, differing only in the block, and the digests must match.
    """
    def _render():
        queue_repo["state"]["rows"] = [_queue_row(appointment_id="APT-BLOCKED", occupancy=False)]
        return planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    queue_repo["state"]["blocks"] = {}
    clean = (await _render()).items[0]
    queue_repo["state"]["blocks"] = {"APT-BLOCKED": [_dock_block()]}
    blocked = (await _render()).items[0]

    assert blocked.displacement.status == "CONFLICT"
    assert clean.displacement.status == "NONE"
    assert blocked.snapshot_hash == clean.snapshot_hash, (
        "a dock block changed the snapshot_hash -- blocking one dock would now make every "
        "outstanding row on it SNAPSHOT_STALE instead of DISPLACEMENT_DETECTED"
    )


@pytest.mark.asyncio
async def test_an_overlapping_claim_still_changes_the_snapshot_hash(queue_repo):
    """The other side of the exclusion, so the test above cannot pass by the hash ignoring
    conflicts altogether."""
    start = NOW + timedelta(hours=1)

    def _render():
        queue_repo["state"]["rows"] = [
            _queue_row(appointment_id="APT-UNCLAIMED", occupancy=False, interval_start=start)
        ]
        return planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    queue_repo["state"]["occupancy"] = []
    clean = (await _render()).items[0]
    queue_repo["state"]["occupancy"] = [
        _occupancy_row(
            appointment_id="APT-OTHER",
            start=start + timedelta(minutes=30),
            end=start + timedelta(minutes=90),
        )
    ]
    contested = (await _render()).items[0]

    assert contested.snapshot_hash != clean.snapshot_hash


@pytest.mark.asyncio
async def test_both_conflict_legs_are_carried_and_told_apart(queue_repo):
    """A row can be both displaced and blocked, and the two are different harms.

    `INTERVAL_CONFLICT` is "another truck is booked here" -- a displacement the planner may still
    choose to cause. `DOCK_BLOCKED` is "there is no dock" -- nothing to choose. One untyped list
    would have made the row say the same sentence for both.
    """
    start = NOW + timedelta(hours=1)
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT-UNCLAIMED", occupancy=False, interval_start=start)
    ]
    queue_repo["state"]["occupancy"] = [
        _occupancy_row(
            appointment_id="APT-OTHER",
            start=start + timedelta(minutes=30),
            end=start + timedelta(minutes=90),
        )
    ]
    queue_repo["state"]["blocks"] = {"APT-UNCLAIMED": [_dock_block("DEVT-2")]}

    row = (
        await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)
    ).items[0]

    assert [c["conflict_type"] for c in row.displacement.conflicts] == [
        "INTERVAL_CONFLICT",
        "DOCK_BLOCKED",
    ]
    # The claim leg keeps every field it carried before the discriminator was added.
    assert row.displacement.conflicts[0]["shipment_id"] == "SHP-APT-OTHER"
    # And the block leg names no shipment at all -- nobody is displaced, the dock is gone.
    assert "shipment_id" not in row.displacement.conflicts[1]


@pytest.mark.asyncio
async def test_the_dock_block_query_is_asked_about_exactly_the_queued_appointments(queue_repo):
    """The shared predicate is only as good as the ids it is asked about.

    `load_dock_block_conflicts` re-derives each appointment's interval through `snapshot.py`'s own
    `_TARGET_CTE`, so the caller passes ids and never windows -- passing a window here would be the
    second interval derivation the shared CTE exists to prevent.
    """
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT-A", occupancy=False),
        _queue_row(appointment_id="APT-B", shipment_id="SHP2", occupancy=False),
    ]

    await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    assert queue_repo["calls"]["blocks"] == [["APT-A", "APT-B"]]


@pytest.mark.asyncio
async def test_an_empty_queue_asks_no_dock_block_question(queue_repo):
    """One query for an empty queue, still -- the common case for four of the five coordinators."""
    queue_repo["state"]["rows"] = []

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    assert queue.count == 0
    assert queue_repo["calls"]["blocks"] == []
    assert queue_repo["order"] == ["rows"]


@pytest.mark.asyncio
async def test_queue_ignores_a_claim_on_another_dock(queue_repo):
    start = NOW + timedelta(hours=1)
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT-UNCLAIMED", occupancy=False, interval_start=start)
    ]
    queue_repo["state"]["occupancy"] = [
        _occupancy_row(
            appointment_id="APT-OTHER-DOCK",
            dock_id="DOCK-JAI-D2",
            start=start,
            end=start + timedelta(hours=1),
        )
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    assert queue.items[0].displacement.status == "NONE"


@pytest.mark.asyncio
async def test_queue_does_not_bury_a_critical_that_arrived_late(queue_repo):
    """SS7.3's seeded SHP1014 case -- the reason the sort is neither FIFO nor pure TTL."""
    queue_repo["state"]["rows"] = [
        _queue_row(
            appointment_id="APT-OLD-NORMAL",
            priority_code="NORMAL",
            booked_at=NOW - timedelta(minutes=13),
        ),
        _queue_row(
            appointment_id="APT-NEW-CRITICAL",
            shipment_id="SHP1014",
            priority_code="CRITICAL",
            booked_at=NOW - timedelta(minutes=1),
        ),
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    assert [item.appointment_id for item in queue.items] == [
        "APT-NEW-CRITICAL",
        "APT-OLD-NORMAL",
    ]


@pytest.mark.asyncio
async def test_queue_ttl_pressure_lifts_a_row_by_at_most_one_priority_band(queue_repo):
    """A NORMAL at its deadline ties a fresh HIGH; it can never outrank a fresh CRITICAL."""
    queue_repo["state"]["rows"] = [
        _queue_row(
            appointment_id="APT-EXPIRING-NORMAL",
            priority_code="NORMAL",
            booked_at=NOW - timedelta(minutes=15),
        ),
        _queue_row(
            appointment_id="APT-FRESH-CRITICAL", priority_code="CRITICAL", booked_at=NOW
        ),
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    by_id = {item.appointment_id: item for item in queue.items}
    assert by_id["APT-EXPIRING-NORMAL"].urgency.ttl_pressure == planner_service.TTL_PRESSURE_MAX
    assert by_id["APT-EXPIRING-NORMAL"].urgency.score == 3000  # NORMAL 2000 + a full band
    assert by_id["APT-FRESH-CRITICAL"].urgency.score == 4000
    assert queue.items[0].appointment_id == "APT-FRESH-CRITICAL"


@pytest.mark.asyncio
async def test_queue_promotes_a_driver_physically_waiting_but_not_one_being_served(queue_repo):
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT-WAITING", queue_state="WAITING_LATE", booked_at=NOW),
        _queue_row(appointment_id="APT-IN-DOCK", queue_state="IN_DOCK", booked_at=NOW),
        _queue_row(appointment_id="APT-TRANSIT", booked_at=NOW),
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    by_id = {item.appointment_id: item for item in queue.items}
    assert by_id["APT-WAITING"].urgency.waiting_bonus == planner_service.WAITING_BONUS
    assert by_id["APT-WAITING"].gate.physically_waiting is True
    # CALLED_TO_DOCK / IN_DOCK are being served, not burning detention in the yard.
    assert by_id["APT-IN-DOCK"].urgency.waiting_bonus == 0
    assert by_id["APT-TRANSIT"].urgency.waiting_bonus == 0
    assert queue.items[0].appointment_id == "APT-WAITING"


@pytest.mark.asyncio
async def test_queue_reports_an_overdue_row_rather_than_hiding_it(queue_repo):
    """The sweeper runs on a cadence, so a row can be past its deadline and still PENDING."""
    queue_repo["state"]["rows"] = [_queue_row(booked_at=NOW - timedelta(minutes=20))]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    assert queue.items[0].ttl.expired is True
    assert queue.items[0].ttl.remaining_seconds == -5 * 60


@pytest.mark.asyncio
async def test_snapshot_hash_ignores_the_passing_of_time_but_not_a_new_conflict(queue_repo):
    start = NOW + timedelta(hours=1)
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT-UNCLAIMED", occupancy=False, interval_start=start)
    ]

    first = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)
    later = await planner_service.get_planner_queue(
        AsyncMock(), _planner_ctx(), clock=CLOCK.shifted(timedelta(minutes=7))
    )
    assert first.items[0].snapshot_hash == later.items[0].snapshot_hash
    assert first.items[0].ttl.remaining_seconds != later.items[0].ttl.remaining_seconds

    queue_repo["state"]["occupancy"] = [
        _occupancy_row(
            appointment_id="APT-OTHER", start=start, end=start + timedelta(hours=1)
        )
    ]
    displaced = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)
    assert displaced.items[0].snapshot_hash != first.items[0].snapshot_hash


@pytest.mark.asyncio
async def test_queue_marks_a_confirm_that_would_pass_the_drivers_own_limit(queue_repo):
    start = NOW + timedelta(hours=4)
    queue_repo["state"]["rows"] = [
        _queue_row(interval_start=start, latest_acceptable_ts=(start - timedelta(hours=1)).isoformat()),
        _queue_row(appointment_id="APT-UNPARSEABLE", latest_acceptable_ts="not a timestamp"),
    ]

    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    by_id = {item.appointment_id: item for item in queue.items}
    assert by_id["APT1"].latest_acceptable_breached is True
    # "we could not check" is not "we checked and it is fine".
    assert by_id["APT-UNPARSEABLE"].latest_acceptable_breached is None


@pytest.mark.asyncio
async def test_empty_queue_costs_one_query_and_no_occupancy_scan(queue_repo):
    queue = await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    assert queue.items == []
    assert queue.count == 0
    assert queue_repo["calls"]["occupancy"] == []


@pytest.mark.asyncio
async def test_queue_clamps_the_limit_and_reports_when_the_page_is_full(queue_repo):
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id=f"APT{n}", shipment_id=f"SHP{n}") for n in range(3)
    ]

    queue = await planner_service.get_planner_queue(
        AsyncMock(), _planner_ctx(), limit=10_000, clock=CLOCK
    )

    assert queue.limit == planner_service.MAX_QUEUE_LIMIT
    assert queue_repo["calls"]["rows"][0]["limit"] == planner_service.MAX_QUEUE_LIMIT
    assert queue.limit_reached is False

    full = await planner_service.get_planner_queue(
        AsyncMock(), _planner_ctx(), limit=3, clock=CLOCK
    )
    assert full.limit_reached is True


@pytest.fixture
def two_phase_hold_on(monkeypatch):
    """Pin the D2 flag on rather than inheriting whatever `.env.local` happens to say.

    `get_settings` is `lru_cache`d, so the cache is cleared on both sides -- without the second
    clear a later test in the same session would inherit this one's flag.
    """
    from app.core.settings import get_settings

    monkeypatch.setenv("TWO_PHASE_HOLD_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TWO_PHASE_HOLD_ENABLED", raising=False)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_queue_expires_lapsed_holds_before_reading_displacement(
    queue_repo, two_phase_hold_on
):
    """Issue #98. Order is the whole assertion, not just that the call happened.

    The displacement column and `snapshot_hash` are both built from `list_live_dock_occupancy`'s
    rows, and that query deliberately carries no `expires_at > now()` term (#84 -- it has to
    predict what the exclusion constraint refuses). So a lapsed, unswept hold has to be gone from
    the *table* before that read runs, not filtered out of its result afterwards. Running the
    expiry after the read would leave the dead hold in this render's conflicts and its digest,
    which is exactly the `DISPLACEMENT_DETECTED`-from-a-dead-hold #98 reports.
    """
    queue_repo["state"]["rows"] = [
        _queue_row(appointment_id="APT1", shipment_id="SHP1"),
        _queue_row(appointment_id="APT2", shipment_id="SHP2"),
    ]

    await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)

    # `blocks` (issue #88's dock-block leg) runs last and is deliberately outside this ordering
    # constraint: it reads `dock_status_events`, which has no hold lifecycle for the expiry to
    # touch, so nothing about it can be poisoned by a lapsed hold.
    assert queue_repo["order"] == ["rows", "expiry", "occupancy", "blocks"]
    call = queue_repo["calls"]["expiry"][0]
    # The same appointment ids the displacement check is about to be computed for -- not a
    # facility-wide sweep, and not a subset.
    assert sorted(call["appointment_ids"]) == ["APT1", "APT2"]
    assert call["now"] == NOW
    assert call["actor_user_id"] == "USR-PLN-1"


@pytest.mark.asyncio
async def test_queue_skips_the_expiry_entirely_when_there_is_nothing_to_read(queue_repo):
    """An empty queue costs no extra statement -- the common case for four of the five
    coordinators at any moment, and the reason the whole occupancy branch is already guarded."""
    queue_repo["state"]["rows"] = []
    await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)
    assert queue_repo["calls"]["expiry"] == []


@pytest.mark.asyncio
async def test_queue_horizon_is_translated_to_an_absolute_bound(queue_repo):
    await planner_service.get_planner_queue(
        AsyncMock(), _planner_ctx(), horizon_hours=8, clock=CLOCK
    )
    assert queue_repo["calls"]["rows"][0]["horizon_end"] == NOW + timedelta(hours=8)

    await planner_service.get_planner_queue(AsyncMock(), _planner_ctx(), clock=CLOCK)
    assert queue_repo["calls"]["rows"][1]["horizon_end"] is None


@pytest.mark.asyncio
async def test_queue_derives_scope_from_the_token_and_refuses_another_facility(queue_repo):
    """M15: the `facility_id` argument narrows within scope; it never decides it.

    Since issue #106 "within scope" also covers a `user_scopes` FACILITY grant, so the refusal is
    asserted against a session that explicitly reports **no** such grant -- otherwise this would be
    testing the mock rather than the rule.
    """
    await planner_service.get_planner_queue(
        AsyncMock(), _planner_ctx(facility_id=FACILITY), facility_id=None, clock=CLOCK
    )
    assert queue_repo["calls"]["rows"][0]["facility_id"] == FACILITY

    with pytest.raises(AppError) as exc:
        await planner_service.get_planner_queue(
            _scope_probe_session(grants=False),
            _planner_ctx(facility_id=FACILITY),
            facility_id=OTHER_FACILITY,
            clock=CLOCK,
        )
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_queue_accepts_a_second_facility_the_callers_user_scopes_grant(queue_repo):
    """Issue #106. A non-global coordinator granted two facilities may read the second.

    Latent when filed -- no roster account holds two FACILITY rows -- but `#72`'s admin console
    ships the write that creates one, and before this the moment anyone used it their second
    facility answered 403 on every surface. The grant is the server's own row for this verified
    `user_id`, so `facility_id` is still a request the server validates, never an assertion it
    trusts (M15/NFR-019).
    """
    await planner_service.get_planner_queue(
        _scope_probe_session(grants=True),
        _planner_ctx(facility_id=FACILITY),
        facility_id=OTHER_FACILITY,
        clock=CLOCK,
    )
    assert queue_repo["calls"]["rows"][0]["facility_id"] == OTHER_FACILITY


@pytest.mark.asyncio
async def test_queue_refuses_an_unscoped_global_read(queue_repo):
    """This surface is deliberately single-facility, so an ADMIN must name one."""
    with pytest.raises(AppError) as exc:
        await planner_service.get_planner_queue(
            AsyncMock(),
            _planner_ctx(facility_id=None, role=RoleName.ADMIN),
            facility_id=None,
            clock=CLOCK,
        )
    assert exc.value.code == "FORBIDDEN"


# ---------------------------------------------------------------------------------------------
# get_dock_board -- the Board tab's at-rest occupancy view (E5.3 states 2/22).
#
# The horizon tests are the load-bearing ones: `screens.md` section 3 fixes the axis at "four
# hours, or until closing time, whichever comes sooner", and both halves of that sentence are a
# real behaviour rather than a caption.
# ---------------------------------------------------------------------------------------------


def _facility_row(*, timezone_name: str = "Asia/Kolkata", close_time: str = "22:00") -> dict:
    return {
        "facility_id": FACILITY,
        "facility_name": "Jaipur",
        "timezone": timezone_name,
        "close_time": close_time,
    }


@pytest.fixture
def board_repo(monkeypatch):
    """Patch the two repository reads `get_dock_board` makes, and record their arguments."""
    calls: dict[str, list] = {"docks": [], "occupancy": []}
    state: dict[str, list] = {"docks": [], "occupancy": []}

    async def _docks(session, facility_id):
        calls["docks"].append(facility_id)
        return state["docks"]

    async def _occupancy(session, **kwargs):
        calls["occupancy"].append(kwargs)
        return state["occupancy"]

    monkeypatch.setattr(planner_service.facilities_repo, "list_docks", _docks)
    monkeypatch.setattr(planner_service.operations_repo, "list_live_dock_occupancy", _occupancy)
    return {"calls": calls, "state": state}


@pytest.mark.asyncio
async def test_board_returns_every_lane_even_with_no_occupancy(board_repo):
    """`stitch-prompts.md` section 8's empty variant: a quiet facility still renders its lanes."""
    board_repo["state"]["docks"] = [
        {"dock_id": DOCK, "dock_code": "D1", "dock_type": "STANDARD", "dock_status": "ACTIVE",
         "supports_refrigerated": 0, "max_vehicle_weight_kg": 20000},
    ]
    session = _session_with(_facility_row(), [])

    board = await planner_service.get_dock_board(session, _planner_ctx(), clock=CLOCK)

    assert [d.dock_code for d in board.docks] == ["D1"]
    assert board.bars == []
    assert board.blocks == []
    assert board.facility_name == "Jaipur"


@pytest.mark.asyncio
async def test_board_horizon_is_four_hours_when_the_facility_closes_later(board_repo):
    session = _session_with(_facility_row(close_time="22:00"), [])
    board = await planner_service.get_dock_board(session, _planner_ctx(), clock=CLOCK)
    assert board.horizon_end == NOW + timedelta(hours=planner_service.BOARD_HORIZON_HOURS)
    assert board.horizon_end_reason == planner_service.BOARD_HORIZON_ROLLING


@pytest.mark.asyncio
async def test_board_horizon_stops_at_facility_close_when_that_is_sooner(board_repo):
    """NOW is 12:00 UTC = 17:30 Asia/Kolkata, so an 18:00 close is 30 minutes away -- sooner than
    the rolling four hours, and the axis has to stop there rather than run past closing."""
    session = _session_with(_facility_row(close_time="18:00"), [])
    board = await planner_service.get_dock_board(session, _planner_ctx(), clock=CLOCK)
    assert board.horizon_end_reason == planner_service.BOARD_HORIZON_FACILITY_CLOSE
    assert board.horizon_end == NOW + timedelta(minutes=30)


@pytest.mark.asyncio
async def test_board_falls_back_to_the_rolling_window_on_an_unusable_timezone(board_repo):
    """A board that renders four hours beats a board that raises. The reason field says which."""
    session = _session_with(_facility_row(timezone_name="Not/AZone"), [])
    board = await planner_service.get_dock_board(session, _planner_ctx(), clock=CLOCK)
    assert board.horizon_end_reason == planner_service.BOARD_HORIZON_ROLLING


@pytest.mark.asyncio
async def test_board_horizon_hours_can_only_narrow(board_repo):
    session = _session_with(_facility_row(), [])
    board = await planner_service.get_dock_board(
        session, _planner_ctx(), horizon_hours=99, clock=CLOCK
    )
    assert board.horizon_end == NOW + timedelta(hours=planner_service.BOARD_HORIZON_HOURS)


@pytest.mark.asyncio
async def test_board_carries_a_hold_bar_with_its_source_and_expiry(board_repo):
    """Issue #84's hold-aware occupancy read, seen from the board: a D2 hold has no appointment
    row, so `claim_source` and `hold_expires_at` are the only channels that say it is one."""
    start = NOW + timedelta(minutes=30)
    expires = NOW + timedelta(seconds=90)
    board_repo["state"]["occupancy"] = [
        {
            "occupancy_id": 7,
            "dock_id": DOCK,
            "appointment_id": None,
            "window_start": start,
            "window_end": start + timedelta(hours=1),
            "shipment_id": "SHP-1",
            "appointment_status": "HELD",
            "claim_source": "dock_occupancy_hold",
            "hold_expires_at": expires,
            "order_reference": "ORD-1",
        }
    ]
    session = _session_with(_facility_row(), [])

    board = await planner_service.get_dock_board(session, _planner_ctx(), clock=CLOCK)

    assert len(board.bars) == 1
    bar = board.bars[0]
    assert bar.state == "HELD"
    assert bar.claim_source == "dock_occupancy_hold"
    assert bar.appointment_id is None
    assert bar.hold_expires_at == expires


@pytest.mark.asyncio
async def test_board_reads_occupancy_over_exactly_its_own_horizon(board_repo):
    session = _session_with(_facility_row(close_time="22:00"), [])
    board = await planner_service.get_dock_board(session, _planner_ctx(), clock=CLOCK)
    call = board_repo["calls"]["occupancy"][0]
    assert call["range_start"] == board.horizon_start
    assert call["range_end"] == board.horizon_end
    assert call["facility_id"] == FACILITY


@pytest.mark.asyncio
async def test_board_derives_scope_from_the_token_and_refuses_another_facility(board_repo):
    """M15, same contract as the queue: `facility_id` narrows within scope, never decides it."""
    session = _session_with(_facility_row(), [])
    await planner_service.get_dock_board(session, _planner_ctx(), facility_id=None, clock=CLOCK)
    assert board_repo["calls"]["docks"][0] == FACILITY

    with pytest.raises(AppError) as exc:
        await planner_service.get_dock_board(
            # Explicitly "no user_scopes grant" -- see `_scope_probe_session` (issue #106).
            _scope_probe_session(grants=False),
            _planner_ctx(),
            facility_id=OTHER_FACILITY,
            clock=CLOCK,
        )
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_board_refuses_an_unscoped_global_read(board_repo):
    with pytest.raises(AppError) as exc:
        await planner_service.get_dock_board(
            AsyncMock(), _planner_ctx(facility_id=None, role=RoleName.ADMIN), clock=CLOCK
        )
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_board_returns_open_ended_blocks_with_a_null_end(board_repo):
    """`event_end_ts IS NULL` means "out until someone ends it"; the server does not invent one."""
    session = _session_with(
        _facility_row(),
        [
            {
                "dock_event_id": "DEVT002",
                "dock_id": DOCK,
                "event_type": "MAINTENANCE",
                "event_start_ts": NOW - timedelta(hours=1),
                "event_end_ts": None,
                "reason": "outage",
            }
        ],
    )
    board = await planner_service.get_dock_board(session, _planner_ctx(), clock=CLOCK)
    assert len(board.blocks) == 1
    assert board.blocks[0].event_end_ts is None
    assert board.blocks[0].reason == "outage"
