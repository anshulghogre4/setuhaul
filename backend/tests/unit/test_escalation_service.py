from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.services.escalation_service import EscalateExceptionCommand


def test_escalation_command_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        EscalateExceptionCommand(  # type: ignore[call-arg]
            shipment_id="SHP1017",
            escalation_type="NO_FEASIBLE_SLOT",
            untrusted_override=True,  # type: ignore[call-arg]
        )


def test_escalation_command_accepts_versioned_recommendation_payload():
    command = EscalateExceptionCommand(
        shipment_id="SHP1017",
        escalation_type="NO_FEASIBLE_SLOT",
        policy_version="sprint3_constraints_v1",
        recommendation_id="REC-123",
        payload={"blocking_reasons": [{"failure_code": "NO_CANDIDATE_SLOTS"}]},
    )

    assert command.escalation_type == "NO_FEASIBLE_SLOT"
    assert command.recommendation_id == "REC-123"


@pytest.mark.asyncio
async def test_resolve_escalation_updates_db_status():
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )

    mock_row = MagicMock()
    mock_row.mappings.return_value.first.return_value = {
        "escalation_id": "ESC-TEST-99",
        "shipment_id": "SHP1006",
        "facility_id": "FAC-GGN-01",
        "escalation_type": "NO_FEASIBLE_SLOT",
        "escalation_status": "RESOLVED",
    }

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_row

    res = await resolve_escalation(mock_session, ctx, "ESC-TEST-99", resolution_note="Approved by Ops Admin")

    assert res["escalation_id"] == "ESC-TEST-99"
    assert res["escalation_status"] == "RESOLVED"
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_resolve_escalation_persists_resolution_note():
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )

    mock_row = MagicMock()
    mock_row.mappings.return_value.first.return_value = {
        "escalation_id": "ESC-TEST-99",
        "shipment_id": "SHP1006",
        "facility_id": "FAC-GGN-01",
        "escalation_type": "NO_FEASIBLE_SLOT",
        "escalation_status": "RESOLVED",
        "resolution_note": "Slot manually confirmed at dock",
    }

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_row

    res = await resolve_escalation(
        mock_session, ctx, "ESC-TEST-99", resolution_note="Slot manually confirmed at dock"
    )

    assert res["resolution_note"] == "Slot manually confirmed at dock"
    # First call is the facility-scope lookup (issue #48's fix); the second is the
    # escalation_queue update, whose bound params must carry the note.
    second_call_params = mock_session.execute.call_args_list[1].args[1]
    assert second_call_params["note"] == "Slot manually confirmed at dock"


@pytest.mark.asyncio
async def test_escalate_exception_requires_confirmation_before_write():
    from unittest.mock import AsyncMock
    from app.services.escalation_service import EscalateExceptionCommand, escalate_exception
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
    )
    mock_session = AsyncMock()

    res = await escalate_exception(
        mock_session,
        ctx,
        EscalateExceptionCommand(
            shipment_id="SHP-D16-RAVI",
            escalation_type="NO_FEASIBLE_SLOT",
            payload={"reason": "driver asked for help"},
            confirmed=False,
        ),
    )

    assert res["status"] == "CONFIRMATION_REQUIRED"
    assert res["requires_confirmation"] is True
    # No DB call at all — not even the shipment-scope lookup — until confirmed=True.
    assert mock_session.execute.await_count == 0


@pytest.mark.asyncio
async def test_get_pending_confirmations_forbids_cross_facility_operator():
    """M15: an operator naming someone else's facility is refused.

    The session answers the issue-#106 `user_scopes` probe with **no** grant row, explicitly. A
    bare `AsyncMock` would answer `.first()` with a truthy mock and this test would pass against a
    resolver that had stopped refusing altogether -- the mock, not the rule, would be under test.
    """
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_pending_confirmations
    from app.core.execution_context import ExecutionContext, RoleName
    from app.core.errors import AppError

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )
    no_grant = MagicMock()
    no_grant.first.return_value = None
    mock_session = AsyncMock()
    mock_session.execute.return_value = no_grant

    with pytest.raises(AppError) as exc_info:
        await get_pending_confirmations(mock_session, ctx, "FAC-JAI-01")
    assert exc_info.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_pending_confirmations_serves_every_facility_when_none_is_named():
    """Issue #107. §7.5.5: omitting `facility_id` for a cross-facility role means all facilities.

    This shipped as a 403 -- `require_facility=True` against SQL that bound `:facility_id`
    unconditionally -- so an ADMIN whose `users.facility_id` is NULL (USR997, the live roster's
    admin) was refused on the ops reads unless they named a facility explicitly. Reproduced live
    read-only 2026-09-01: 403 with no parameter, 200 with `?facility_id=FAC-JAI-01`, 200 with
    `?facility_id=FAC-GGN-01`.

    Both halves are asserted, because "no 403" alone would also be satisfied by a query that
    quietly kept filtering: the statement must carry **no** facility predicate and **no**
    `facility_id` parameter.
    """
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_pending_confirmations
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR997",
        email="admin@setuhaul.com",
        full_name="Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
        facility_id=None,
    )
    mock_rows = MagicMock()
    mock_rows.mappings.return_value.all.return_value = [_pending_row()]
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_rows

    res = await get_pending_confirmations(mock_session, ctx, None)

    assert res["facility_id"] is None
    assert len(res["items"]) == 1
    statement, params = mock_session.execute.call_args.args
    assert params == {}
    # The *predicate*, not the column -- `sl.facility_id` is still selected, and should be: an
    # unscoped answer has to tell the client which facility each row belongs to.
    assert "AND sl.facility_id =" not in str(statement)


