from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.assistant.tools import build_driver_tools
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.feasibility import (
    OUTCOME_FEASIBLE,
    OUTCOME_NO_FEASIBLE_SLOT,
    OUTCOME_NO_SAME_DAY_SLOT,
    active_facility_rules,
    derive_outcome,
    evaluate_candidate_slot,
    explain_slot_eligibility,
    recommendation_id_for,
)


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


def _rule(rule_id: str, rule_type: str, rule_value: str, **overrides):
    data = {
        "rule_id": rule_id,
        "rule_type": rule_type,
        "rule_value": rule_value,
        "effective_from": "2026-01-01",
        "effective_to": None,
    }
    data.update(overrides)
    return data


# --- SOLUTION_DESIGN.md section 5 Stage 1: facility rules with time-bounded effectivity ---


def test_facility_rule_last_new_start_time_rejects_a_late_unload_start():
    # RULE005 at FAC-JAI-01: no new unload may start after 21:00 local. The 25-minute unload
    # fits inside the 21:00-22:00 window, so only the rule can reject this.
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=25),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T21:15:00+05:30"),
        candidate=_candidate(
            slot_start_ts="2026-08-04T21:00:00+05:30",
            slot_end_ts="2026-08-04T22:00:00+05:30",
        ),
        checked_constraints=[],
        facility_rules=[_rule("RULE005", "LAST_NEW_START_TIME", "21:00")],
    )

    assert option is None
    assert reason is not None
    assert reason.failure_code == "FACILITY_RULE_VIOLATION"
    assert "RULE005" in reason.message


def test_facility_rule_last_new_start_time_permits_a_start_exactly_at_the_cutoff():
    # "should start after 21:00" is read strictly: 21:00 itself is still allowed.
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=30),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T20:30:00+05:30"),
        candidate=_candidate(
            slot_start_ts="2026-08-04T21:00:00+05:30",
            slot_end_ts="2026-08-04T22:00:00+05:30",
        ),
        checked_constraints=[],
        facility_rules=[_rule("RULE005", "LAST_NEW_START_TIME", "21:00")],
    )

    assert reason is None
    assert option is not None


def test_facility_rule_outside_its_effectivity_window_is_not_applied():
    expired = _rule(
        "RULE005",
        "LAST_NEW_START_TIME",
        "21:00",
        effective_from="2026-01-01",
        effective_to="2026-06-01",
    )
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=25),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T21:15:00+05:30"),
        candidate=_candidate(
            slot_start_ts="2026-08-04T21:00:00+05:30",
            slot_end_ts="2026-08-04T22:00:00+05:30",
        ),
        checked_constraints=[],
        facility_rules=[expired],
    )

    assert reason is None
    assert option is not None


def test_facility_rule_absence_is_permission_not_inheritance():
    # FAC-GGN-01 defines no LAST_NEW_START_TIME and must never inherit Jaipur's.
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=25),
        facility=_facility(facility_id="FAC-GGN-01"),
        eta_dt=datetime.fromisoformat("2026-08-04T21:15:00+05:30"),
        candidate=_candidate(
            slot_start_ts="2026-08-04T21:00:00+05:30",
            slot_end_ts="2026-08-04T22:00:00+05:30",
        ),
        checked_constraints=[],
        facility_rules=[_rule("RULE006", "NO_SHOW_GRACE_MIN", "20")],
    )

    assert reason is None
    assert option is not None


def test_facility_rule_heavy_dock_routes_an_over_threshold_load_away_from_a_standard_dock():
    # RULE004: loads above 25,000 kg must use the heavy dock. The candidate dock here rates
    # 40,000 kg, so the existing max_vehicle_weight_kg check alone would pass it.
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(load_weight_kg=26000, required_dock_type="ANY"),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:00:00+05:30"),
        candidate=_candidate(dock_type="STANDARD", max_vehicle_weight_kg=40000),
        checked_constraints=[],
        facility_rules=[_rule("RULE004", "HEAVY_DOCK_REQUIRED_KG", "25000")],
    )

    assert option is None
    assert reason is not None
    assert reason.failure_code == "FACILITY_RULE_VIOLATION"
    assert "RULE004" in reason.message


