"""M8 expiry sweeper + section 9.1 injectable clock (GitHub issue #20 / E1.5).

What these tests are actually pinning down, beyond "it runs":

* the D9 deadline is computed from the *injected* clock, so the suite does not start failing
  tomorrow (SOLUTION_DESIGN.md section 9.1);
* the locking statement carries `appointment_status = 'PENDING_CONFIRMATION'` and `SKIP LOCKED`,
  which is the entire mechanism behind section 7.5.1's race resolution -- if someone deletes that
  predicate the race silently comes back, so it is asserted on the SQL text itself;
* the `dock_occupancy` claim is released through `allocation._release_dock_occupancy`, in the same
  transaction, before the commit -- not a parallel release path;
* the loser of the race gets `ALREADY_ACTIONED` naming the winner, not a generic 409.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.clock import SYSTEM_CLOCK, FrozenClock, SystemClock, resolve_clock
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling import allocation, expiry

# 2026-08-13 is D14's snapshot date; 12:00 IST is 06:30 UTC.
SNAPSHOT = datetime(2026, 8, 13, 6, 30, tzinfo=timezone.utc)


def _ops_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req",
        auth_subject="auth-ops",
        user_id="USR101",
        email="ops@setuhaul.example",
        full_name="Ops Executive",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-JAI-01",
    )


# --------------------------------------------------------------------------------------
# section 9.1 -- the injectable clock
# --------------------------------------------------------------------------------------


def test_system_clock_is_timezone_aware_utc():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_frozen_clock_returns_the_same_instant_every_call():
    clock = FrozenClock(SNAPSHOT)
    assert clock.now() == SNAPSHOT
    assert clock.now() == clock.now()


def test_frozen_clock_rejects_a_naive_instant():
    """A naive `now` compared against a timestamptz column is the section 9.1 defect itself."""
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 8, 13, 12, 0))


def test_frozen_clock_normalises_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    clock = FrozenClock(datetime(2026, 8, 13, 12, 0, tzinfo=ist))
    assert clock.now() == SNAPSHOT


def test_frozen_clock_shift_steps_across_a_ttl_boundary():
    clock = FrozenClock(SNAPSHOT)
    later = clock.shifted(timedelta(minutes=16))
    assert later.now() - clock.now() == timedelta(minutes=16)
    assert clock.now() == SNAPSHOT  # original is immutable


def test_resolve_clock_defaults_to_the_system_clock():
    assert resolve_clock(None) is SYSTEM_CLOCK
    frozen = FrozenClock(SNAPSHOT)
    assert resolve_clock(frozen) is frozen


# --------------------------------------------------------------------------------------
# D2 -- the HELD leg, reported as unsupported rather than silently zero
# --------------------------------------------------------------------------------------


def test_held_sweep_reports_unsupported_and_names_both_missing_schema_pieces():
    """Forcing function: when the D2 columns land, this test fails and demands the real sweep."""
    result = expiry.sweep_held_holds(ttl_seconds=90)

    assert result.supported is False
    assert result.expired == 0
    assert result.ttl_seconds == 90
    assert result.unsupported_reason is not None
    assert "HELD status" in result.unsupported_reason
    assert "expires_at" in result.unsupported_reason


# --------------------------------------------------------------------------------------
# D9 -- the PENDING sweep
# --------------------------------------------------------------------------------------


def _sweeper_session(candidates: list[dict], *, lock_returns: list[object]) -> AsyncMock:
    """A session whose `execute` walks a scripted sequence of the sweeper's statements.

    Order per sweep: actor check, candidate scan, then for each candidate a locking SELECT and
    (when locked) an UPDATE, a release and an audit INSERT. `lock_returns` supplies one entry per
    candidate: a row mapping to hand back, or None to simulate SKIP LOCKED / lost race.
    """
    session = AsyncMock()
    lock_iter = iter(lock_returns)

    async def _execute(statement, params=None):
        sql = str(statement)
        result = MagicMock()
        if "FROM public.users" in sql:
            result.first.return_value = (1,)
            return result
        if "ORDER BY a.booked_at ASC" in sql:
            result.mappings.return_value.all.return_value = candidates
            return result
        if "FOR UPDATE SKIP LOCKED" in sql:
            result.mappings.return_value.first.return_value = next(lock_iter)
            return result
        return result

    session.execute.side_effect = _execute
    return session


@pytest.mark.asyncio
async def test_sweep_derives_the_d9_deadline_from_the_injected_clock(monkeypatch):
    session = _sweeper_session([], lock_returns=[])
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    result = await expiry.sweep_expired_appointments(
        session,
        actor_user_id="USR-SYS",
        clock=FrozenClock(SNAPSHOT),
        pending_ttl_minutes=15,
    )

    assert result.as_of == SNAPSHOT.isoformat()
    assert result.pending_deadline == (SNAPSHOT - timedelta(minutes=15)).isoformat()
    scan = [
        call
        for call in session.execute.await_args_list
        if "ORDER BY a.booked_at ASC" in str(call.args[0])
    ]
    assert scan, "candidate scan never ran"
    assert scan[0].args[1]["deadline"] == SNAPSHOT - timedelta(minutes=15)


@pytest.mark.asyncio
async def test_sweep_locks_with_the_status_predicate_and_skip_locked(monkeypatch):
    """This SQL *is* section 7.5.1's race resolution -- see expiry.py's module docstring."""
    candidate = {
        "appointment_id": "APT-STALE",
        "shipment_id": "SHP1002",
        "slot_id": "SLT001",
        "booked_at": SNAPSHOT - timedelta(minutes=40),
        "facility_id": "FAC-JAI-01",
    }
    session = _sweeper_session(
        [candidate],
        lock_returns=[
            {"appointment_id": "APT-STALE", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"}
        ],
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    lock_sql = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if "FOR UPDATE SKIP LOCKED" in str(call.args[0])
    )
    assert "appointment_status = 'PENDING_CONFIRMATION'" in lock_sql
    assert "is_current = 1" in lock_sql
    assert "FOR UPDATE SKIP LOCKED" in lock_sql


@pytest.mark.asyncio
async def test_sweep_releases_the_dock_claim_in_the_same_transaction(monkeypatch):
    """Without this an EXPIRED appointment blocks its dock interval forever (E1.3's release rule)."""
    candidate = {
        "appointment_id": "APT-STALE",
        "shipment_id": "SHP1002",
        "slot_id": "SLT001",
        "booked_at": SNAPSHOT - timedelta(minutes=40),
        "facility_id": "FAC-JAI-01",
    }
    session = _sweeper_session(
        [candidate],
        lock_returns=[
            {"appointment_id": "APT-STALE", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"}
        ],
    )
    order: list[str] = []
    session.commit.side_effect = lambda: order.append("commit")

    async def _release(_session, appointment_id):
        order.append(f"release:{appointment_id}")
        return True

    monkeypatch.setattr(allocation, "_release_dock_occupancy", _release)

    result = await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    assert order == ["release:APT-STALE", "commit"], "release must precede the commit"
    assert result.pending_expired == 1
    assert result.expired[0].appointment_id == "APT-STALE"
    assert result.expired[0].occupancy_released is True
    assert result.expired[0].facility_id == "FAC-JAI-01"


@pytest.mark.asyncio
async def test_sweep_records_a_claimless_expiry_honestly(monkeypatch):
    """The E1.1 backfill left 42 active appointments without a claim; expiring one is not a lie."""
    candidate = {
        "appointment_id": "APT-NOCLAIM",
        "shipment_id": "SHP1002",
        "slot_id": "SLT001",
        "booked_at": SNAPSHOT - timedelta(minutes=40),
        "facility_id": "FAC-JAI-01",
    }
    session = _sweeper_session(
        [candidate],
        lock_returns=[
            {"appointment_id": "APT-NOCLAIM", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"}
        ],
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=False))

    result = await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    assert result.pending_expired == 1
    assert result.expired[0].occupancy_released is False


@pytest.mark.asyncio
async def test_sweep_writes_an_audit_row_naming_the_sweeper_as_the_actor(monkeypatch):
    """section 7.5.1: "The audit log must show which won and why"."""
    candidate = {
        "appointment_id": "APT-STALE",
        "shipment_id": "SHP1002",
        "slot_id": "SLT001",
        "booked_at": SNAPSHOT - timedelta(minutes=40),
        "facility_id": "FAC-JAI-01",
    }
    session = _sweeper_session(
        [candidate],
        lock_returns=[
            {"appointment_id": "APT-STALE", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"}
        ],
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    audit = next(
        call.args[1]
        for call in session.execute.await_args_list
        if "INSERT INTO public.audit_logs" in str(call.args[0])
    )
    assert audit["user_id"] == "USR-SYS"
    assert audit["action_type"] == allocation.AUDIT_ACTION_EXPIRE_APPOINTMENT
    assert audit["entity_id"] == "APT-STALE"
    new_value = json.loads(audit["new_value_json"])
    assert new_value["status"] == "EXPIRED"
    assert new_value["is_current"] == 0
    assert new_value["actor"] == "EXPIRY_SWEEPER"
    assert new_value["occupancy_released"] is True


@pytest.mark.asyncio
async def test_sweep_binds_a_datetime_to_timestamptz_and_a_string_to_text(monkeypatch):
    """Not style -- a hard runtime failure if swapped.

    `appointments.updated_at` is `timestamptz` after E1.1; asyncpg 0.31.0 raises
    `DataError: invalid input for query argument $1 ... (expected a datetime.date or
    datetime.datetime instance, got 'str')` when a str is bound there (verified live 2026-08-23).
    `audit_logs.created_at` was never converted and is still `text`. This test is what stops a
    future tidy-up from making both the same.
    """
    candidate = {
        "appointment_id": "APT-STALE",
        "shipment_id": "SHP1002",
        "slot_id": "SLT001",
        "booked_at": SNAPSHOT - timedelta(minutes=40),
        "facility_id": "FAC-JAI-01",
    }
    session = _sweeper_session(
        [candidate],
        lock_returns=[
            {"appointment_id": "APT-STALE", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"}
        ],
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    update = next(
        call.args[1]
        for call in session.execute.await_args_list
        if "UPDATE public.appointments" in str(call.args[0])
    )
    assert isinstance(update["updated_at"], datetime)
    assert update["updated_at"] == SNAPSHOT

    audit = next(
        call.args[1]
        for call in session.execute.await_args_list
        if "INSERT INTO public.audit_logs" in str(call.args[0])
    )
    assert isinstance(audit["created_at"], str)
    assert audit["created_at"] == SNAPSHOT.isoformat()

    scan = next(
        call.args[1]
        for call in session.execute.await_args_list
        if "ORDER BY a.booked_at ASC" in str(call.args[0])
    )
    assert isinstance(scan["deadline"], datetime)


@pytest.mark.asyncio
async def test_sweep_escalates_via_the_shared_worklist_not_a_second_mechanism(monkeypatch):
    """M8's escalate leg (SOLUTION_DESIGN.md section 7.4, PENDING_EXPIRED_UNACTIONED) reuses
    escalation_queue -- same table E1.2's REQUIRES_TIME_RESOLUTION/REQUIRES_DOCK_REASSIGNMENT
    already reuses -- not a new mechanism."""
    candidate = {
        "appointment_id": "APT-STALE",
        "shipment_id": "SHP1002",
        "slot_id": "SLT001",
        "booked_at": SNAPSHOT - timedelta(minutes=40),
        "facility_id": "FAC-JAI-01",
    }
    session = _sweeper_session(
        [candidate],
        lock_returns=[
            {"appointment_id": "APT-STALE", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"}
        ],
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    esc = next(
        call.args[1]
        for call in session.execute.await_args_list
        if "INSERT INTO public.escalation_queue" in str(call.args[0])
    )
    assert esc["shipment_id"] == "SHP1002"
    assert esc["facility_id"] == "FAC-JAI-01"
    assert esc["dedupe_key"] == "PENDING-EXPIRED-APT-STALE"
    payload = json.loads(esc["payload_json"])
    assert payload["appointment_id"] == "APT-STALE"
    assert payload["occupancy_released"] is True
    esc_sql = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if "INSERT INTO public.escalation_queue" in str(call.args[0])
    )
    assert "PENDING_EXPIRED_UNACTIONED" in esc_sql
    assert "ON CONFLICT (dedupe_key) DO NOTHING" in esc_sql


@pytest.mark.asyncio
async def test_sweep_defers_a_row_it_could_not_lock_without_writing(monkeypatch):
    """SKIP LOCKED / lost race: no UPDATE, no release, no commit -- picked up next cycle."""
    candidate = {
        "appointment_id": "APT-CONTENDED",
        "shipment_id": "SHP1002",
        "slot_id": "SLT001",
        "booked_at": SNAPSHOT - timedelta(minutes=40),
        "facility_id": "FAC-JAI-01",
    }
    session = _sweeper_session([candidate], lock_returns=[None])
    release = AsyncMock(return_value=True)
    monkeypatch.setattr(allocation, "_release_dock_occupancy", release)

    result = await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    assert result.pending_candidates == 1
    assert result.pending_expired == 0
    assert result.pending_deferred_or_lost == 1
    release.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    assert not [
        call
        for call in session.execute.await_args_list
        if "UPDATE public.appointments" in str(call.args[0])
    ]


@pytest.mark.asyncio
async def test_sweep_commits_per_appointment_so_one_bad_row_cannot_undo_the_others(monkeypatch):
    candidates = [
        {
            "appointment_id": f"APT-{i}",
            "shipment_id": "SHP1002",
            "slot_id": "SLT001",
            "booked_at": SNAPSHOT - timedelta(minutes=40),
            "facility_id": "FAC-JAI-01",
        }
        for i in range(3)
    ]
    session = _sweeper_session(
        candidates,
        lock_returns=[
            {"appointment_id": "APT-0", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"},
            None,
            {"appointment_id": "APT-2", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"},
        ],
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    result = await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT)
    )

    assert result.pending_expired == 2
    assert result.pending_deferred_or_lost == 1
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_sweep_flags_a_full_batch_so_a_backlog_is_visible(monkeypatch):
    candidates = [
        {
            "appointment_id": f"APT-{i}",
            "shipment_id": "SHP1002",
            "slot_id": "SLT001",
            "booked_at": SNAPSHOT - timedelta(minutes=40),
            "facility_id": "FAC-JAI-01",
        }
        for i in range(2)
    ]
    session = _sweeper_session(
        candidates,
        lock_returns=[
            {"appointment_id": "APT-0", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"},
            {"appointment_id": "APT-1", "shipment_id": "SHP1002", "slot_id": "SLT001",
             "facility_id": "FAC-JAI-01"},
        ],
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    result = await expiry.sweep_expired_appointments(
        session, actor_user_id="USR-SYS", clock=FrozenClock(SNAPSHOT), batch_limit=2
    )

    assert result.batch_limit == 2
    assert result.batch_limit_reached is True
    scan = next(
        call.args[1]
        for call in session.execute.await_args_list
        if "ORDER BY a.booked_at ASC" in str(call.args[0])
    )
    assert scan["limit"] == 2


@pytest.mark.asyncio
async def test_sweep_refuses_before_writing_when_the_audit_actor_is_not_a_real_user():
    """audit_logs.user_id is a NOT NULL FK; a bad actor must fail closed, not mid-transaction."""
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = None
    session.execute.return_value = result

    with pytest.raises(AppError) as exc:
        await expiry.sweep_expired_appointments(
            session, actor_user_id="USR-NOPE", clock=FrozenClock(SNAPSHOT)
        )

    assert exc.value.code == "SWEEPER_ACTOR_INVALID"
    assert exc.value.status_code == 503
    session.commit.assert_not_awaited()
    assert session.execute.await_count == 1, "must refuse before the candidate scan"


# --------------------------------------------------------------------------------------
# section 7.5.1 -- the loser-facing half of the race
# --------------------------------------------------------------------------------------


def test_already_actioned_error_names_the_winning_transition():
    err = allocation._already_actioned_error(
        {"appointment_status": "EXPIRED", "cancellation_reason": expiry.EXPIRY_REASON},
        attempted="confirm",
    )

    assert err.code == "ALREADY_ACTIONED"
    assert err.status_code == 409
    assert "EXPIRED" in err.message
    assert "D9" in err.message


@pytest.mark.asyncio
async def test_confirm_loses_the_race_with_already_actioned(monkeypatch):
    """The planner clicked Confirm; the sweeper had already expired the row."""
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(
            return_value={
                "shipment_id": "SHP1002",
                "driver_id": "DRV001",
                "destination_facility_id": "FAC-JAI-01",
            }
        ),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(
            return_value={
                "appointment_id": "APT-STALE",
                "shipment_id": "SHP1002",
                "slot_id": "SLT001",
                "appointment_status": "EXPIRED",
                "is_current": 0,
                "cancellation_reason": expiry.EXPIRY_REASON,
            }
        ),
    )

    with pytest.raises(AppError) as exc:
        await allocation.confirm_appointment(
            session,
            _ops_ctx(),
            shipment_id="SHP1002",
            command=allocation.ConfirmAppointmentCommand(
                appointment_id="APT-STALE", warehouse_confirmation_ref="WH-1"
            ),
            idempotency_key="idem-1",
        )

    assert exc.value.code == "ALREADY_ACTIONED"
    assert "EXPIRED" in exc.value.message
    session.commit.assert_not_awaited()
