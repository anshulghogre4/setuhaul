"""A-G6 / issue #74 -- `get_facility_rule_impact`, the read behind `edge-cases.md` #4's High-tier
confirmation ("the count of affected appointments *before* the edit commits").

The scenario the edge case names verbatim is the first test: tightening the new-start cutoff from
21:00 to 20:00 while a CONFIRMED appointment sits at 20:30.

Shaped after `get_dock_block_impact`/`get_user_removal_impact` -- a pure read, no write, and the
edit path itself is deliberately unchanged (facility rules govern future feasibility checks; they
never un-commit a promise).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services import admin_governance_service
from app.services.admin_governance_service import get_facility_rule_impact

FACILITY = "FAC-JAI-01"


def _admin_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-ADMIN-1", email="admin@setuhaul.com",
        full_name="Admin", role_id="ROL008", role_name=RoleName.ADMIN,
    )


def _non_admin_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-OPS-1", email="ops@setuhaul.com",
        full_name="Ops", role_id="ROL002", role_name=RoleName.OPERATIONS_EXECUTIVE, facility_id=FACILITY,
    )


def _session_with(*results) -> AsyncMock:
    mocks = []
    for r in results:
        m = MagicMock()
        if isinstance(r, list):
            m.mappings.return_value.all.return_value = r
        else:
            m.mappings.return_value.first.return_value = r
        mocks.append(m)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mocks)
    return session


def _rule(**overrides):
    data = {
        "rule_id": "RULE005", "facility_id": FACILITY, "rule_type": "LAST_NEW_START_TIME",
        "rule_value": "21:00", "description": "No new unload starts after 21:00",
        "effective_from": None, "effective_to": None, "active_flag": 1,
        "timezone": "Asia/Kolkata",
    }
    data.update(overrides)
    return data


def _appointment(**overrides):
    data = {
        "appointment_id": "APT2001", "shipment_id": "SHP2001", "appointment_status": "CONFIRMED",
        "slot_id": "SLOT-JAI-088", "slot_start_ts": "2026-08-04T20:30:00+05:30",
        "slot_end_ts": "2026-08-04T21:30:00+05:30", "dock_id": "DOCK-JAI-D2", "dock_code": "D2",
        "dock_type": "STANDARD", "supports_refrigerated": 0, "load_weight_kg": 11500,
        "temperature_control_required": 0, "carrier_id": "CAR001",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------------------------
# edge-cases.md #4, verbatim
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tightening_the_new_start_cutoff_names_the_2030_appointment_it_would_strand():
    """edge-cases.md #4 word for word: "Tightening ... from 21:00 to 20:00 could make an
    already-CONFIRMED appointment at 20:30 retroactively non-compliant"."""
    session = _session_with(_rule(), [_appointment()])

    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="20:00"
    )

    assert result["evaluable"] is True
    assert result["affected_count"] == 1
    affected = result["affected_appointments"][0]
    assert affected["appointment_id"] == "APT2001"
    assert affected["shipment_id"] == "SHP2001"
    assert affected["appointment_status"] == "CONFIRMED"
    # The reason is the ENGINE's own message, so the dialog cannot describe the violation
    # differently from the check that will actually reject future bookings.
    assert "20:00" in affected["reason"] and "20:30" in affected["reason"]
    assert result["already_non_compliant_count"] == 0
    assert result["current"]["rule_value"] == "21:00"
    assert result["proposed"]["rule_value"] == "20:00"


@pytest.mark.asyncio
async def test_an_appointment_that_still_complies_after_the_edit_is_not_counted():
    """20:30 against a 20:45 cutoff is fine. A preview that counted every appointment in the
    window would make every rule edit look catastrophic."""
    session = _session_with(_rule(), [_appointment()])
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="20:45"
    )
    assert result["affected_count"] == 0
    assert result["scanned_count"] == 1


@pytest.mark.asyncio
async def test_an_appointment_the_current_rule_already_forbids_is_reported_separately():
    """This edit did not cause those, so folding them into affected_count would overstate the
    consequence of pressing Save -- and understating it is not the fix either, hence a second
    named number rather than a silent exclusion."""
    session = _session_with(
        _rule(rule_value="20:00"),
        [_appointment(slot_start_ts="2026-08-04T20:30:00+05:30")],
    )
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="19:00"
    )
    assert result["affected_count"] == 0
    assert result["already_non_compliant_count"] == 1


@pytest.mark.asyncio
async def test_a_cutoff_boundary_is_strict_the_same_way_the_engine_is():
    """`check_facility_rules` permits a start exactly AT the cutoff (RULE005 forbids starting
    *after* 21:00). The preview inherits that instead of re-deciding it."""
    session = _session_with(_rule(), [_appointment(slot_start_ts="2026-08-04T20:00:00+05:30")])
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="20:00"
    )
    assert result["affected_count"] == 0


# ---------------------------------------------------------------------------------------------
# The other two mechanically-evaluated rule types
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lowering_the_heavy_dock_threshold_names_the_overweight_loads_on_standard_docks():
    session = _session_with(
        _rule(rule_id="RULE004", rule_type="HEAVY_DOCK_REQUIRED_KG", rule_value="25000"),
        [
            _appointment(appointment_id="APT-A", load_weight_kg=11500),
            _appointment(appointment_id="APT-B", shipment_id="SHP2002", load_weight_kg=22000),
        ],
    )
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE004", rule_value="20000"
    )
    assert result["affected_count"] == 1
    assert result["affected_appointments"][0]["appointment_id"] == "APT-B"