def test_facility_rule_reefer_dock_required_names_the_rule_that_blocked_it():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(required_dock_type="ANY", temperature_control_required=1),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:00:00+05:30"),
        candidate=_candidate(supports_refrigerated=0),
        checked_constraints=[],
        facility_rules=[_rule("RULE003", "REEFER_DOCK_REQUIRED", "TRUE")],
    )

    assert option is None
    assert reason is not None
    # The pre-existing physical-compatibility invariant fires first; the point of this test
    # is that a reefer load on a dry dock is never offered, by either path.
    assert reason.failure_code in {"DOCK_INCOMPATIBLE_LOAD", "FACILITY_RULE_VIOLATION"}


def test_unknown_facility_rule_type_is_ignored_rather_than_guessed_at():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(),
        checked_constraints=[],
        facility_rules=[_rule("RULE001", "CHECKIN_EARLY_LIMIT_MIN", "60")],
    )

    assert reason is None
    assert option is not None


def test_active_facility_rules_reads_a_bare_date_as_facility_local_midnight():
    rules = [_rule("R1", "LAST_NEW_START_TIME", "21:00", effective_from="2026-08-05")]
    before = active_facility_rules(
        rules,
        at=datetime.fromisoformat("2026-08-04T23:30:00+05:30"),
        tz_name="Asia/Kolkata",
    )
    on_the_day = active_facility_rules(
        rules,
        at=datetime.fromisoformat("2026-08-05T00:30:00+05:30"),
        tz_name="Asia/Kolkata",
    )

    assert before == []
    assert len(on_the_day) == 1


# --- SOLUTION_DESIGN.md section 5 Stage 1: the driver's own constraints, both ends ---


def test_driver_latest_acceptable_ts_rejects_an_interval_that_finishes_too_late():
    # EXC002-shaped: "I must leave before 13:30".
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(),
        checked_constraints=[],
        driver_window={"latest_acceptable_ts": "2026-08-04T12:30:00+05:30"},
    )

    assert option is None
    assert reason is not None
    assert reason.failure_code == "DRIVER_WINDOW_VIOLATION"


def test_driver_earliest_acceptable_ts_rejects_an_interval_before_the_driver_can_arrive():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(),
        checked_constraints=[],
        driver_window={"earliest_acceptable_ts": "2026-08-04T12:45:00+05:30"},
    )

    assert option is None
    assert reason is not None
    assert reason.failure_code == "DRIVER_WINDOW_VIOLATION"


def test_driver_window_with_no_stated_bounds_does_not_reject():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(),
        checked_constraints=[],
        driver_window={"earliest_acceptable_ts": None, "latest_acceptable_ts": None},
    )

    assert reason is None
    assert option is not None


# --- SOLUTION_DESIGN.md section 5 Stage 0: multi-day horizon and the outcome split ---


def test_option_carries_the_facility_local_date_not_the_offset_date():
    # The engine returns offset-bearing ISO timestamps (live rows come back as +00:00), and
    # their date component is not always the facility-local calendar date. Shown here with a
    # UTC+12 facility, where 2026-08-04T19:00:00+00:00 is already 2026-08-05 locally.
    # Rendering the ISO date instead of slot_local_date would put a driver at the dock a day
    # early -- the exact wrong-day hazard section 5 Stage 0 calls out.
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=25, original_eta_ts="2026-08-04T19:00:00+00:00"),
        facility=_facility(timezone="Pacific/Auckland"),
        eta_dt=datetime.fromisoformat("2026-08-04T19:00:00+00:00"),
        candidate=_candidate(
            slot_start_ts="2026-08-04T19:00:00+00:00",
            slot_end_ts="2026-08-04T20:00:00+00:00",
        ),
        checked_constraints=[],
    )

    assert reason is None
    assert option is not None
    assert option.slot_start_ts.startswith("2026-08-04")
    assert option.slot_local_date == "2026-08-05"
    assert option.is_same_day is True


