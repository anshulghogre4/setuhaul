import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.assistant.tools import build_driver_tools
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling import allocation
from app.scheduling.allocation import (
    CancelAppointmentCommand,
    ConfirmAppointmentCommand,
    RequestSlotCommand,
    RescheduleAppointmentCommand,
    allocation_unique_constraint_name,
    appointment_request_status_code,
    cancel_appointment,
    confirm_appointment,
)


class _DbOrig:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _MessageOnlyOrig(Exception):
    """A DBAPI error that exposes only a message -- what the asyncpg dialect really raises."""


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req",
        auth_subject="auth",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
    )


def _ops_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req",
        auth_subject="auth-ops",
        user_id="USR101",
        email="priya.mehta@setuhaul.com",
        full_name="Priya Mehta",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-JAI-01",
    )


def test_request_slot_command_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RequestSlotCommand(note="ok", confirm=True)


def test_request_slot_command_accepts_displayed_policy_version():
    command = RequestSlotCommand(
        note="Please request this option.",
        displayed_policy_version="sprint3_constraints_v1",
        client_message_id="msg-1",
    )

    assert command.displayed_policy_version == "sprint3_constraints_v1"
    assert command.client_message_id == "msg-1"


def test_request_slot_command_accepts_displayed_recommendation_id():
    command = RequestSlotCommand(displayed_recommendation_id="REC-abcdef")

    assert command.displayed_recommendation_id == "REC-abcdef"


def test_reschedule_command_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RescheduleAppointmentCommand(
            appointment_id="APT001", new_slot_id="SLT001", untrusted=True
        )


def test_appointment_request_status_code_marks_pending_confirmation():
    code, requires_confirmation = appointment_request_status_code("PENDING_CONFIRMATION")

    assert code == "APPOINTMENT_PENDING_CONFIRMATION"
    assert requires_confirmation is True


def test_appointment_request_status_code_does_not_confirm_closed_states():
    assert appointment_request_status_code("CONFIRMED") == ("APPOINTMENT_CONFIRMED", False)
    assert appointment_request_status_code("REJECTED") == ("APPOINTMENT_REJECTED", False)
    assert appointment_request_status_code("EXPIRED") == ("APPOINTMENT_EXPIRED", False)
    assert appointment_request_status_code(None) == ("NO_APPOINTMENT_REQUEST", False)


@pytest.mark.parametrize(
    "constraint_name",
    [
        "ux_active_appointment_per_slot",
        "ux_current_active_appointment_per_shipment",
        "dock_occupancy_dock_id_window_excl",
    ],
)
def test_allocation_unique_constraint_name_detects_postgres_allocation_guards(constraint_name):
    exc = IntegrityError("insert appointments", {}, _DbOrig(constraint_name))

    assert allocation_unique_constraint_name(exc) == constraint_name


def test_allocation_unique_constraint_name_reads_exclusion_violation_from_message_only():
    """The production shape, not a convenience fake.

    SQLAlchemy's asyncpg dialect rebuilds its DBAPI error as `IntegrityError("%s: %s" %
    (type(error), error))` and copies sqlstate but not constraint_name, so `exc.orig` carries
    no constraint_name attribute at all and the D1 exclusion violation has to be recognised
    from Postgres' own message wording.
    """
    orig = _MessageOnlyOrig(
        "<class 'asyncpg.exceptions.ExclusionViolationError'>: conflicting key value "
        'violates exclusion constraint "dock_occupancy_dock_id_window_excl"'
    )
    assert not hasattr(orig, "constraint_name")
    exc = IntegrityError("INSERT INTO public.dock_occupancy", {}, orig)

    assert allocation_unique_constraint_name(exc) == "dock_occupancy_dock_id_window_excl"


def test_allocation_unique_constraint_name_ignores_unrelated_integrity_errors():
    exc = IntegrityError("insert appointments", {}, _DbOrig("appointments_pkey"))

    assert allocation_unique_constraint_name(exc) is None