@pytest.mark.asyncio
async def test_dock_status_and_queue_status_also_serve_every_facility_when_none_is_named():
    """The other two reads #107 named. All three shipped the same `require_facility=True` shape."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_dock_status, get_queue_status
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR997",
        email="admin@setuhaul.com",
        full_name="Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
        facility_id=None,
    )

    docks = MagicMock()
    docks.mappings.return_value.all.return_value = []
    dock_session = AsyncMock()
    dock_session.execute.return_value = docks
    dock_result = await get_dock_status(dock_session, ctx, None)
    assert dock_result["facility_id"] is None
    assert dock_session.execute.call_args.args[1] == {}

    counts = MagicMock()
    counts.scalar_one.return_value = 3
    queue_session = AsyncMock()
    queue_session.execute.return_value = counts
    queue_result = await get_queue_status(queue_session, ctx, None)
    assert queue_result["facility_id"] is None
    assert queue_result["pending_appointments"] == 3
    assert queue_result["open_escalations"] == 3
    # Both counts must be resolved against the same scope decision, not one each.
    assert [call.args[1] for call in queue_session.execute.await_args_list] == [{}, {}]


@pytest.mark.asyncio
async def test_an_operator_is_still_scoped_when_they_name_no_facility():
    """#107 must not over-correct: omission means "all facilities *in scope*", and a facility-scoped
    operator's scope is exactly one facility. Only the global tier gets the unfiltered read."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_queue_status
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )
    counts = MagicMock()
    counts.scalar_one.return_value = 0
    session = AsyncMock()
    session.execute.return_value = counts

    res = await get_queue_status(session, ctx, None)

    assert res["facility_id"] == "FAC-GGN-01"
    assert session.execute.call_args.args[1] == {"facility_id": "FAC-GGN-01"}


@pytest.mark.asyncio
async def test_get_pending_confirmations_scopes_to_own_facility():
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_pending_confirmations
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )
    mock_rows = MagicMock()
    mock_rows.mappings.return_value.all.return_value = [_pending_row()]
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_rows

    res = await get_pending_confirmations(mock_session, ctx, None)

    assert res["facility_id"] == "FAC-GGN-01"
    assert len(res["items"]) == 1
    assert res["items"][0]["appointment_id"] == "APT-1"
    params = mock_session.execute.call_args.args[1]
    assert params["facility_id"] == "FAC-GGN-01"


# ---------------------------------------------------------------------------------------------
# Issue #82 -- get_pending_confirmations orders by section 7.3's composite urgency, not FIFO.
# ---------------------------------------------------------------------------------------------

_PENDING_NOW = datetime(2026, 8, 16, 21, 30, tzinfo=timezone.utc)


def _pending_row(
    appointment_id: str = "APT-1",
    *,
    priority_code: str = "NORMAL",
    queue_state: str | None = None,
    booked_minutes_ago: int = 5,
):
    """One `get_pending_confirmations` row, shaped like the live statement's output.

    `booked_at` is a real `datetime`: `appointments.booked_at` became `timestamptz` in migration
    20260823060000, so asyncpg hands back an aware datetime and the TTL term is arithmetic on it.
    """
    return {
        "appointment_id": appointment_id,
        "shipment_id": f"SHP-{appointment_id}",
        "driver_id": "DRV-RS-01",
        "order_reference": f"ORD-{appointment_id}",
        "facility_id": "FAC-GGN-01",
        "dock_id": "DOCK-GGN-D2",
        "slot_start_ts": "2026-08-16T09:00:00+05:30",
        "slot_end_ts": "2026-08-16T09:30:00+05:30",
        "booked_at": _PENDING_NOW - timedelta(minutes=booked_minutes_ago),
        "priority_code": priority_code,
        "queue_state": queue_state,
    }