def test_option_on_a_later_local_day_than_the_eta_is_not_same_day():
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=25),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T21:30:00+05:30"),
        candidate=_candidate(
            slot_start_ts="2026-08-05T06:00:00+05:30",
            slot_end_ts="2026-08-05T07:00:00+05:30",
        ),
        checked_constraints=[],
    )

    assert reason is None
    assert option is not None
    assert option.slot_local_date == "2026-08-05"
    assert option.is_same_day is False


def test_stage0_outcome_split_only_escalates_when_the_whole_horizon_is_exhausted():
    same_day, _ = evaluate_candidate_slot(
        shipment=_shipment(),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(),
        checked_constraints=[],
    )
    next_day, _ = evaluate_candidate_slot(
        shipment=_shipment(expected_unload_min=25),
        facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T21:30:00+05:30"),
        candidate=_candidate(
            slot_id="SLOT-NEXT-DAY",
            slot_start_ts="2026-08-05T06:00:00+05:30",
            slot_end_ts="2026-08-05T07:00:00+05:30",
        ),
        checked_constraints=[],
    )
    assert same_day is not None
    assert next_day is not None

    assert derive_outcome([]) == OUTCOME_NO_FEASIBLE_SLOT
    assert derive_outcome([next_day]) == OUTCOME_NO_SAME_DAY_SLOT
    assert derive_outcome([same_day, next_day]) == OUTCOME_FEASIBLE


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


def test_recommendation_id_is_stable_and_uses_noslot_marker():
    first = recommendation_id_for(
        shipment_id="SHP1017",
        policy_version="sprint3_constraints_v1",
        effective_eta_ts="2026-08-04T12:00:00+05:30",
        option_slot_ids=["SLT-A", "SLT-B"],
    )
    assert first == recommendation_id_for(
        shipment_id="SHP1017",
        policy_version="sprint3_constraints_v1",
        effective_eta_ts="2026-08-04T12:00:00+05:30",
        option_slot_ids=["SLT-A", "SLT-B"],
    )
    assert first.startswith("REC-")
    assert len(first) == 28
    assert recommendation_id_for(
        shipment_id="SHP1017",
        policy_version="sprint3_constraints_v1",
        effective_eta_ts="2026-08-04T12:00:00+05:30",
        option_slot_ids=[],
    ) != first


# --------------------------------------------------------------------------------------
# E3.1 (issue #25) -- explain_slot_eligibility, FR-DRV-006
# --------------------------------------------------------------------------------------


def _driver_ctx(**overrides) -> ExecutionContext:
    data = {
        "request_id": "r",
        "auth_subject": "sub",
        "user_id": "USR201",
        "email": "driver@setuhaul.com",
        "full_name": "Test Driver",
        "role_id": "ROL001",
        "role_name": RoleName.DRIVER,
        "driver_id": "DRV001",
    }
    data.update(overrides)
    return ExecutionContext(**data)


def _mock_result(row: dict | None):
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    return result


def _eligibility_session(*, shipment_row: dict, candidate_row: dict | None, facility_row: dict | None):
    """Mocks the three sequential session.execute calls explain_slot_eligibility makes:
    shipment, candidate slot, facility -- in that order (matches the function's own body)."""
    session = AsyncMock()
    calls = [_mock_result(shipment_row)]
    if candidate_row is not None:
        calls.append(_mock_result(candidate_row))
        calls.append(_mock_result(facility_row))
    else:
        calls.append(_mock_result(None))
    session.execute = AsyncMock(side_effect=calls)
    return session