def test_driver_tool_allowlist_includes_request_slot():
    """SOLUTION_DESIGN.md section 7.5.4's driver allowlist, now 12 of 12 (issue #53).

    E3.1 (issue #25) bound 11 and deferred `confirm_held_slot` because the D2 HELD state had no
    schema to live in. Issue #53 gave it one, so the list is complete. Section 7.5.4's own
    justification for the count -- "the honest reason it is not 9: `confirm_held_slot` and
    `explain_slot_eligibility` are new and both are load-bearing" -- is now satisfied by both
    rather than one.

    reschedule_appointment/scheduling_capability_disabled remain gone -- D1 collapses a reschedule
    into cancel_appointment + request_slot, both already on the allowlist, so there is nothing left
    to disable a stub tool for.
    """
    tools = build_driver_tools(session=None, ctx=_driver_ctx(), thread_id="THR-TEST")  # type: ignore[arg-type]
    names = {tool.name for tool in tools}

    assert names == {
        "get_driver_operational_context",
        "list_active_shipments",
        "get_latest_eta",
        "get_current_appointment",
        "report_delay_or_update_eta",
        "find_feasible_slots",
        "request_slot",
        "confirm_held_slot",
        "get_appointment_request_status",
        "explain_slot_eligibility",
        "cancel_appointment",
        "escalate_exception",
    }
    assert "get_conversation_memory" not in names
    assert "reschedule_appointment" not in names
    assert "scheduling_capability_disabled" not in names


@pytest.mark.asyncio
async def test_cancel_appointment_transitions_active_row_and_commits(monkeypatch):
    session = AsyncMock()
    shipment = {
        "shipment_id": "SHP1017",
        "driver_id": "DRV001",
        "destination_facility_id": "FAC-JAI-01",
    }
    current = {
        "appointment_id": "APT020",
        "shipment_id": "SHP1017",
        "slot_id": "SLT020",
        "appointment_status": "CONFIRMED",
        "is_current": 1,
    }
    cancelled = {
        **current,
        "appointment_status": "CANCELLED",
        "is_current": 0,
        "cancellation_reason": "Vehicle breakdown",
    }
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=shipment))
    monkeypatch.setattr(allocation, "_locked_appointment", AsyncMock(return_value=current))
    monkeypatch.setattr(
        allocation,
        "_reread_appointment",
        AsyncMock(side_effect=[cancelled, cancelled]),
    )
    store = AsyncMock()
    monkeypatch.setattr(allocation, "store_idempotency", store)
    # Covered on its own in test_cancel_appointment_releases_the_dock_claim; stubbed here so
    # this test keeps asserting the appointment transition itself.
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    result = await cancel_appointment(
        session,
        _driver_ctx(),
        shipment_id="SHP1017",
        command=CancelAppointmentCommand(
            appointment_id="APT020",
            cancellation_reason="Vehicle breakdown",
        ),
        idempotency_key="cancel-key",
    )

    assert result.code == "APPOINTMENT_CANCELLED"
    assert result.status == "CANCELLED"
    assert result.appointment_writes == 1
    update_params = session.execute.await_args_list[0].args[1]
    assert update_params["appointment_id"] == "APT020"
    assert update_params["cancellation_reason"] == "Vehicle breakdown"
    store.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_appointment_transitions_pending_row_and_commits(monkeypatch):
    session = AsyncMock()
    shipment = {
        "shipment_id": "SHP1002",
        "driver_id": "DRV002",
        "destination_facility_id": "FAC-JAI-01",
    }
    pending = {
        "appointment_id": "APT021",
        "shipment_id": "SHP1002",
        "slot_id": "SLT021",
        "appointment_status": "PENDING_CONFIRMATION",
        "is_current": 1,
    }
    confirmed = {
        **pending,
        "appointment_status": "CONFIRMED",
        "warehouse_confirmation_ref": "WH-JAI-2026-021",
    }
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=shipment))
    monkeypatch.setattr(allocation, "_locked_appointment", AsyncMock(return_value=pending))
    monkeypatch.setattr(
        allocation,
        "_reread_appointment",
        AsyncMock(side_effect=[confirmed, confirmed]),
    )
    store = AsyncMock()
    monkeypatch.setattr(allocation, "store_idempotency", store)
    # Covered on its own in the E5.3 snapshot-guard tests below; stubbed here so this test keeps
    # asserting the confirm transition itself rather than the guard in front of it.
    monkeypatch.setattr(
        allocation,
        "_snapshot_guard",
        AsyncMock(return_value={"snapshot_hash": "hash-after"}),
    )

    result = await confirm_appointment(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        command=ConfirmAppointmentCommand(
            appointment_id="APT021",
            snapshot_hash="hash-the-planner-saw",
            warehouse_confirmation_ref="WH-JAI-2026-021",
        ),
        idempotency_key="confirm-key",
    )

    assert result.code == "APPOINTMENT_CONFIRMED"
    assert result.status == "CONFIRMED"
    # The token the caller should carry into its next write on this row, so a planner acting twice
    # never has to re-read the queue just to obtain a fresh hash.
    assert result.snapshot_hash == "hash-after"
    update_params = session.execute.await_args_list[0].args[1]
    assert update_params["appointment_id"] == "APT021"
    assert update_params["warehouse_confirmation_ref"] == "WH-JAI-2026-021"
    store.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_replay_claim_is_active_requires_current_active_status():
    assert allocation.replay_claim_is_active(
        {"appointment_status": "PENDING_CONFIRMATION", "is_current": 1}
    )
    assert allocation.replay_claim_is_active({"appointment_status": "CONFIRMED", "is_current": 1})
    assert not allocation.replay_claim_is_active(
        {"appointment_status": "CANCELLED", "is_current": 0}
    )
    assert not allocation.replay_claim_is_active(
        {"appointment_status": "CONFIRMED", "is_current": 0}
    )
    assert not allocation.replay_claim_is_active(None)


