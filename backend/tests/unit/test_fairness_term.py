"""A-G1 / issue #69 -- D7's `w_fairness` term: present, defaulted off, and no longer silently
droppable.

Three things are under test and they are deliberately separate concerns:

  1. **Byte-identity at `w_fairness = 0`.** The load-bearing regression risk: `_rank_slot` is the
     D1 booking hot path, and adding a term to it must be arithmetically invisible in the shipped
     policy. Proved by recomputing the pre-#69 formula literally, not by asserting "it still looks
     right".
  2. **A real effect when enabled.** A term that cannot change an outcome is not a term. This also
     covers *why* the input is keyed on the candidate's facility-local date rather than on the
     carrier alone -- a per-carrier constant could never reorder one shipment's own option list.
  3. **Unknown weight keys are refused, not ignored.** The actual defect #69 names: an admin could
     send `w_fairness`/`P_churn` to `POST /admin/policy/simulate` and get a real-looking
     `flip_count` the field contributed nothing to.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling import feasibility
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import WEIGHT_FAIRNESS, _rank_slot, evaluate_candidate_slot
from app.services import admin_governance_service

FACILITY = "FAC-JAI-01"


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------


def _shipment(**overrides):
    data = {
        "shipment_id": "SHP1017",
        "priority_code": "NORMAL",
        "original_eta_ts": "2026-08-04T11:30:00+05:30",
        "required_dock_type": "STANDARD",
        "temperature_control_required": 0,
        "load_weight_kg": 11500,
        "expected_unload_min": 50,
        "carrier_id": "CAR001",
    }
    data.update(overrides)
    return data


def _facility(**overrides):
    data = {
        "facility_id": FACILITY, "timezone": "Asia/Kolkata",
        "open_time": "06:00", "close_time": "22:00",
    }
    data.update(overrides)
    return data


def _candidate(**overrides):
    data = {
        "slot_id": "SLOT-JAI-019", "facility_id": FACILITY, "dock_id": "DOCK-JAI-D2",
        "dock_code": "D2", "dock_type": "STANDARD", "supports_refrigerated": 0,
        "max_vehicle_weight_kg": 25000, "dock_status": "ACTIVE",
        "slot_start_ts": "2026-08-04T12:00:00+05:30",
        "slot_end_ts": "2026-08-04T13:00:00+05:30",
        "slot_status": "OPEN", "active_appointment_id": None, "active_dock_event_id": None,
    }
    data.update(overrides)
    return data


def _rank_args(**overrides):
    args = {
        "shipment": _shipment(priority_code="HIGH"),
        "eta_dt": datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        "candidate": {"dock_type": "STANDARD", "slot_id": "SLOT-JAI-019"},
        "feasible_start": datetime.fromisoformat("2026-08-04T12:30:00+05:30"),
        "feasible_end": datetime.fromisoformat("2026-08-04T13:20:00+05:30"),
        "slot_end": datetime.fromisoformat("2026-08-04T14:00:00+05:30"),
    }
    args.update(overrides)
    return args


def _constraints_with_fairness(value: int):
    """A copy of the live constraints with `w_fairness` set, leaving `constraints.json` alone.

    Enabling the term is a POLICY change (D7: "a policy decision with an audit trail, not a code
    change"), so a test that needed the shipped file edited to exercise it would be testing the
    wrong thing.
    """
    base = load_scheduling_constraints()
    policy = base.ranking_policy.model_copy(
        update={"score_weights": {**base.ranking_policy.score_weights, WEIGHT_FAIRNESS: value}}
    )
    return base.model_copy(update={"ranking_policy": policy})


# ---------------------------------------------------------------------------------------------
# 1 -- byte-identity at the shipped w_fairness = 0
# ---------------------------------------------------------------------------------------------


def test_the_shipped_policy_defaults_the_fairness_term_to_zero():
    """D7: "present, defaulted off". Before #69 the key was absent entirely, which made
    "defaulted off" and "not implemented" indistinguishable from the outside."""
    weights = load_scheduling_constraints().ranking_policy.score_weights
    assert WEIGHT_FAIRNESS in weights
    assert weights[WEIGHT_FAIRNESS] == 0


@pytest.mark.parametrize("concentration", [0, 1, 3, 17])
def test_rank_slot_score_is_identical_to_the_pre_change_formula_at_w_fairness_zero(concentration):
    """The regression proof. The expected value is the literal pre-#69 expression, recomputed
    here rather than captured from the new code, so this fails if the added term ever contributes
    anything at the shipped weight -- for ANY carrier concentration, not merely for zero."""
    policy = load_scheduling_constraints().ranking_policy
    weights = policy.score_weights
    priority_scores = policy.priority_scores
    args = _rank_args()

    lateness_minutes = 35  # 11:30 original ETA -> 12:05 effective ETA
    wait_after_eta_minutes = 25  # 12:05 -> 12:30
    fit_slack_minutes = 40  # 13:20 -> 14:00

    pre_change_score = (
        priority_scores["HIGH"]
        + min(lateness_minutes, weights["lateness_cap_minutes"]) * weights["lateness_per_minute"]
        + wait_after_eta_minutes * weights["wait_after_eta_per_minute"]
        + min(fit_slack_minutes, weights["fit_slack_cap_minutes"]) * weights["fit_slack_per_minute"]
        + 0  # exact dock type match
    )

    score, factors = _rank_slot(**args, carrier_concentration=concentration)

    assert score == pre_change_score
    assert factors["lateness_minutes"] == lateness_minutes
    assert factors["wait_after_eta_minutes"] == wait_after_eta_minutes
    assert factors["fit_slack_minutes"] == fit_slack_minutes
    assert factors["fairness_penalty"] == 0


def test_rank_slot_ranking_factors_keep_every_pre_change_key_unchanged():
    """The receipt is a public response field (`FeasibleSlotOption.ranking_factors`). #69 may add
    keys to it; it may not change or drop one."""
    score_default, factors_default = _rank_slot(**_rank_args())
    score_explicit, factors_explicit = _rank_slot(**_rank_args(), carrier_concentration=0)

    assert score_default == score_explicit
    assert factors_default == factors_explicit

    pre_change_keys = {
        "priority_code", "priority_score", "lateness_minutes", "wait_after_eta_minutes",
        "fit_slack_minutes", "dock_match", "operational_disruption_score", "stable_tiebreaker",
    }
    assert pre_change_keys <= set(factors_default)
    # ...and exactly the two new ones, so a third does not creep in unnoticed.
    assert set(factors_default) - pre_change_keys == {"carrier_concentration", "fairness_penalty"}


def test_the_driver_facing_explanation_is_unchanged_while_the_term_is_off():
    """`ranking_explanation` is what the LLM narrates to a driver (section 12.1 Q11). A
    "fairness penalty 0" sentence on an option card would be noise, so the prose stays at its
    four pre-#69 sentences while the structured receipt above still reports the zero."""
    option, reason = evaluate_candidate_slot(
        shipment=_shipment(), facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(), checked_constraints=[],
    )
    assert reason is None and option is not None
    assert len(option.ranking_explanation) == 4
    assert not any("fairness" in line.lower() for line in option.ranking_explanation)
    assert option.ranking_factors["carrier_concentration"] == 0


def test_evaluate_candidate_slot_ignores_a_concentration_map_while_the_term_is_off():
    """The map can be present and non-empty (a caller could pass a stale one) and must still not
    move the score while the policy has the term disabled."""
    without, _ = evaluate_candidate_slot(
        shipment=_shipment(), facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(), checked_constraints=[],
    )
    with_map, _ = evaluate_candidate_slot(
        shipment=_shipment(), facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(), checked_constraints=[],
        carrier_concentration_by_local_date={"2026-08-04": 9},
    )
    assert without is not None and with_map is not None
    assert with_map.rank_score == without.rank_score
    assert with_map.ranking_factors["carrier_concentration"] == 9
    assert with_map.ranking_factors["fairness_penalty"] == 0


# ---------------------------------------------------------------------------------------------
# 2 -- a real effect once an admin enables it
# ---------------------------------------------------------------------------------------------


def test_enabling_w_fairness_penalises_a_carrier_that_already_holds_capacity(monkeypatch):
    monkeypatch.setattr(feasibility, "load_scheduling_constraints", lambda: _constraints_with_fairness(-40))

    unconcentrated, _ = _rank_slot(**_rank_args(), carrier_concentration=0)
    concentrated, factors = _rank_slot(**_rank_args(), carrier_concentration=3)

    assert concentrated == unconcentrated - 120
    assert factors["carrier_concentration"] == 3
    assert factors["fairness_penalty"] == -120


def test_the_fairness_term_can_actually_reorder_one_shipments_own_options(monkeypatch):
    """Why the input is keyed on the candidate's LOCAL DATE and not on the carrier alone: a bare
    per-carrier count is constant across a shipment's candidate pool and therefore can never
    change which interval that driver is offered -- a term in name only. Here the carrier already
    owns three of today's intervals, so tomorrow morning wins instead."""
    monkeypatch.setattr(feasibility, "load_scheduling_constraints", lambda: _constraints_with_fairness(-200))
    concentration = {"2026-08-04": 3, "2026-08-05": 0}
    # A round-the-clock facility, so the two candidates can straddle local midnight an hour apart
    # rather than being separated by an overnight closure -- the wait penalty would otherwise
    # dominate any plausible fairness weight and the comparison would prove nothing.
    shared = {
        "shipment": _shipment(expected_unload_min=30),
        "facility": _facility(open_time="00:00", close_time="23:59"),
        "eta_dt": datetime.fromisoformat("2026-08-04T23:00:00+05:30"), "checked_constraints": [],
    }
    tonight = _candidate(slot_start_ts="2026-08-04T23:00:00+05:30", slot_end_ts="2026-08-04T23:45:00+05:30")
    after_midnight = _candidate(
        slot_id="SLOT-JAI-101",
        slot_start_ts="2026-08-05T00:00:00+05:30", slot_end_ts="2026-08-05T00:45:00+05:30",
    )

    today, _ = evaluate_candidate_slot(
        candidate=tonight, carrier_concentration_by_local_date=concentration, **shared
    )
    tomorrow, _ = evaluate_candidate_slot(
        candidate=after_midnight, carrier_concentration_by_local_date=concentration, **shared
    )

    assert today is not None and tomorrow is not None
    assert today.slot_local_date == "2026-08-04" and tomorrow.slot_local_date == "2026-08-05"
    assert today.ranking_factors["fairness_penalty"] == -600
    assert tomorrow.ranking_factors["fairness_penalty"] == 0
    assert tomorrow.rank_score > today.rank_score
    # ...and with the term off, the same pair ranks the other way round, which is what makes this
    # a demonstration of the term rather than of the fixture.
    monkeypatch.setattr(feasibility, "load_scheduling_constraints", load_scheduling_constraints)
    today_off, _ = evaluate_candidate_slot(candidate=tonight, **shared)
    tomorrow_off, _ = evaluate_candidate_slot(candidate=after_midnight, **shared)
    assert today_off is not None and tomorrow_off is not None
    assert today_off.rank_score > tomorrow_off.rank_score


def test_an_enabled_fairness_term_says_so_in_the_driver_facing_explanation(monkeypatch):
    monkeypatch.setattr(feasibility, "load_scheduling_constraints", lambda: _constraints_with_fairness(-40))
    option, _ = evaluate_candidate_slot(
        shipment=_shipment(), facility=_facility(),
        eta_dt=datetime.fromisoformat("2026-08-04T12:05:00+05:30"),
        candidate=_candidate(), checked_constraints=[],
        carrier_concentration_by_local_date={"2026-08-04": 2},
    )
    assert option is not None
    assert len(option.ranking_explanation) == 5
    assert "Fairness term applied (D7)" in option.ranking_explanation[4]


# ---------------------------------------------------------------------------------------------
# 2b -- the round-trip budget. COMPARISON-latency F16 already flags find_feasible_slots' four
# sequential trips; the disabled default must not gain a fifth.
# ---------------------------------------------------------------------------------------------


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-DRV-1", email="ravi@setuhaul.com",
        full_name="Ravi", role_id="ROL001", role_name=RoleName.DRIVER, driver_id="DRV001",
    )