async def _pending(rows):
    """Call the read with `now` pinned to `_PENDING_NOW` (section 9.1's injected clock)."""
    from unittest.mock import AsyncMock, MagicMock

    from app.core.clock import FrozenClock
    from app.core.execution_context import ExecutionContext, RoleName
    from app.services.escalation_service import get_pending_confirmations

    ctx = ExecutionContext(
        request_id="r", auth_subject="sub", user_id="USR-OPS-TEST",
        email="ops@setuhaul.com", full_name="Ops User", role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE, facility_id="FAC-GGN-01",
    )
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute.return_value = result
    return await get_pending_confirmations(session, ctx, None, clock=FrozenClock(_PENDING_NOW))


@pytest.mark.asyncio
async def test_pending_confirmations_does_not_bury_a_critical_that_arrived_late():
    """Section 7.3's own worked example, and the reason issue #82 exists.

    The seeded SHP1014 case is a CRITICAL request that entered the queue *after* lower-priority
    ones. Under the FIFO this read shipped with (`ORDER BY booked_at ASC`) it came last; section
    7.3 rejects that ordering by name for exactly this outcome.
    """
    res = await _pending(
        [
            _pending_row("APT-OLD-LOW", priority_code="LOW", booked_minutes_ago=12),
            _pending_row("APT-NEW-CRITICAL", priority_code="CRITICAL", booked_minutes_ago=1),
        ]
    )
    assert [item["appointment_id"] for item in res["items"]] == [
        "APT-NEW-CRITICAL",
        "APT-OLD-LOW",
    ]
    assert res["ordering"]["rule"] == "composite_urgency"


@pytest.mark.asyncio
async def test_pending_confirmations_promotes_a_driver_physically_waiting_at_the_gate():
    """Section 7.3's third term: "a truck burning detention in the yard outranks one still in
    transit". Same two requests otherwise -- only `facility_checkins.queue_state` differs."""
    res = await _pending(
        [
            _pending_row("APT-IN-TRANSIT", queue_state="NOT_QUEUED"),
            _pending_row("APT-WAITING", queue_state="WAITING_LATE"),
        ]
    )
    assert [item["appointment_id"] for item in res["items"]] == [
        "APT-WAITING",
        "APT-IN-TRANSIT",
    ]
    assert res["items"][0]["urgency"]["waiting_bonus"] > 0
    assert res["items"][1]["urgency"]["waiting_bonus"] == 0


@pytest.mark.asyncio
async def test_pending_confirmations_uses_the_shared_ranking_not_a_second_copy():
    """The point of issue #82: one implementation of the policy, not two that can drift.

    Asserts the term-by-term identity against `scheduling/urgency.py` itself rather than against
    re-typed expected numbers -- a test carrying its own copy of the weights would be a third
    implementation and would go on passing if this read forked from the planner queue's.
    """
    from app.scheduling.constraints import load_scheduling_constraints
    from app.scheduling.expiry import DEFAULT_PENDING_TTL_MINUTES
    from app.scheduling.urgency import composite_urgency

    res = await _pending([_pending_row("APT-1", priority_code="HIGH", queue_state="WAITING_EARLY")])
    urgency = res["items"][0]["urgency"]

    # The TTL term is the only clock-dependent one, so it is read back rather than recomputed
    # against a second `now`; every other term must match the shared policy exactly.
    expected = composite_urgency(
        priority_code="HIGH",
        priority_scores=load_scheduling_constraints().ranking_policy.priority_scores,
        ttl_remaining_seconds=0,
        ttl_total_seconds=DEFAULT_PENDING_TTL_MINUTES * 60,
        physically_waiting=True,
    )
    assert urgency["priority_score"] == expected.priority_score
    assert urgency["waiting_bonus"] == expected.waiting_bonus
    assert urgency["score"] == (
        urgency["priority_score"] + urgency["ttl_pressure"] + urgency["waiting_bonus"]
    )


@pytest.mark.asyncio
async def test_pending_confirmations_ties_break_on_appointment_id_not_arrival():
    """Deterministic under equal urgency -- U19 freezes the sort while a row has focus, so two
    polls of an unchanged queue must not reorder it."""
    res = await _pending([_pending_row("APT-B"), _pending_row("APT-A")])
    assert [item["appointment_id"] for item in res["items"]] == ["APT-A", "APT-B"]