def test_chat_request_slot_idempotency_key_is_stable_for_same_client_message():
    from app.assistant.tools import chat_mutation_idempotency_key

    first = chat_mutation_idempotency_key(
        thread_id="THR-1",
        action="request-slot",
        parts=["SHP-D16-RAVI", "D16-SLT-1"],
        client_message_id="msg-42",
    )
    second = chat_mutation_idempotency_key(
        thread_id="THR-1",
        action="request-slot",
        parts=["SHP-D16-RAVI", "D16-SLT-1"],
        client_message_id="msg-42",
    )
    third = chat_mutation_idempotency_key(
        thread_id="THR-1",
        action="request-slot",
        parts=["SHP-D16-RAVI", "D16-SLT-1"],
        client_message_id="msg-43",
    )
    assert first == second
    assert first != third
    assert first.endswith("-msg-42")


def test_chat_request_slot_idempotency_key_without_client_message_is_unique():
    from app.assistant.tools import chat_mutation_idempotency_key

    first = chat_mutation_idempotency_key(
        thread_id="THR-1",
        action="request-slot",
        parts=["SHP1", "SLT1"],
        client_message_id=None,
    )
    second = chat_mutation_idempotency_key(
        thread_id="THR-1",
        action="request-slot",
        parts=["SHP1", "SLT1"],
        client_message_id=None,
    )
    assert first != second


