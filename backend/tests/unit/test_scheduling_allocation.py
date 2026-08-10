import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.assistant.tools import build_driver_tools
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.allocation import (
    RequestSlotCommand,
    allocation_unique_constraint_name,
    appointment_request_status_code,
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


def test_appointment_request_status_code_marks_pending_confirmation():
    code, requires_confirmation = appointment_request_status_code("PENDING_CONFIRMATION")

    assert code == "APPOINTMENT_PENDING_CONFIRMATION"
    assert requires_confirmation is True


def test_appointment_request_status_code_does_not_confirm_closed_states():
    assert appointment_request_status_code("CONFIRMED") == ("APPOINTMENT_CONFIRMED", False)
    assert appointment_request_status_code("REJECTED") == ("APPOINTMENT_REJECTED", False)
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

    assert "find_feasible_slots" in names
    assert "request_slot" in names
    assert "get_appointment_request_status" in names
    assert "scheduling_capability_disabled" in names