@pytest.mark.asyncio
async def test_explain_slot_eligibility_reports_eligible_with_the_same_explanation_shape():
    shipment_row = _shipment(
        driver_id="DRV001",
        destination_facility_id="FAC-JAI-01",
        effective_eta_ts="2026-08-04T11:30:00+05:30",
        driver_earliest_acceptable_ts=None,
        driver_latest_acceptable_ts=None,
    )
    candidate_row = _candidate()
    facility_row = {**_facility(), "active_flag": 1, "facility_rules_json": "[]"}
    session = _eligibility_session(
        shipment_row=shipment_row, candidate_row=candidate_row, facility_row=facility_row
    )

    result = await explain_slot_eligibility(session, _driver_ctx(), "SHP1017", "SLOT-JAI-019")

    assert result.eligible is True
    assert result.failure_code is None
    assert result.explanation, "an eligible slot must still explain why, not just say yes"
    assert result.checked_constraints  # non-empty: this is what "per-invariant" means


@pytest.mark.asyncio
async def test_explain_slot_eligibility_names_the_same_failure_code_request_slot_would_give():
    """FR-DRV-006 answers with the same vocabulary evaluate_candidate_slot already uses for
    request_slot's own rejection -- a driver asking "why not" and a driver who tried and got a
    409 should hear the same reason, not two different vocabularies for one fact."""
    shipment_row = _shipment(
        driver_id="DRV001",
        destination_facility_id="FAC-JAI-01",
        effective_eta_ts="2026-08-04T11:30:00+05:30",
        driver_earliest_acceptable_ts=None,
        driver_latest_acceptable_ts=None,
    )
    candidate_row = _candidate(active_appointment_id="APT-EXISTING")
    facility_row = {**_facility(), "active_flag": 1, "facility_rules_json": "[]"}
    session = _eligibility_session(
        shipment_row=shipment_row, candidate_row=candidate_row, facility_row=facility_row
    )

    result = await explain_slot_eligibility(session, _driver_ctx(), "SHP1017", "SLOT-JAI-019")

    assert result.eligible is False
    assert result.failure_code == "SLOT_CAPACITY_UNAVAILABLE"
    assert result.message
    assert result.explanation == []


@pytest.mark.asyncio
async def test_explain_slot_eligibility_reports_not_found_without_raising():
    """Browse-only per FR-DRV-006's own wording: a slot_id that does not exist at this
    facility is an answer ("not eligible, here is why"), not a 404 the driver assistant has
    to translate into conversational language itself."""
    shipment_row = _shipment(
        driver_id="DRV001",
        destination_facility_id="FAC-JAI-01",
        effective_eta_ts="2026-08-04T11:30:00+05:30",
        driver_earliest_acceptable_ts=None,
        driver_latest_acceptable_ts=None,
    )
    session = _eligibility_session(shipment_row=shipment_row, candidate_row=None, facility_row=None)

    result = await explain_slot_eligibility(session, _driver_ctx(), "SHP1017", "SLOT-DOES-NOT-EXIST")

    assert result.eligible is False
    assert result.failure_code == "SLOT_NOT_FOUND"


@pytest.mark.asyncio
async def test_explain_slot_eligibility_refuses_a_shipment_outside_the_callers_scope():
    """assert_shipment_visible (E2.2's repository tier) is the actual scope gate here -- a
    different driver's shipment must be refused before any slot data is even fetched."""
    shipment_row = _shipment(
        driver_id="DRV999",  # not the calling driver
        destination_facility_id="FAC-JAI-01",
        effective_eta_ts="2026-08-04T11:30:00+05:30",
        driver_earliest_acceptable_ts=None,
        driver_latest_acceptable_ts=None,
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_mock_result(shipment_row))

    with pytest.raises(AppError) as exc_info:
        await explain_slot_eligibility(session, _driver_ctx(), "SHP-NOT-MINE", "SLOT-JAI-019")
    assert exc_info.value.code == "FORBIDDEN"
