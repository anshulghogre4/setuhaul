"""The sequencer's pure core -- SOLUTION_DESIGN.md section 5.1 (issues #49, #54, #69's remainder).

What is asserted **here** rather than in `tests/proof/test_part12_sequencer.py`: everything that is
a property of the objective, the search and the diff, none of which needs a database. What is
asserted **there**: everything that is a property of what PostgreSQL refuses -- the partial unique
index behind `RUN_ALREADY_ACTIVE`, the exclusion constraint behind an all-or-nothing apply, the
snapshot recomputation over real rows. The CHANGELOG's 2026-09-01 lesson is why the split is drawn
there and not further along: a mocked session cannot refuse anything, so a unit test can never be
evidence that the database defends an invariant.

The four claims this file exists to pin, each one a place where section 5.1 is easy to implement
*almost* right:

  1. **One currency with Stage 2.** The waiting and fallback-dock terms are Stage 2's own numbers
     with the sign flipped -- taken from the `ranking_factors` receipt `_rank_slot` produced, not
     recomputed. If someone ever "simplifies" that into a local calculation, section 5.1's opening
     warning comes true: *"the two will recommend different things and the planner sees the system
     contradict itself."*
  2. **`P_churn` prices only a communicated promise, past a 15-minute epsilon.** Both halves are
     boundary-tested, because both are cheap to get subtly wrong and neither is visible in a diff.
  3. **The proposal never double-books a dock**, using the claim window and not the slot window.
  4. **Determinism** (NFR-007): the same scope and policy produce a byte-identical proposal.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import FeasibleSlotOption
from app.scheduling.occupancy import CHANGEOVER_BUFFER_MINUTES, claim_window_sql
from app.scheduling.sequencer import (
    CHURN_EPSILON_MINUTES,
    WEIGHT_CHURN,
    Coefficients,
    Job,
    Scope,
    build_diff,
    build_explanation,
    build_objective,
    claim_window,
    _search,
    placement_cost,
)

FACILITY = {
    "facility_id": "FAC-JAI-01",
    "facility_name": "Jaipur DC",
    "timezone": "Asia/Kolkata",
    "open_time": "06:00",
    "close_time": "22:00",
}
BASE = datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc)


def _shipment(shipment_id: str = "SHP1001", priority: str = "NORMAL", unload: int = 60):
    return {
        "shipment_id": shipment_id,
        "order_reference": f"ORD-{shipment_id}",
        "priority_code": priority,
        "carrier_id": "CAR001",
        "required_dock_type": "STANDARD",
        "temperature_control_required": 0,
        "load_weight_kg": 8000,
        "expected_unload_min": unload,
        "original_eta_ts": BASE.isoformat(),
        "current_status": "IN_TRANSIT",
    }


def _job(
    *,
    shipment_id: str = "SHP1001",
    priority: str = "NORMAL",
    unload: int = 60,
    release: datetime | None = None,
    due: datetime | None = None,
    current_slot_id: str | None = None,
    current_start: datetime | None = None,
    communicated: bool = False,
    pinned: bool = False,
    weight: int | None = None,
) -> Job:
    scores = load_scheduling_constraints().ranking_policy.priority_scores
    return Job(
        shipment=_shipment(shipment_id, priority, unload),
        release=release or BASE,
        release_source="ETA",
        due=due,
        weight=weight if weight is not None else scores[priority],
        appointment_id=("APT-" + shipment_id) if current_slot_id else None,
        appointment_status="CONFIRMED" if communicated else ("PENDING_CONFIRMATION" if current_slot_id else None),
        current_slot_id=current_slot_id,
        current_dock_id="DOCK-A" if current_slot_id else None,
        current_dock_code="D1" if current_slot_id else None,
        current_start=current_start,
        pinned=pinned,
        communicated=communicated,
        driver_window={},
    )


def _option(
    *,
    slot_id: str = "SLOT-1",
    dock_id: str = "DOCK-A",
    start: datetime | None = None,
    unload: int = 60,
    wait_minutes: int = 0,
    exact_dock: bool = True,
    fairness_penalty: int = 0,
    rank_score: int = 2000,
) -> FeasibleSlotOption:
    """A Stage-2 option as `evaluate_candidate_slot` would have produced it.

    `ranking_factors` carries the two keys `placement_cost` reads back rather than recomputes --
    that borrowing is the mechanism behind claim 1 above, so the fixture has to be shaped like the
    real receipt, not like whatever this file finds convenient.
    """
    start = start or BASE
    return FeasibleSlotOption(
        slot_id=slot_id,
        facility_id="FAC-JAI-01",
        dock_id=dock_id,
        dock_code=dock_id[-2:],
        dock_type="STANDARD",
        slot_start_ts=start.isoformat(),
        slot_end_ts=(start + timedelta(minutes=unload + 30)).isoformat(),
        feasible_start_ts=start.isoformat(),
        feasible_end_ts=(start + timedelta(minutes=unload)).isoformat(),
        rank_score=rank_score,
        ranking_factors={
            "priority_code": "NORMAL",
            "wait_after_eta_minutes": wait_minutes,
            "dock_match": "exact" if exact_dock else "compatible",
            "carrier_concentration": 0,
            "fairness_penalty": fairness_penalty,
        },
        ranking_explanation=[],
        checked_constraints=[],
    )


# ---------------------------------------------------------------------------------------------
# The claim window -- D1's interval, not the published slot's
# ---------------------------------------------------------------------------------------------


def test_the_python_claim_window_mirrors_the_sql_one_the_database_actually_writes():
    """`claim_window` and `occupancy.claim_window_sql` must mean the same interval.

    The sequencer plans against the Python one and PostgreSQL enforces the SQL one, so a divergence
    would produce proposals the exclusion constraint refuses -- the #97 failure shape with a new
    module in it. Pinned by reading the buffer out of the SQL text rather than restating 15 here.
    """
    start, end = claim_window(BASE, 75)
    assert end - start == timedelta(minutes=75 + CHANGEOVER_BUFFER_MINUTES)
    sql = claim_window_sql(start_expr="sl.slot_start_ts", unload_min_expr=":unload_min")
    assert f"+ {CHANGEOVER_BUFFER_MINUTES})" in sql.replace(" ", " ")
    # And the whole point of D1: a 75-minute unload does NOT fit its 60-minute published slot.
    assert end - start > timedelta(minutes=60)


# ---------------------------------------------------------------------------------------------
# Section 5.1's "one currency with Stage 2"
# ---------------------------------------------------------------------------------------------


def test_the_coefficients_are_stage_2s_own_weights_with_the_sign_inverted():
    """Section 5.1: *"Use the same coefficients with inverted sign -- the sequencer minimises
    exactly what Stage 2 maximises."* Read from `constraints.json`, never written down twice."""
    weights = load_scheduling_constraints().ranking_policy.score_weights
    coeff = Coefficients.from_policy()
    assert coeff.wait_per_minute == abs(weights["wait_after_eta_per_minute"])
    assert coeff.fallback_dock == abs(weights["compatible_but_not_exact_dock_penalty"])
    assert coeff.churn == weights[WEIGHT_CHURN]
    assert coeff.fairness == weights["w_fairness"]
    assert coeff.priority_scores == load_scheduling_constraints().ranking_policy.priority_scores