@pytest.mark.asyncio
async def test_omitted_recommendation_id_honors_redis_stale_marker(monkeypatch):
    class _Mem:
        def is_recommendation_stale(self, **_kwargs):
            return True

    async def fake_stale(_session, _ctx, **_kwargs):
        return allocation.RequestSlotResult(
            as_of="t",
            status="CONFLICTED",
            code="SLOT_OPTIONS_STALE",
            shipment_id="SHP1",
            slot_id="SLT1",
            policy_version="v1",
            idempotency_key="k",
        )

    monkeypatch.setattr(allocation, "ConversationMemory", lambda _settings: _Mem())
    monkeypatch.setattr(allocation, "get_settings", lambda: object())
    monkeypatch.setattr(allocation, "_stale_recommendation_result", fake_stale)

    result = await allocation._validate_displayed_recommendation(
        AsyncMock(),
        _driver_ctx(),
        shipment_id="SHP1",
        slot_id="SLT1",
        displayed_policy_version=None,
        displayed_recommendation_id=None,
        idempotency_key="k",
    )
    assert result is not None
    assert result.code == "SLOT_OPTIONS_STALE"


@pytest.mark.asyncio
async def test_omitted_recommendation_id_allows_request_when_redis_not_stale(monkeypatch):
    class _Mem:
        def is_recommendation_stale(self, **_kwargs):
            return False

    monkeypatch.setattr(allocation, "ConversationMemory", lambda _settings: _Mem())
    monkeypatch.setattr(allocation, "get_settings", lambda: object())

    result = await allocation._validate_displayed_recommendation(
        AsyncMock(),
        _driver_ctx(),
        shipment_id="SHP1",
        slot_id="SLT1",
        displayed_policy_version=None,
        displayed_recommendation_id=None,
        idempotency_key="k",
    )
    assert result is None


@pytest.mark.asyncio
async def test_reschedule_restores_old_appointment_when_claim_conflicts(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(
            return_value={
                "shipment_id": "SHP1",
                "driver_id": "DRV001",
                "destination_facility_id": "FAC-JAI-01",
            }
        ),
    )
    monkeypatch.setattr(allocation, "_assert_shipment_scope", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(allocation, "_validate_displayed_recommendation", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "find_feasible_slots",
        AsyncMock(return_value=SimpleNamespace(options=[SimpleNamespace(slot_id="SLT-NEW")], policy_version="v1")),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(
            return_value={
                "appointment_id": "APT-OLD",
                "appointment_status": "CONFIRMED",
                "slot_id": "SLT-OLD",
            }
        ),
    )
    conflict = allocation.RequestSlotResult(
        as_of="t",
        status="CONFLICTED",
        code="SLOT_CONFLICT_REFRESH_REQUIRED",
        shipment_id="SHP1",
        slot_id="SLT-NEW",
        policy_version="v1",
        appointment_writes=0,
        idempotency_key="k:claim",
    )
    request_slot_mock = AsyncMock(return_value=conflict)
    monkeypatch.setattr(allocation, "request_slot", request_slot_mock)
    store = AsyncMock()
    monkeypatch.setattr(allocation, "store_idempotency", store)
    # The dock_occupancy release/re-claim pair has its own tests below; stubbed here so this
    # one stays about restoring the old appointment row.
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))
    monkeypatch.setattr(allocation, "_claim_dock_occupancy", AsyncMock(return_value={}))

    from app.scheduling.allocation import reschedule_appointment

    result = await reschedule_appointment(
        session,
        _driver_ctx(),
        shipment_id="SHP1",
        command=RescheduleAppointmentCommand(appointment_id="APT-OLD", new_slot_id="SLT-NEW"),
        idempotency_key="k",
    )

    assert result.code == "SLOT_CONFLICT_REFRESH_REQUIRED"
    request_slot_mock.assert_awaited_once()
    assert request_slot_mock.await_args.kwargs["persist"] is False
    # Matched by content, not position: the statement sequence around this restore now also
    # carries the dock_occupancy release and re-claim, and an index-based assertion silently
    # starts checking a different statement every time one is added.
    statements = [
        (str(call.args[0]), call.args[1] if len(call.args) > 1 else {})
        for call in session.execute.await_args_list
    ]
    restore_params = next(
        params
        for sql, params in statements
        if "UPDATE public.appointments" in sql and params.get("status") == "CONFIRMED"
    )
    assert restore_params["appointment_id"] == "APT-OLD"
    store.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reschedule_releases_then_restores_the_dock_claim(monkeypatch):
    """A failed reschedule must put the D1 claim back, not leave the old appointment active on
    an unclaimed dock interval."""
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(
            return_value={
                "shipment_id": "SHP1",
                "driver_id": "DRV001",
                "destination_facility_id": "FAC-JAI-01",
            }
        ),
    )
    monkeypatch.setattr(allocation, "_assert_shipment_scope", lambda *_a, **_k: None)
    monkeypatch.setattr(allocation, "_validate_displayed_recommendation", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "find_feasible_slots",
        AsyncMock(
            return_value=SimpleNamespace(
                options=[SimpleNamespace(slot_id="SLT-NEW")], policy_version="v1"
            )
        ),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(
            return_value={
                "appointment_id": "APT-OLD",
                "appointment_status": "CONFIRMED",
                "slot_id": "SLT-OLD",
            }
        ),
    )
    release = AsyncMock(return_value=True)
    claim = AsyncMock(return_value={"dock_id": "DOCK-JAI-D1", "window": "[)"})
    monkeypatch.setattr(allocation, "_release_dock_occupancy", release)
    monkeypatch.setattr(allocation, "_claim_dock_occupancy", claim)
    monkeypatch.setattr(
        allocation,
        "request_slot",
        AsyncMock(
            return_value=allocation.RequestSlotResult(
                as_of="t",
                status="CONFLICTED",
                code="SLOT_OPTIONS_STALE",
                shipment_id="SHP1",
                slot_id="SLT-NEW",
                policy_version="v1",
                appointment_writes=0,
                idempotency_key="k:claim",
            )
        ),
    )
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    from app.scheduling.allocation import reschedule_appointment

    result = await reschedule_appointment(
        session,
        _driver_ctx(),
        shipment_id="SHP1",
        command=RescheduleAppointmentCommand(appointment_id="APT-OLD", new_slot_id="SLT-NEW"),
        idempotency_key="k",
    )

    assert result.code == "SLOT_OPTIONS_STALE"
    release.assert_awaited_once_with(session, "APT-OLD")
    claim.assert_awaited_once_with(
        session, appointment_id="APT-OLD", shipment_id="SHP1", slot_id="SLT-OLD"
    )