@pytest.mark.asyncio
async def test_turning_the_reefer_pin_on_names_temperature_loads_on_non_reefer_docks():
    session = _session_with(
        _rule(rule_id="RULE003", rule_type="REEFER_DOCK_REQUIRED", rule_value="FALSE"),
        [
            _appointment(appointment_id="APT-A", temperature_control_required=1, supports_refrigerated=0),
            _appointment(appointment_id="APT-B", temperature_control_required=1, supports_refrigerated=1),
            _appointment(appointment_id="APT-C", temperature_control_required=0, supports_refrigerated=0),
        ],
    )
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE003", rule_value="TRUE"
    )
    assert [a["appointment_id"] for a in result["affected_appointments"]] == ["APT-A"]


# ---------------------------------------------------------------------------------------------
# Effectivity window -- the scan is bounded by the PROPOSED window, evaluated by the engine
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_scan_is_bounded_by_the_proposed_effective_window_not_by_wall_clock():
    """No `now()` filter, deliberately: this engine has no injected clock (section 9.1), so a
    wall-clock bound would return a confident zero against any dataset whose snapshot clock
    differs -- and a dialog that always says "0 affected" is worse than one that says nothing."""
    session = _session_with(_rule(), [])
    await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="20:00",
        effective_from="2026-08-04", effective_to="2026-08-06",
    )
    sql = str(session.execute.call_args_list[1].args[0])
    params = session.execute.call_args_list[1].args[1]
    assert "sl.slot_start_ts >= :scan_from" in sql
    assert "sl.slot_start_ts < :scan_to" in sql
    assert "now()" not in sql.lower()
    # A bare date is read as facility-local midnight, exactly as the engine reads it.
    assert params["scan_from"].isoformat().startswith("2026-08-04T00:00:00+05:30")
    assert params["active_statuses"] == ["PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"]


@pytest.mark.asyncio
async def test_an_appointment_outside_the_proposed_effective_window_is_not_affected():
    """The rule is not in force at that instant, so it cannot forbid it. `active_facility_rules`
    decides this, not a locally-rewritten date comparison."""
    session = _session_with(
        _rule(), [_appointment(slot_start_ts="2026-08-09T20:30:00+05:30")]
    )
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="20:00",
        effective_from="2026-08-01", effective_to="2026-08-05",
    )
    assert result["scanned_count"] == 1
    assert result["affected_count"] == 0


@pytest.mark.asyncio
async def test_omitting_every_proposal_answers_who_the_rule_already_excludes():
    """Arguments mirror `update_facility_rule`'s COALESCE semantics, so "no change proposed" is a
    legal question with a real answer rather than an error."""
    session = _session_with(
        _rule(rule_value="20:00"), [_appointment(slot_start_ts="2026-08-04T20:30:00+05:30")]
    )
    result = await get_facility_rule_impact(session, _admin_ctx(), rule_id="RULE005")
    assert result["proposed"] == result["current"]
    assert result["affected_count"] == 0
    assert result["already_non_compliant_count"] == 1


# ---------------------------------------------------------------------------------------------
# Honest non-answers
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("rule_type", ["CHECKIN_EARLY_LIMIT_MIN", "NO_SHOW_GRACE_MIN"])
async def test_a_rule_type_the_engine_never_evaluates_says_so_instead_of_returning_zero(rule_type):
    """Both are real registry types the feasibility engine deliberately does not enforce
    (`check_facility_rules`' own docstring says why). A confident "0 affected" would read as
    "checked, nothing found" when the truth is "nothing checks this at offer time"."""
    session = _session_with(_rule(rule_type=rule_type, rule_value="60"))
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="30"
    )
    assert result["evaluable"] is False
    assert result["affected_count"] == 0
    assert "not evaluated by the feasibility engine" in result["note"]
    # No appointment scan at all -- there is nothing to evaluate against.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_an_inactive_rule_reports_no_impact_and_names_why():
    """The engine loads `active_flag = 1` rules only, so editing an inactive one changes nothing
    until it is reactivated."""
    session = _session_with(_rule(active_flag=0))
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="20:00"
    )
    assert result["affected_count"] == 0
    assert "inactive" in result["note"]
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_truncation_is_reported_rather_than_hidden(monkeypatch):
    monkeypatch.setattr(admin_governance_service, "RULE_IMPACT_SCAN_LIMIT", 2)
    session = _session_with(
        _rule(),
        [_appointment(appointment_id="APT-A"), _appointment(appointment_id="APT-B", shipment_id="SHP2002")],
    )
    result = await get_facility_rule_impact(
        session, _admin_ctx(), rule_id="RULE005", rule_value="20:00"
    )
    assert result["truncated"] is True
    assert session.execute.call_args_list[1].args[1]["scan_limit"] == 2


# ---------------------------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_facility_rule_impact_raises_not_found():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await get_facility_rule_impact(session, _admin_ctx(), rule_id="RULE-GHOST")
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_facility_rule_impact_refuses_a_non_admin():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await get_facility_rule_impact(session, _non_admin_ctx(), rule_id="RULE005")
    assert exc.value.code == "FORBIDDEN"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_preview_never_writes():
    """edge-cases.md #4: the edit "does not reach into `appointments` and mutate or escalate
    them", and neither does looking at it."""
    session = _session_with(_rule(), [_appointment()])
    await get_facility_rule_impact(session, _admin_ctx(), rule_id="RULE005", rule_value="20:00")
    for call in session.execute.call_args_list:
        sql = str(call.args[0]).upper()
        assert "UPDATE " not in sql and "INSERT " not in sql and "DELETE " not in sql
    session.commit.assert_not_awaited()