def test_the_waiting_term_is_stage_2s_own_wait_minutes_and_not_a_recomputation():
    """Claim 1. The cost must be `6 x ranking_factors['wait_after_eta_minutes']` exactly -- so a
    receipt saying 40 minutes and a cost saying anything but 240 is a contradiction, whatever this
    module might otherwise have derived from the timestamps."""
    coeff = Coefficients.from_policy()
    placement = placement_cost(_job(), _option(wait_minutes=40), coeff)
    assert placement.wait_minutes == 40
    assert placement.waiting_cost == 40 * coeff.wait_per_minute == 240


def test_a_fallback_dock_costs_exactly_stage_2s_penalty_and_an_exact_dock_costs_nothing():
    coeff = Coefficients.from_policy()
    assert placement_cost(_job(), _option(exact_dock=True), coeff).fallback_dock_cost == 0
    fallback = placement_cost(_job(), _option(exact_dock=False), coeff)
    assert fallback.fallback_dock_cost == coeff.fallback_dock == 25


def test_lateness_is_priority_weighted_minutes_past_the_promise_and_zero_without_one():
    """Section 5.1's `w_j * max(0, start_j - d_j)`. A job with no appointment has no `d_j`, so it
    has no lateness term at all -- not a large one, and not a zero that hides a missing due date."""
    coeff = Coefficients.from_policy()
    due = BASE
    late = placement_cost(
        _job(priority="CRITICAL", due=due), _option(start=due + timedelta(minutes=30)), coeff
    )
    assert late.lateness_minutes == 30
    assert late.lateness_cost == 30 * 4000

    early = placement_cost(
        _job(priority="CRITICAL", due=due), _option(start=due - timedelta(minutes=30)), coeff
    )
    assert early.lateness_minutes == 0 and early.lateness_cost == 0

    unpromised = placement_cost(_job(priority="CRITICAL"), _option(), coeff)
    assert unpromised.lateness_minutes == 0 and unpromised.lateness_cost == 0