@pytest.mark.asyncio
async def test_reschedule_does_not_invent_a_claim_it_never_released(monkeypatch):
    """One of E1.1's escalated appointments holds no claim; restoring it must not create one,
    which would fail the exclusion constraint on an interval nobody owned."""
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(
            return_value={
                "shipment_id": "SHP1",
                "driver_id": "DRV001",
                "destination_facility_id": "FAC-JAI-01",
            }
        ),
    )
    monkeypatch.setattr(allocation, "_assert_shipment_scope", lambda *_a, **_k: None)
    monkeypatch.setattr(allocation, "_validate_displayed_recommendation", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "find_feasible_slots",
        AsyncMock(
            return_value=SimpleNamespace(
                options=[SimpleNamespace(slot_id="SLT-NEW")], policy_version="v1"
            )
        ),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(
            return_value={
                "appointment_id": "APT-OLD",
                "appointment_status": "CONFIRMED",
                "slot_id": "SLT-OLD",
            }
        ),
    )
    claim = AsyncMock()
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=False))
    monkeypatch.setattr(allocation, "_claim_dock_occupancy", claim)
    monkeypatch.setattr(
        allocation,
        "request_slot",
        AsyncMock(
            return_value=allocation.RequestSlotResult(
                as_of="t",
                status="CONFLICTED",
                code="SLOT_OPTIONS_STALE",
                shipment_id="SHP1",
                slot_id="SLT-NEW",
                policy_version="v1",
                appointment_writes=0,
                idempotency_key="k:claim",
            )
        ),
    )
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    from app.scheduling.allocation import reschedule_appointment

    await reschedule_appointment(
        session,
        _driver_ctx(),
        shipment_id="SHP1",
        command=RescheduleAppointmentCommand(appointment_id="APT-OLD", new_slot_id="SLT-NEW"),
        idempotency_key="k",
    )

    claim.assert_not_awaited()