def _feasibility_session(*, concentration_rows: list | None = None) -> AsyncMock:
    """A session that answers find_feasible_slots' reads in order: shipment, facility,
    active appointment, [carrier concentration], candidate slots."""
    eta = "2026-08-04T12:05:00+05:30"
    results: list = [
        {
            **_shipment(), "driver_id": "DRV001", "vehicle_id": "VEH1",
            "destination_facility_id": FACILITY, "current_status": "IN_TRANSIT",
            "latest_eta_ts": eta, "effective_eta_ts": eta, "eta_source": "DRIVER_DECLARED",
            "eta_confidence": "MEDIUM", "driver_earliest_acceptable_ts": None,
            "driver_latest_acceptable_ts": None,
        },
        {**_facility(), "facility_name": "Jaipur", "active_flag": 1, "facility_rules_json": "[]"},
        None,  # no active appointment
    ]
    if concentration_rows is not None:
        results.append(concentration_rows)
    results.append([_candidate()])

    mocks = []
    for item in results:
        m = MagicMock()
        if isinstance(item, list):
            m.mappings.return_value.all.return_value = item
        else:
            m.mappings.return_value.first.return_value = item
        mocks.append(m)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mocks)
    return session


@pytest.mark.asyncio
async def test_find_feasible_slots_makes_no_extra_round_trip_while_fairness_is_off():
    session = _feasibility_session()
    result = await feasibility.find_feasible_slots(session, _driver_ctx(), "SHP1017")

    assert result.options[0].ranking_factors["fairness_penalty"] == 0
    assert session.execute.await_count == 4
    assert not any(
        "carrier_id = :carrier_id" in str(call.args[0]) for call in session.execute.call_args_list
    )