def test_the_fairness_cost_is_the_literal_negation_of_stage_2s_own_penalty():
    """D7 / issue #69. Stage 2 *maximises* with a negative `w_fairness`, so the sequencer's
    *minimised* cost is that penalty's negation -- a non-negative cost when the term is enabled, and
    exactly zero at the shipped `w_fairness = 0`, which keeps section 5.1's four-term formula the
    one that actually runs."""
    coeff = Coefficients.from_policy()
    assert placement_cost(_job(), _option(fairness_penalty=0), coeff).fairness_cost == 0
    enabled = placement_cost(_job(), _option(fairness_penalty=-120), coeff)
    assert enabled.fairness_cost == 120


# ---------------------------------------------------------------------------------------------
# P_churn -- issue #69's other half
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("delta_minutes", "expected_churn"),
    [
        (0, False),
        (CHURN_EPSILON_MINUTES - 1, False),
        # Section 5.1: *"The 15-minute epsilon matches the D11 grid, so sub-grid jitter never counts
        # as churn."* At exactly the epsilon it is still jitter -- the rule is "> 15 min".
        (CHURN_EPSILON_MINUTES, False),
        (CHURN_EPSILON_MINUTES + 1, True),
        (-(CHURN_EPSILON_MINUTES + 1), True),  # moving a promise EARLIER is churn too
    ],
)
def test_churn_is_priced_only_past_the_d11_grid_epsilon(delta_minutes, expected_churn):
    coeff = Coefficients.from_policy()
    promised = BASE
    placement = placement_cost(
        _job(current_slot_id="SLOT-OLD", current_start=promised, communicated=True),
        _option(start=promised + timedelta(minutes=delta_minutes)),
        coeff,
    )
    assert placement.is_churn is expected_churn
    assert placement.churn_cost == (coeff.churn if expected_churn else 0)


def test_moving_an_uncommunicated_request_costs_no_churn():
    """Section 5.1's own diff annotates a moved row *"(not yet communicated)"* precisely because
    that move costs nothing in trust. A PENDING_CONFIRMATION request has not been agreed with the
    driver, so pricing it as churn would make the sequencer reluctant to fix a schedule nobody has
    been promised yet -- the opposite of what `P_churn` is for."""
    coeff = Coefficients.from_policy()
    placement = placement_cost(
        _job(current_slot_id="SLOT-OLD", current_start=BASE, communicated=False),
        _option(start=BASE + timedelta(hours=2)),
        coeff,
    )
    assert placement.is_churn is False and placement.churn_cost == 0


