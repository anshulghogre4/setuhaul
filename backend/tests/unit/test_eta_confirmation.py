from app.services.eta_service import (
    ALLOWED_EXCEPTION_TYPES,
    AUDIT_ACTION_UPDATE_ETA,
    EtaUpdateCommand,
    confirmation_preview,
    format_eta_display,
)
from app.services.idempotency import payload_hash


def test_audit_action_type_matches_baseline_check():
    # Baseline CHECK allows UPDATE_ETA, not synonyms like ETA_UPDATE.
    assert AUDIT_ACTION_UPDATE_ETA == "UPDATE_ETA"


def test_default_exception_type_is_allowed():
    cmd = EtaUpdateCommand(declared_eta_ts="2026-08-07T21:00:00+05:30")
    assert cmd.exception_type in ALLOWED_EXCEPTION_TYPES
    assert "LATE_ETA" not in ALLOWED_EXCEPTION_TYPES


def test_repair_duration_is_not_treated_as_eta_in_preview():
    cmd = EtaUpdateCommand(
        declared_eta_ts="2026-08-07T20:30:00+05:30",
        repair_duration_min=45,
        confirmed=False,
    )
    preview = confirmation_preview(cmd)
    assert preview["status"] == "CONFIRMATION_REQUIRED"
    assert preview["repair_duration_min"] == 45
    assert "Repair duration is not an ETA" in preview["note"]


def test_format_eta_display_includes_timezone():
    text = format_eta_display("2026-08-07T20:30:00+05:30")
    assert "2026-08-07" in text
    assert "Asia/Kolkata" in text


def test_payload_hash_stable():
    a = payload_hash({"b": 1, "a": 2})
    b = payload_hash({"a": 2, "b": 1})
    assert a == b
    assert a != payload_hash({"a": 2, "b": 3})


def test_confirmation_required_without_confirmed_flag():
    cmd = EtaUpdateCommand(declared_eta_ts="2026-08-07T21:00:00+05:30", confirmed=False)
    preview = confirmation_preview(cmd)
    assert preview["requires_confirmation"] is True
    assert preview["declared_eta_ts"] == "2026-08-07T21:00:00+05:30"