D1_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20260823060000_d1_correctness_bedrock.sql"
)


def _sql_fingerprint(sql: str) -> str:
    """Whitespace- and alias-insensitive form, so the same expression written across several
    lines with a different table alias still compares equal."""
    return re.sub(r"\b(?:r|s|sl)\.", "", re.sub(r"\s+", "", sql))


async def _captured_claim_sql() -> tuple[str, dict]:
    session = AsyncMock()
    # execute() is awaited, but the Result it resolves to is synchronous -- an AsyncMock child
    # would hand back a coroutine from .mappings().
    session.execute.return_value = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = {
        "dock_id": "DOCK-JAI-D1",
        "window": "[2026-08-16 13:30+00,2026-08-16 14:10+00)",
    }
    claim = await allocation._claim_dock_occupancy(
        session, appointment_id="APT-NEW", shipment_id="SHP1", slot_id="SLT1"
    )
    assert claim == {
        "dock_id": "DOCK-JAI-D1",
        "window": "[2026-08-16 13:30+00,2026-08-16 14:10+00)",
    }
    call = session.execute.await_args
    return str(call.args[0]), call.args[1]


@pytest.mark.asyncio
async def test_claim_dock_occupancy_writes_the_exclusion_constrained_row():
    sql, params = await _captured_claim_sql()

    assert "INSERT INTO public.dock_occupancy" in sql
    assert 'RETURNING dock_id, "window"' in sql
    # Idempotent per appointment so the reschedule restore can re-claim blindly, without
    # weakening the race between two different appointment ids.
    assert "NOT EXISTS" in sql
    assert params == {
        "appointment_id": "APT-NEW",
        "shipment_id": "SHP1",
        "slot_id": "SLT1",
    }


@pytest.mark.asyncio
async def test_claim_window_matches_the_e11_backfill_expression_exactly():
    """Drift guard. If the booking path and the E1.1 backfill ever compute the window
    differently, backfilled rows and newly claimed rows stop meaning the same thing by
    'occupied' -- and nothing else in the system would notice.
    """
    sql, _ = await _captured_claim_sql()
    migration_line = next(
        line
        for line in D1_MIGRATION.read_text(encoding="utf-8").splitlines()
        if "computed_window :=" in line
    )
    backfill_expression = migration_line.split(":=", 1)[1].strip().rstrip(";")

    assert "tstzrange(" in backfill_expression
    assert _sql_fingerprint(backfill_expression) in _sql_fingerprint(sql)


@pytest.mark.asyncio
async def test_release_dock_occupancy_reports_whether_a_claim_existed():
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.first.return_value = (76,)

    assert await allocation._release_dock_occupancy(session, "APT-OLD") is True
    sql, params = str(session.execute.await_args.args[0]), session.execute.await_args.args[1]
    assert "DELETE FROM public.dock_occupancy" in sql
    assert "RETURNING occupancy_id" in sql
    assert params == {"appointment_id": "APT-OLD"}

    session.execute.return_value.first.return_value = None
    assert await allocation._release_dock_occupancy(session, "APT-NO-CLAIM") is False