def test_a_churn_price_high_enough_makes_the_search_leave_a_promise_alone():
    """Section 5.1's whole justification for the term: *"A move must pay for itself."*

    Two jobs, one dock, and a cheaper arrangement that requires moving a communicated promise. At a
    low churn price the search takes it; at a high one it does not. Same scope, same code, one
    coefficient -- which is exactly the "policy decision, not a code change" property D7 asks for.
    """
    promised = BASE + timedelta(hours=1)
    incumbent = _job(
        shipment_id="SHP-A", current_slot_id="SLOT-EARLY", current_start=BASE, communicated=True
    )
    incumbent.options = {
        "SLOT-EARLY": _option(slot_id="SLOT-EARLY", start=BASE, wait_minutes=0, rank_score=2000),
        "SLOT-LATE": _option(
            slot_id="SLOT-LATE", start=promised, wait_minutes=1, rank_score=1990
        ),
    }
    scope = Scope(
        facility=FACILITY,
        facility_rules=[],
        horizon_start=BASE,
        horizon_end=BASE + timedelta(hours=4),
        horizon_end_reason="ROLLING_WINDOW",
        jobs=[incumbent],
        blocked={},
        candidates=[],
    )

    cheap = Coefficients.from_policy()
    object.__setattr__(cheap, "churn", 0)
    dear = Coefficients.from_policy()
    object.__setattr__(dear, "churn", 100_000)

    # With churn free, the 1-minute-of-waiting difference is the only signal, so the incumbent slot
    # (cost 0) still wins -- make the alternative genuinely cheaper by giving the incumbent a wait.
    incumbent.options["SLOT-EARLY"] = _option(
        slot_id="SLOT-EARLY", start=BASE, wait_minutes=10, rank_score=2000
    )
    assert _search(scope, cheap)["SHP-A"].slot_id == "SLOT-LATE"
    assert _search(scope, dear)["SHP-A"].slot_id == "SLOT-EARLY"


# ---------------------------------------------------------------------------------------------
# The search -- section 5.1's algorithm
# ---------------------------------------------------------------------------------------------


def _two_job_scope() -> Scope:
    """Two standard jobs and two intervals on the SAME dock, one of which they both prefer."""
    a = _job(shipment_id="SHP-A", priority="CRITICAL")
    b = _job(shipment_id="SHP-B", priority="LOW")
    for job, score in ((a, 4000), (b, 1000)):
        job.options = {
            "SLOT-1": _option(slot_id="SLOT-1", start=BASE, wait_minutes=0, rank_score=score),
            "SLOT-2": _option(
                slot_id="SLOT-2",
                start=BASE + timedelta(minutes=90),
                wait_minutes=90,
                rank_score=score - 100,
            ),
        }
    return Scope(
        facility=FACILITY,
        facility_rules=[],
        horizon_start=BASE,
        horizon_end=BASE + timedelta(hours=4),
        horizon_end_reason="ROLLING_WINDOW",
        jobs=[a, b],
        blocked={},
        candidates=[],
    )


def test_the_search_never_puts_two_jobs_on_one_dock_at_overlapping_times():
    """Claim 3, and the invariant NFR-006 turns into a headline metric. Both jobs prefer SLOT-1 on
    DOCK-A; exactly one can have it, and the overlap test is on the CLAIM window -- 60 minutes of
    unload plus D10's 15-minute buffer -- not on the published slot."""
    placements = _search(_two_job_scope(), Coefficients.from_policy())
    assert len(placements) == 2
    a, b = placements["SHP-A"], placements["SHP-B"]
    assert a.slot_id != b.slot_id
    assert not (a.claim[0] < b.claim[1] and b.claim[0] < a.claim[1])


def test_the_higher_stage_2_score_is_placed_first_and_gets_the_better_interval():
    """Section 5.1 step 2: *"Order jobs by Stage-2 score, descending."* The CRITICAL job outranks
    the LOW one, so it takes the earlier interval and the LOW job takes the later."""
    placements = _search(_two_job_scope(), Coefficients.from_policy())
    assert placements["SHP-A"].slot_id == "SLOT-1"
    assert placements["SHP-B"].slot_id == "SLOT-2"


def test_the_search_is_deterministic_for_one_scope_and_policy():
    """NFR-007: *"same snapshot + policy version -> byte-identical ranking and sequencer
    proposal."* Section 5.1 step 5's tie-break is what buys it; this asserts it rather than trusting
    that dictionary iteration happens to be stable."""
    coeff = Coefficients.from_policy()
    first = _search(_two_job_scope(), coeff)
    second = _search(_two_job_scope(), coeff)
    assert {k: (v.slot_id, v.dock_id, v.total) for k, v in first.items()} == {
        k: (v.slot_id, v.dock_id, v.total) for k, v in second.items()
    }


