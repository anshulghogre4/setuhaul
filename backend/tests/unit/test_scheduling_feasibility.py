from datetime import datetime

from app.assistant.tools import build_driver_tools
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.feasibility import evaluate_candidate_slot


def _shipment(**overrides):
    data = {
        "shipment_id": "SHP1017",
        "priority_code": "NORMAL",
        "original_eta_ts": "2026-08-04T11:30:00+05:30",
        "required_dock_type": "STANDARD",
        "temperature_control_required": 0,
        "load_weight_kg": 11500,
        "expected_unload_min": 50,
    }
    data.update(overrides)
    return data


def _facility(**overrides):
    data = {
        "facility_id": "FAC-JAI-01",
        "timezone": "Asia/Kolkata",
        "open_time": "06:00",
        "close_time": "22:00",
    }
    data.update(overrides)
    return data


def _candidate(**overrides):
    data = {
        "slot_id": "SLOT-JAI-019",
        "facility_id": "FAC-JAI-01",
        "dock_id": "DOCK-JAI-D2",
        "dock_code": "D2",
        "dock_type": "STANDARD",
        "supports_refrigerated": 0,
        "max_vehicle_weight_kg": 25000,
        "dock_status": "ACTIVE",
        "slot_start_ts": "2026-08-04T12:00:00+05:30",
        "slot_end_ts": "2026-08-04T13:00:00+05:30",
        "slot_status": "OPEN",
        "active_appointment_id": None,
        "active_dock_event_id": None,
    }
    data.update(overrides)
    return data


def test_candidate_slot_is_feasible_when_eta_and_dock_rules_fit():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(),
        checked_constraints=["slot_capacity_available"],
    )

    assert reason is None
    assert option is not None
    assert option.option_status == "DISPLAYED_NOT_RESERVED"
    assert option.feasible_end_ts == "2026-08-04T12:55:00+05:30"
    assert option.rank_score > 0
    assert option.ranking_factors["priority_code"] == "NORMAL"
    assert option.ranking_factors["lateness_minutes"] == 35
    assert option.ranking_factors["wait_after_eta_minutes"] == 0


def test_candidate_slot_rejects_stale_eta_that_cannot_unload_inside_window():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=70),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:10:00+05:30"),
        candidate=_candidate(),
        checked_constraints=[],
    )

    assert option is None
    assert reason is not None
    assert reason.failure_code == "ETA_AFTER_SLOT_WINDOW"


def test_candidate_slot_rejects_active_slot_occupancy():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:00:00+05:30"),
        candidate=_candidate(active_appointment_id="APT1001"),
        checked_constraints=[],
    )

    assert option is None
    assert reason is not None
    assert reason.failure_code == "SLOT_CAPACITY_UNAVAILABLE"


def test_candidate_slot_rejects_incompatible_reefer_requirement():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(required_dock_type="REEFER", temperature_control_required=1),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:00:00+05:30"),
        candidate=_candidate(),
        checked_constraints=[],
    )

    assert option is None
    assert reason is not None
    assert reason.failure_code in {"DOCK_INCOMPATIBLE_VEHICLE", "DOCK_INCOMPATIBLE_LOAD"}


def test_candidate_slot_score_penalizes_wait_after_eta():
    early, early_reason = evaluate_candidate_slot(
        shipment=_shipment(priority_code="HIGH"),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:00:00+05:30"),
        candidate=_candidate(slot_id="SLOT-EARLY", slot_start_ts="2026-08-04T12:00:00+05:30"),
        checked_constraints=[],
    )
    late, late_reason = evaluate_candidate_slot(
        shipment=_shipment(priority_code="HIGH"),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:00:00+05:30"),
        candidate=_candidate(
            slot_id="SLOT-LATE",
            slot_start_ts="2026-08-04T13:00:00+05:30",
            slot_end_ts="2026-08-04T14:00:00+05:30",
        ),
        checked_constraints=[],
    )

    assert early_reason is None
    assert late_reason is None
    assert early is not None
    assert late is not None
    assert early.rank_score > late.rank_score
    assert late.ranking_factors["wait_after_eta_minutes"] == 60


def test_driver_tool_allowlist_includes_feasible_slot_search():
    ctx = ExecutionContext(
        request_id="req",
        auth_subject="auth",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
    )

    tools = build_driver_tools(session=None, ctx=ctx, thread_id="THR-TEST")  # type: ignore[arg-type]
    names = {tool.name for tool in tools}

    assert "find_feasible_slots" in names