@pytest.mark.asyncio
async def test_pending_confirmations_ttl_pressure_lifts_a_row_by_at_most_one_priority_band():
    """Why this is a composite score and not "sort by TTL". Section 7.3 rejects pure TTL ordering
    for the same reason it rejects FIFO, so a fully-burnt NORMAL must not outrank a fresh
    CRITICAL."""
    from app.scheduling.urgency import TTL_PRESSURE_MAX

    res = await _pending(
        [
            _pending_row("APT-EXPIRING-NORMAL", priority_code="NORMAL", booked_minutes_ago=60),
            _pending_row("APT-FRESH-CRITICAL", priority_code="CRITICAL", booked_minutes_ago=0),
        ]
    )
    by_id = {item["appointment_id"]: item for item in res["items"]}
    assert by_id["APT-EXPIRING-NORMAL"]["urgency"]["ttl_pressure"] == TTL_PRESSURE_MAX
    assert by_id["APT-FRESH-CRITICAL"]["urgency"]["ttl_pressure"] == 0
    assert [item["appointment_id"] for item in res["items"]] == [
        "APT-FRESH-CRITICAL",
        "APT-EXPIRING-NORMAL",
    ]


def test_pending_confirmations_keeps_booked_at_as_the_truncation_order():
    """`LIMIT 100` still cuts oldest-first, because `booked_at` is what the D9 deadline derives
    from -- the rows kept are the ones closest to expiring. Only the *display* order changed, so
    the SQL must keep both, and a future edit that "tidies" the ORDER BY away has to fail here."""
    import inspect

    from app.services import escalation_service

    source = inspect.getsource(escalation_service.get_pending_confirmations)
    assert "ORDER BY a.booked_at ASC" in source
    assert "LIMIT 100" in source


@pytest.mark.asyncio
async def test_resolve_escalation_forbids_global_read_only_roles():
    """Issue #10 acceptance: TRANSPORT_MANAGER / REGIONAL_OPERATIONS_HEAD hold only
    *_read_global permissions, so they must be refused on this write even though they sit in
    OPS_PORTAL_ROLES and therefore clear the router-level require_roles gate."""
    from unittest.mock import AsyncMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName
    from app.core.errors import AppError

    for role_id, role in (("ROL006", RoleName.TRANSPORT_MANAGER), ("ROL007", RoleName.REGIONAL_OPERATIONS_HEAD)):
        ctx = ExecutionContext(
            request_id="r",
            auth_subject="sub",
            user_id="USR-RO-TEST",
            email="readonly@setuhaul.com",
            full_name="Read Only",
            role_id=role_id,
            role_name=role,
        )
        mock_session = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await resolve_escalation(mock_session, ctx, "ESC-TEST-99", resolution_note="Should not persist")
        assert exc_info.value.code == "FORBIDDEN", role
        assert exc_info.value.status_code == 403, role
        assert not mock_session.commit.called, f"{role} must not reach a commit"


@pytest.mark.asyncio
async def test_resolve_escalation_still_allows_admin():
    """Guards against over-correcting issue #10 into locking real admins out."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR999",
        email="admin@setuhaul.com",
        full_name="Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
    )
    mock_row = MagicMock()
    mock_row.mappings.return_value.first.return_value = {
        "escalation_id": "ESC-TEST-99",
        "shipment_id": "SHP1006",
        "facility_id": "FAC-ANY-01",  # ADMIN's assert_facility_write_scope bypasses the facility match entirely
        "escalation_type": "NO_FEASIBLE_SLOT",
        "escalation_status": "RESOLVED",
    }
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_row

    res = await resolve_escalation(mock_session, ctx, "ESC-TEST-99", resolution_note="Approved by Admin")

    assert res["escalation_status"] == "RESOLVED"
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_global_read_only_role_keeps_cross_facility_read():
    """The fix must not over-correct: these personas are granted *_read_global, so a
    cross-facility read must still succeed (only their write paths close)."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_pending_confirmations
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-RO-TEST",
        email="readonly@setuhaul.com",
        full_name="Read Only",
        role_id="ROL006",
        role_name=RoleName.TRANSPORT_MANAGER,
    )
    mock_rows = MagicMock()
    mock_rows.mappings.return_value.all.return_value = []
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_rows

    res = await get_pending_confirmations(mock_session, ctx, "FAC-JAI-01")
    assert res["facility_id"] == "FAC-JAI-01"