@pytest.mark.asyncio
async def test_find_feasible_slots_reads_carrier_concentration_only_once_fairness_is_enabled(monkeypatch):
    monkeypatch.setattr(feasibility, "load_scheduling_constraints", lambda: _constraints_with_fairness(-40))
    session = _feasibility_session(concentration_rows=[{"local_date": "2026-08-04", "held_count": 2}])

    result = await feasibility.find_feasible_slots(session, _driver_ctx(), "SHP1017")

    assert session.execute.await_count == 5
    concentration_sql = str(session.execute.call_args_list[3].args[0])
    # The shipment being ranked must not count itself, and the count is facility-local per day.
    assert "other.shipment_id <> :shipment_id" in concentration_sql
    assert "AT TIME ZONE :tz_name" in concentration_sql
    assert result.options[0].ranking_factors["carrier_concentration"] == 2
    assert result.options[0].ranking_factors["fairness_penalty"] == -80


# ---------------------------------------------------------------------------------------------
# 3 -- unknown weight keys are refused, not silently dropped
# ---------------------------------------------------------------------------------------------


def _admin_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-ADMIN-1", email="admin@setuhaul.com",
        full_name="Admin", role_id="ROL008", role_name=RoleName.ADMIN,
    )


def test_the_weight_allowlist_is_derived_from_the_live_engines_own_key_set():
    """A hand-written allowlist would drift the moment a coefficient changed. This one cannot."""
    engine_keys = set(load_scheduling_constraints().ranking_policy.score_weights)
    allowed = admin_governance_service.allowed_weight_keys()
    assert engine_keys <= allowed
    assert WEIGHT_FAIRNESS in allowed
    assert "priority_scores" in allowed
    assert "P_churn" not in allowed