def test_a_pinned_job_is_never_placed_and_never_loses_its_dock():
    """Section 5.1's fixed tasks: *"In-progress unloads pin their dock to expected finish."* A
    pinned job gets no options and is not a placement decision -- its interval reaches the search as
    part of `Scope.blocked`, which `build_scope` fills from `list_live_dock_occupancy`."""
    scope = _two_job_scope()
    scope.jobs[0].pinned = True
    placements = _search(scope, Coefficients.from_policy())
    assert "SHP-A" not in placements


def test_a_blocked_interval_removes_the_placement_that_would_overlap_it():
    """`Scope.blocked` carries the intervals a run may not touch -- other facilities' overrunning
    bookings, live D2 holds, in-progress unloads and outage windows. A job whose only remaining
    interval is blocked becomes unplaceable rather than being placed on top of it."""
    scope = _two_job_scope()
    scope.jobs = scope.jobs[:1]
    scope.blocked = {
        "DOCK-A": [
            (BASE, BASE + timedelta(minutes=75)),
            (BASE + timedelta(minutes=90), BASE + timedelta(minutes=165)),
        ]
    }
    assert _search(scope, Coefficients.from_policy()) == {}


# ---------------------------------------------------------------------------------------------
# The diff and the objective
# ---------------------------------------------------------------------------------------------


def test_the_diff_sorts_jobs_into_section_5_1s_four_buckets():
    """*"What the planner actually receives (D5) -- a diff, not a schedule."* Unchanged / moved /
    newly placed / unplaceable, and the rule for each is the job's prior state, not its cost."""
    unchanged = _job(shipment_id="SHP-SAME", current_slot_id="SLOT-1", current_start=BASE)
    moved = _job(shipment_id="SHP-MOVE", current_slot_id="SLOT-OLD", current_start=BASE)
    fresh = _job(shipment_id="SHP-NEW")
    stuck = _job(shipment_id="SHP-STUCK")
    stuck.first_refusal = ("DOCK_INCOMPATIBLE_LOAD", "Needs a reefer dock; none is free.")
    for job in (unchanged, moved, fresh):
        job.options = {"SLOT-1": _option(slot_id="SLOT-1")}

    scope = Scope(
        facility=FACILITY, facility_rules=[], horizon_start=BASE,
        horizon_end=BASE + timedelta(hours=4), horizon_end_reason="ROLLING_WINDOW",
        jobs=[unchanged, moved, fresh, stuck], blocked={}, candidates=[],
    )
    coeff = Coefficients.from_policy()
    placements = {
        job.shipment_id: placement_cost(job, job.options["SLOT-1"], coeff)
        for job in (unchanged, moved, fresh)
    }
    diff = build_diff(scope, placements)

    assert [v.shipment_id for v in diff.unchanged] == ["SHP-SAME"]
    assert [v.shipment_id for v in diff.moved] == ["SHP-MOVE"]
    assert [v.shipment_id for v in diff.newly_placed] == ["SHP-NEW"]
    assert [v.shipment_id for v in diff.unplaceable] == ["SHP-STUCK"]
    # The unplaceable row carries Stage 1's own vocabulary, not a second one invented here.
    assert diff.unplaceable[0].failure_code == "DOCK_INCOMPATIBLE_LOAD"
    assert diff.counts == {"unchanged": 1, "moved": 1, "newly_placed": 1, "unplaceable": 1}


def test_the_objective_reports_every_term_and_counts_churn_separately_from_moves():
    """`churn_count <= promises_moved` always, and both are reported: D7's trade-off is monitored by
    the first, section 5.1's "promises moved" headline by the second. A run that moves three
    uncommunicated requests has moved three promises and churned none."""
    coeff = Coefficients.from_policy()
    churned = _job(
        shipment_id="SHP-A", current_slot_id="SLOT-OLD", current_start=BASE, communicated=True
    )
    quiet = _job(
        shipment_id="SHP-B", current_slot_id="SLOT-OLD-B", current_start=BASE, communicated=False
    )
    for job in (churned, quiet):
        job.options = {"SLOT-1": _option(slot_id="SLOT-1", start=BASE + timedelta(hours=1))}
    scope = Scope(
        facility=FACILITY, facility_rules=[], horizon_start=BASE,
        horizon_end=BASE + timedelta(hours=4), horizon_end_reason="ROLLING_WINDOW",
        jobs=[churned, quiet], blocked={}, candidates=[],
    )
    placements = {
        job.shipment_id: placement_cost(job, job.options["SLOT-1"], coeff)
        for job in (churned, quiet)
    }
    diff = build_diff(scope, placements)
    objective = build_objective(placements, diff, coeff)

    assert objective.promises_moved == 2
    assert objective.churn_count == 1
    assert objective.churn_cost == coeff.churn
    assert objective.total_cost == sum(p.total for p in placements.values())
    # The policy the run was scored with is stamped on it (D7 / section 5 Stage 2).
    assert objective.policy_version == load_scheduling_constraints().policy_version
    assert objective.coefficients[WEIGHT_CHURN] == coeff.churn


