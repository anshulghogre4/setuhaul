import pytest
from pydantic import ValidationError

from app.services.escalation_service import EscalateExceptionCommand


def test_escalation_command_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        EscalateExceptionCommand(
            shipment_id="SHP1017",
            escalation_type="NO_SLOT",
            untrusted_override=True,
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