@pytest.mark.asyncio
async def test_simulate_refuses_p_churn_and_names_the_sequencer_as_the_reason():
    """P_churn is not a typo -- it is a real section 5 formula term whose definition depends on
    the sequencer (#49), which is unbuilt. Saying so beats "unknown key"."""
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.simulate_policy_weights(
            session, _admin_ctx(), weights={"P_churn": 30},
            window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(days=1),
        )
    assert exc.value.code == "UNKNOWN_WEIGHT_KEYS"
    assert exc.value.status_code == 422
    assert "P_churn" in exc.value.message
    assert "sequencer" in exc.value.detail.lower() and "#49" in exc.value.detail
    # Refused before any read: a rejected simulation must not scan the window.
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_simulate_refuses_a_misspelled_weight_rather_than_ignoring_it():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.simulate_policy_weights(
            session, _admin_ctx(), weights={"lateness_per_min": 4},
            window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(days=1),
        )
    assert exc.value.code == "UNKNOWN_WEIGHT_KEYS"
    assert "lateness_per_min" in exc.value.message
    # The refusal names what IS accepted, so the admin can correct it without reading the source.
    assert "lateness_per_minute" in exc.value.detail


@pytest.mark.asyncio
async def test_simulate_accepts_w_fairness_and_reports_that_it_evaluated_the_term(monkeypatch):
    """The whole point of #69: `w_fairness` reaches the formula instead of being dropped, and the
    response says outright that it did."""
    calls: dict = {}

    async def _fake_candidates(session, *, window_start, window_end):
        calls["candidates"] = True
        return []

    async def _fake_concentration(session, *, window_start, window_end):
        calls["concentration"] = True
        return {}

    monkeypatch.setattr(admin_governance_service, "_replayable_candidates", _fake_candidates)
    monkeypatch.setattr(admin_governance_service, "_carrier_concentration_map", _fake_concentration)

    result = await admin_governance_service.simulate_policy_weights(
        AsyncMock(), _admin_ctx(), weights={WEIGHT_FAIRNESS: -40},
        window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert result["code"] == "SIMULATED"
    assert result["fairness_term_evaluated"] is True
    assert result["proposed_w_fairness"] == -40
    assert result["live_w_fairness"] == 0
    assert calls.get("concentration") is True


@pytest.mark.asyncio
async def test_simulate_skips_the_concentration_read_when_neither_side_enables_fairness(monkeypatch):
    async def _fake_candidates(session, *, window_start, window_end):
        return []

    async def _must_not_run(session, *, window_start, window_end):
        raise AssertionError("concentration must not be read when w_fairness is 0 on both sides")

    monkeypatch.setattr(admin_governance_service, "_replayable_candidates", _fake_candidates)
    monkeypatch.setattr(admin_governance_service, "_carrier_concentration_map", _must_not_run)

    result = await admin_governance_service.simulate_policy_weights(
        AsyncMock(), _admin_ctx(), weights={"lateness_per_minute": 5},
        window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert result["fairness_term_evaluated"] is False


@pytest.mark.asyncio
async def test_publish_refuses_an_unread_weight_key_before_taking_an_idempotency_key():
    """Writing an unread key into an immutable policy_versions row is the same silent lie as
    dropping it in a simulation, only durable. Refused before the key is consumed, so a corrected
    retry can reuse it."""
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.publish_policy_version(
            session, _admin_ctx(), weights={"P_churn": 30}, idempotency_key="pub-churn",
        )
    assert exc.value.code == "UNKNOWN_WEIGHT_KEYS"
    session.execute.assert_not_awaited()


def test_the_simulators_copied_formula_matches_rank_slot_with_the_fairness_term_too():
    """`admin_governance_service._score` is a deliberate copy of `_rank_slot`'s formula (see that
    module's docstring). The existing parity test pins them at concentration 0; this extends the
    same guard to the new term, which is where a copy is most likely to drift."""
    weights = {**load_scheduling_constraints().ranking_policy.score_weights, WEIGHT_FAIRNESS: -40}
    priority_scores = load_scheduling_constraints().ranking_policy.priority_scores

    copied = admin_governance_service._score(
        priority_code="HIGH", lateness_minutes=35, wait_after_eta_minutes=25,
        fit_slack_minutes=40, exact_dock_type_match=True, weights=weights,
        priority_scores=priority_scores, carrier_concentration=3,
    )
    baseline = admin_governance_service._score(
        priority_code="HIGH", lateness_minutes=35, wait_after_eta_minutes=25,
        fit_slack_minutes=40, exact_dock_type_match=True, weights=weights,
        priority_scores=priority_scores, carrier_concentration=0,
    )
    assert copied == baseline - 120
