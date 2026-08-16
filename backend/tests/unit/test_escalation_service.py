import pytest
from pydantic import ValidationError

from app.services.escalation_service import EscalateExceptionCommand


def test_escalation_command_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        EscalateExceptionCommand(  # type: ignore[call-arg]
            shipment_id="SHP1017",
            escalation_type="NO_SLOT",
            untrusted_override=True,  # type: ignore[call-arg]
        )


def test_escalation_command_accepts_versioned_recommendation_payload():
    command = EscalateExceptionCommand(
        shipment_id="SHP1017",
        escalation_type="NO_SLOT",
        policy_version="sprint3_constraints_v1",
        recommendation_id="REC-123",
        payload={"blocking_reasons": [{"failure_code": "NO_CANDIDATE_SLOTS"}]},
    )

    assert command.escalation_type == "NO_SLOT"
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
        "escalation_type": "NO_SLOT",
        "escalation_status": "RESOLVED",
    }

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_row

    res = await resolve_escalation(mock_session, ctx, "ESC-TEST-99", resolution_note="Approved by Ops Admin")

    assert res["escalation_id"] == "ESC-TEST-99"
    assert res["escalation_status"] == "RESOLVED"
    assert mock_session.commit.called
