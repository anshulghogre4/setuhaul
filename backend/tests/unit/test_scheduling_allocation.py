from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    ["ux_active_appointment_per_slot", "ux_current_active_appointment_per_shipment"],
)
def test_allocation_unique_constraint_name_detects_postgres_allocation_guards(constraint_name):
    exc = IntegrityError("insert appointments", {}, _DbOrig(constraint_name))

    assert allocation_unique_constraint_name(exc) == constraint_name


def test_allocation_unique_constraint_name_ignores_unrelated_integrity_errors():
    exc = IntegrityError("insert appointments", {}, _DbOrig("appointments_pkey"))

    assert allocation_unique_constraint_name(exc) is None


def test_driver_tool_allowlist_includes_request_slot():
    tools = build_driver_tools(session=None, ctx=_driver_ctx(), thread_id="THR-TEST")  # type: ignore[arg-type]
    names = {tool.name for tool in tools}

    assert "get_conversation_memory" in names
    assert "find_feasible_slots" in names
    assert "request_slot" in names
    assert "get_appointment_request_status" in names
    assert "cancel_appointment" in names
    assert "reschedule_appointment" in names
    assert "escalate_exception" in names
    assert "scheduling_capability_disabled" in names


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

    result = await confirm_appointment(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        command=ConfirmAppointmentCommand(
            appointment_id="APT021",
            warehouse_confirmation_ref="WH-JAI-2026-021",
        ),
        idempotency_key="confirm-key",
    )

    assert result.code == "APPOINTMENT_CONFIRMED"
    assert result.status == "CONFIRMED"
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
    monkeypatch.setattr(allocation, "_assert_read_scope", lambda *_args, **_kwargs: None)
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
    restore_params = session.execute.await_args_list[1].args[1]
    assert restore_params["appointment_id"] == "APT-OLD"
    assert restore_params["status"] == "CONFIRMED"
    store.assert_awaited_once()
    session.commit.assert_awaited_once()