@pytest.mark.asyncio
async def test_cancel_appointment_releases_the_dock_claim(monkeypatch):
    """Without this the cancelled appointment's interval stays claimed forever and every
    later booking on it loses the race to a row nobody owns."""
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(
            return_value={
                "shipment_id": "SHP1017",
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
                "appointment_id": "APT020",
                "shipment_id": "SHP1017",
                "slot_id": "SLT020",
                "appointment_status": "CONFIRMED",
                "is_current": 1,
            }
        ),
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())
    release = AsyncMock(return_value=True)
    monkeypatch.setattr(allocation, "_release_dock_occupancy", release)

    await cancel_appointment(
        session,
        _driver_ctx(),
        shipment_id="SHP1017",
        command=CancelAppointmentCommand(
            appointment_id="APT020", cancellation_reason="Vehicle breakdown"
        ),
        idempotency_key="cancel-key",
    )

    release.assert_awaited_once_with(session, "APT020")


@pytest.mark.asyncio
@pytest.mark.parametrize("target_status", ["REJECTED", "EXPIRED"])
async def test_ops_pending_transition_releases_the_dock_claim(monkeypatch, target_status):
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(
            return_value={
                "shipment_id": "SHP1002",
                "driver_id": "DRV002",
                "destination_facility_id": "FAC-JAI-01",
            }
        ),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(
            return_value={
                "appointment_id": "APT021",
                "shipment_id": "SHP1002",
                "slot_id": "SLT021",
                "appointment_status": "PENDING_CONFIRMATION",
                "is_current": 1,
            }
        ),
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())
    release = AsyncMock(return_value=True)
    monkeypatch.setattr(allocation, "_release_dock_occupancy", release)

    await allocation._ops_pending_transition(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        appointment_id="APT021",
        target_status=target_status,
        reason="Dock unavailable",
        action_type=allocation.AUDIT_ACTION_REJECT_APPOINTMENT,
        idempotency_key="ops-key",
    )

    release.assert_awaited_once_with(session, "APT021")


# --- E1.1 bind-type regression guard ---------------------------------------------------------
# Why this exists: E1.1 converted six tables' timestamp columns from `text` to `timestamptz`, and
# asyncpg 0.31.0 encodes a timestamptz parameter with its datetime codec only -- a `str` raises
# `DataError: invalid input for query argument $1 ... (expected a datetime.date or
# datetime.datetime instance, got 'str')`. Every write path in this module bound `.isoformat()`
# strings, so every real appointment transition 500'd in production from the moment the migration
# landed, and the whole mock-based suite still passed because a MagicMock session never encodes a
# parameter. These tests close exactly that blind spot.
#
# The converted-column set is parsed out of the migration rather than hardcoded, so a later
# migration that converts another column makes this guard cover it automatically instead of going
# quietly out of date.


def _converted_columns_from_migration() -> dict[str, set[str]]:
    """{table: {column, ...}} for every `text` -> `timestamptz` conversion E1.1 performed."""
    sql = D1_MIGRATION.read_text(encoding="utf-8")
    converted: dict[str, set[str]] = {}
    for table, body in re.findall(
        r"ALTER TABLE public\.(\w+)\s+((?:\s*ALTER COLUMN[^;]*?));", sql, re.IGNORECASE
    ):
        cols = set(re.findall(r"ALTER COLUMN (\w+) TYPE timestamptz", body, re.IGNORECASE))
        if cols:
            converted.setdefault(table, set()).update(cols)
    return converted


def test_migration_parse_finds_the_six_converted_tables():
    """Guards the guard: if the parse silently matched nothing, the assertions below would pass
    vacuously and the regression they exist to catch would sail straight through."""
    converted = _converted_columns_from_migration()

    assert set(converted) == {
        "appointment_slots",
        "appointments",
        "shipments",
        "dock_status_events",
        "eta_updates",
        "facility_checkins",
    }
    assert converted["appointments"] == {
        "booked_at",
        "confirmed_at",
        "cancelled_at",
        "updated_at",
    }