@pytest.mark.asyncio
async def test_the_apply_route_carries_the_typed_refusal_inside_errors_detail():
    """A 409 must not drop `infeasible[]` / `drift` on the floor.

    The frontend's central error type is built from `errors[0]` alone, so a typed payload that lives
    only in the envelope's `data` is unreachable from a rejected call -- and Flow 9 steps 4 and 5
    both require the console to render exactly that payload ("states this plainly", "explains which
    constraint made the whole proposal invalid"). This codebase's existing convention is to
    `json.dumps` the structured refusal into `detail` (`allocation._snapshot_stale_error`,
    `_displacement_error`, `_interval_unavailable_error` all do it); this asserts the sequencer's
    apply route follows it rather than inventing a second shape.
    """
    import json as _json
    from unittest.mock import AsyncMock, MagicMock

    from app.api.v1.routers import scheduling as route_module
    from app.scheduling.sequencer import ApplyResult

    refusal = ApplyResult(
        as_of="2026-08-04T09:00:00+00:00",
        code="PARTIALLY_INFEASIBLE",
        scheduling_run_id="SR-TEST",
        status="SUPERSEDED",
        infeasible=[
            {
                "shipment_id": "SHP1013",
                "slot_id": "SLOT-JAI-018",
                "failure_code": "DOCK_UNAVAILABLE",
                "message": "A dock event overlaps this slot.",
            }
        ],
    )

    async def _fake_apply(*args, **kwargs):
        return refusal

    original = route_module.apply_schedule_proposal
    route_module.apply_schedule_proposal = _fake_apply
    try:
        request = MagicMock()
        request.state.request_id = "req-1"
        response = await route_module.apply_schedule(
            "SR-TEST",
            route_module.ApplyScheduleBody(snapshot_hash="abc"),
            request,
            MagicMock(),
            AsyncMock(),
            idempotency_key="key-1",
        )
    finally:
        route_module.apply_schedule_proposal = original

    assert response.status_code == 409
    body = _json.loads(response.body)
    assert body["success"] is False
    assert body["errors"][0]["code"] == "PARTIALLY_INFEASIBLE"
    # The load-bearing assertion: `detail` round-trips to the full typed result.
    recovered = _json.loads(body["errors"][0]["detail"])
    assert recovered["infeasible"][0]["failure_code"] == "DOCK_UNAVAILABLE"
    assert recovered["scheduling_run_id"] == "SR-TEST"
    # And `data` still carries the same object, so a client reading either place sees one truth.
    assert body["data"]["infeasible"] == recovered["infeasible"]


def test_the_explanation_is_section_5_1s_own_template():
    """Templated, never generated (`voice-and-tone.md`:8). The counts and the effect line are the
    two things section 5.1's worked example puts in front of a planner."""
    scope = Scope(
        facility=FACILITY, facility_rules=[], horizon_start=BASE,
        horizon_end=BASE + timedelta(hours=4), horizon_end_reason="ROLLING_WINDOW",
        jobs=[], blocked={}, candidates=[],
    )
    diff = build_diff(scope, {})
    objective = build_objective({}, diff, Coefficients.from_policy())
    line = build_explanation(scope, diff, objective)
    assert "Jaipur DC" in line
    assert "Unchanged 0 · Moved 0 · Newly placed 0 · Unplaceable 0" in line
    assert "promises moved 0" in line