def _assert_timestamp_binds_are_correctly_typed(session) -> int:
    """Every bind into a converted column must be a datetime; audit_logs.created_at must stay str.

    Returns how many binds were actually checked so a caller can refuse to pass on zero.
    """
    from datetime import datetime

    converted = _converted_columns_from_migration()
    checked = 0
    for call in session.execute.await_args_list:
        if len(call.args) < 2 or not isinstance(call.args[1], dict):
            continue
        sql, params = str(call.args[0]), call.args[1]
        for table, columns in converted.items():
            if f"public.{table}" not in sql:
                continue
            for column in columns:
                # Only when the statement really assigns/inserts that column via a bind of the
                # same name -- these paths name their parameters after their columns.
                if column in params and re.search(rf"\b{column}\b", sql):
                    assert isinstance(params[column], datetime), (
                        f"{table}.{column} is timestamptz after E1.1 but was bound as "
                        f"{type(params[column]).__name__}; asyncpg would raise DataError."
                    )
                    checked += 1
        if "public.audit_logs" in sql and "created_at" in params:
            assert isinstance(params["created_at"], str), (
                "audit_logs.created_at was deliberately NOT converted by E1.1 and must stay a "
                "string bind; a datetime raises the mirror-image asyncpg DataError."
            )
            checked += 1
    return checked


@pytest.mark.asyncio
async def test_cancel_appointment_binds_datetimes_not_iso_strings(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(return_value={"shipment_id": "SHP1017", "driver_id": "DRV001",
                                "destination_facility_id": "FAC-JAI-01"}),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(return_value={"appointment_id": "APT020", "shipment_id": "SHP1017",
                                "slot_id": "SLT020", "appointment_status": "CONFIRMED",
                                "is_current": 1}),
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    await cancel_appointment(
        session,
        _driver_ctx(),
        shipment_id="SHP1017",
        command=CancelAppointmentCommand(
            appointment_id="APT020", cancellation_reason="Vehicle breakdown"
        ),
        idempotency_key="cancel-bind-key",
    )

    # cancelled_at + updated_at (timestamptz) and audit_logs.created_at (text).
    assert _assert_timestamp_binds_are_correctly_typed(session) == 3


@pytest.mark.asyncio
async def test_confirm_appointment_binds_datetimes_not_iso_strings(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(return_value={"shipment_id": "SHP1002", "driver_id": "DRV002",
                                "destination_facility_id": "FAC-JAI-01"}),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(return_value={"appointment_id": "APT021", "shipment_id": "SHP1002",
                                "slot_id": "SLT021",
                                "appointment_status": "PENDING_CONFIRMATION", "is_current": 1}),
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())
    monkeypatch.setattr(
        allocation, "_snapshot_guard", AsyncMock(return_value={"snapshot_hash": "h"})
    )

    await confirm_appointment(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        command=ConfirmAppointmentCommand(
            appointment_id="APT021",
            snapshot_hash="h-seen",
            warehouse_confirmation_ref="WH-JAI-2026-021",
        ),
        idempotency_key="confirm-bind-key",
    )

    # confirmed_at + updated_at (timestamptz) and audit_logs.created_at (text).
    assert _assert_timestamp_binds_are_correctly_typed(session) == 3


@pytest.mark.asyncio
async def test_ops_pending_transition_binds_datetimes_not_iso_strings(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(return_value={"shipment_id": "SHP1002", "driver_id": "DRV002",
                                "destination_facility_id": "FAC-JAI-01"}),
    )
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(return_value={"appointment_id": "APT021", "shipment_id": "SHP1002",
                                "slot_id": "SLT021",
                                "appointment_status": "PENDING_CONFIRMATION", "is_current": 1}),
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))

    await allocation._ops_pending_transition(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        appointment_id="APT021",
        target_status="REJECTED",
        reason="Dock unavailable",
        action_type=allocation.AUDIT_ACTION_REJECT_APPOINTMENT,
        idempotency_key="ops-bind-key",
    )

    # updated_at (timestamptz) and audit_logs.created_at (text).
    assert _assert_timestamp_binds_are_correctly_typed(session) == 2

