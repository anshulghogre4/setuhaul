"""Section 10 part 12 -- the facility sequencer against a real cluster (issues #49, #54, #69).

Design citation: `SOLUTION_DESIGN.md` D5 (*"Sequencer proposes; a planner applies"*), section 5
Stage 4, section 5.1 in full (run scope, objective, `P_churn`, debounce, the diff, the two apply
rules, the cascade path), section 7.5.3's three-tool table, section 7.5.5's
`request_sequencer_proposal` row.
Requirements: `ARCHITECTURE/REQUIREMENTS.md` FR-SYS-016, FR-SYS-019, FR-OPS-004, FR-PLN-009,
FR-SYS-042, NFR-006, NFR-007.

## What is asserted here and not in `tests/unit/test_scheduling_sequencer.py`

Everything that is a property of what **PostgreSQL** refuses or guarantees, because a mocked session
cannot refuse anything -- the CHANGELOG's 2026-09-01 lesson, that the unit suite sat green through
four production-breaking M5 defects. Specifically:

* the partial unique index really serialising a second proposal (`RUN_ALREADY_ACTIVE`);
* an apply really being all-or-nothing, proved by **counting rows before and after a refusal**
  rather than by trusting a code path (the "bite" the brief asks for);
* `SNAPSHOT_DRIFT` really firing when another actor moves capacity between propose and apply;
* the stored run really replaying byte-identically a read later;
* the moved promises really landing in `notification_outbox`, one row per driver per run;
* issue #54's `escalation_id` really being a foreign key that joins the incident to the run.

## The one piece of test scaffolding, stated plainly

The shipped seed has exactly one facility with active appointments (FAC-JAI-01, 14 of them across
2026-08-04) and section 5.1 allows one live proposal per facility, so these tests necessarily share
that facility and run in file order. `_clear_active_runs` resets that slot between scenarios. It is
**test hygiene, not a production affordance**: there is deliberately no "discard a proposal" tool
(see the migration's header on why `DISCARDED` has no producer), and a real deployment clears the
slot by applying, by drifting, or by the horizon passing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.execution_context import ExecutionContext, RoleName
from app.repositories import scheduling_runs as runs_repo
from app.scheduling import sequencer
from tests.proof.evidence import record_evidence

pytestmark = pytest.mark.asyncio(loop_scope="session")

FACILITY = "FAC-JAI-01"
PLANNER_USER = "USR102"      # WAREHOUSE_PLANNER at FAC-JAI-01 (seed)
OPS_USER = "USR101"          # OPERATIONS_EXECUTIVE at FAC-JAI-01 (seed)

# Section 9.1's deterministic clock. 03:00 UTC = 08:30 IST on the seeded day, so the 4-hour rolling
# horizon is 08:30-12:30 IST -- inside Jaipur's 06:00-22:00 operating window (hence ROLLING_WINDOW
# rather than the FACILITY_CLOSE clamp) and covering 11 of the seed's 14 active appointments.
NOW = datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)

# The dock taken out of service to force a re-sequence. This is DEVT001's own shape -- section 5.1's
# cascade example is "D3 down 09:15-13:00" -- and it is what makes `moved` non-empty deterministically
# rather than hoping the seed happens to contain an improvable schedule.
BLOCKED_DOCK = "DOCK-JAI-D1"


def _ctx(user_id: str, role: RoleName) -> ExecutionContext:
    return ExecutionContext(
        request_id="proof-sequencer",
        auth_subject=f"proof-{user_id}",
        user_id=user_id,
        email=f"{user_id.lower()}@proof.invalid",
        full_name=f"Proof {user_id}",
        role_id="ROL002",
        role_name=role,
        facility_id=FACILITY,
    )


def _planner() -> ExecutionContext:
    return _ctx(PLANNER_USER, RoleName.WAREHOUSE_PLANNER)


def _ops() -> ExecutionContext:
    return _ctx(OPS_USER, RoleName.OPERATIONS_EXECUTIVE)


async def _clear_active_runs(session) -> None:
    """Free the facility's one active-run slot. See this module's docstring: scaffolding only."""
    await session.execute(
        text(
            """
            UPDATE public.scheduling_runs
               SET status = 'SUPERSEDED', superseded_at = now(),
                   superseded_reason = 'TEST_RESET'
             WHERE facility_id = :f AND status = 'PROPOSED'
            """
        ),
        {"f": FACILITY},
    )
    await session.commit()


async def _block_dock(session, dock_id: str, *, event_id: str, start: datetime, end: datetime) -> None:
    """Take a dock out of service, through the table D1 makes the single availability authority.

    `dock_status_events`, not `appointment_slots.slot_status` -- section 0.9 point 9 already records
    that those two disagree, and `planner_service.block_dock` writes this one for the same reason.
    """
    await session.execute(
        text(
            """
            INSERT INTO public.dock_status_events (
              dock_event_id, dock_id, event_type, event_start_ts, event_end_ts, reason, created_at
            ) VALUES (
              :id, :dock, 'MANUAL_BLOCK', :start, :end, 'proof part 12', :created
            )
            ON CONFLICT (dock_event_id) DO NOTHING
            """
        ),
        {
            "id": event_id, "dock": dock_id, "start": start, "end": end,
            "created": start.isoformat(),
        },
    )
    await session.commit()


async def _end_block(session, event_id: str) -> None:
    await session.execute(
        text("DELETE FROM public.dock_status_events WHERE dock_event_id = :id"), {"id": event_id}
    )
    await session.commit()


async def _busiest_dock_in_horizon(session) -> str:
    """The dock carrying the most live promises inside the run horizon, chosen by query.

    Discovered rather than hardcoded, for the reason `test_part3b_notification_outbox.py` gives for
    its own fixture: appointment and dock ids are Layer-A seed data that section 9.1 explicitly
    allows to be rebased, so a test naming one silently stops testing anything the day the generator
    moves. `ORDER BY count DESC, dock_id` keeps the choice deterministic, which section 9.1 requires
    of every proof assertion.

    Taking this dock out of service is what makes `moved` non-empty **deterministically**: measured
    on a pristine cluster, the shipped seed's schedule is already locally optimal under section
    5.1's objective, so a proposal against it correctly moves nothing. A test that waited for a
    spontaneous move would be asserting on the seed's luck.
    """
    dock = await session.scalar(
        text(
            """
            SELECT sl.dock_id
              FROM public.appointments a
              JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
             WHERE a.is_current = 1
               AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED')
               AND sl.facility_id = :f
               AND sl.slot_start_ts >= :lo AND sl.slot_start_ts < :hi
             GROUP BY sl.dock_id
             ORDER BY count(*) DESC, sl.dock_id
             LIMIT 1
            """
        ),
        {"f": FACILITY, "lo": NOW, "hi": NOW + timedelta(hours=4)},
    )
    assert dock, "no dock carries a movable promise in the horizon -- fixture assumption broken"
    return str(dock)


async def _one_movable_promise_with_an_alternative(session) -> dict:
    """A live promise the engine itself says has somewhere else to go.

    Chosen by asking the sequencer, not by querying `appointments` and hoping: `build_scope` runs
    the same Stage-1 guard the proposal will, so `job.options` is the authoritative answer to "does
    this truck have another feasible interval today". Picking a promise **without** one and taking
    its slot away produces an `unplaceable` row -- the honest outcome, and measured on this seed the
    common one, because Jaipur's 4-hour horizon is close to saturated -- but not the scenario this
    test is about.

    That saturation is a real property of the shipped seed and is worth stating rather than working
    around silently: section 0's own arithmetic puts contention at "demand clustering into a narrow
    window", and the seeded 08:30-12:30 block is exactly such a cluster.

    **Having an alternative is necessary but not sufficient**, which is why this function verifies
    its choice rather than trusting it. Section 5.1's greedy places jobs in Stage-2 score order, so
    a low-priority truck's alternatives can be taken by higher-priority ones before its turn comes
    -- it then lands in `unplaceable`, not `moved`. Each candidate is therefore tried for real: the
    outage is written, the scope is rebuilt and the search re-run in-process, and the candidate is
    accepted only if that job genuinely comes back moved. Every trial is rolled back except the one
    that is kept, so nothing is left behind.

    Deterministic: candidates are tried most-alternatives-first, then by `shipment_id`.
    """
    scope = await sequencer.build_scope(session, facility_id=FACILITY, now=NOW)
    slots = {str(row["slot_id"]): row for row in scope.candidates}
    coeff = sequencer.Coefficients.from_policy()

    candidates: list[tuple[int, str, dict]] = []
    for job in scope.jobs:
        if job.pinned or not job.current_slot_id:
            continue
        alternatives = [slot_id for slot_id in job.options if slot_id != job.current_slot_id]
        current = slots.get(str(job.current_slot_id))
        if not alternatives or current is None:
            continue
        candidates.append(
            (
                -len(alternatives),
                job.shipment_id,
                {
                    "appointment_id": job.appointment_id,
                    "shipment_id": job.shipment_id,
                    "dock_id": str(current["dock_id"]),
                    "slot_start_ts": current["slot_start_ts"],
                    "slot_end_ts": current["slot_end_ts"],
                    "alternatives": len(alternatives),
                },
            )
        )
    candidates.sort(key=lambda item: (item[0], item[1]))

    for _, _, target in candidates:
        await _block_dock(
            session, target["dock_id"], event_id="DEVT-PROOF-12C",
            start=target["slot_start_ts"], end=target["slot_end_ts"],
        )
        trial_scope = await sequencer.build_scope(session, facility_id=FACILITY, now=NOW)
        placed = sequencer._search(trial_scope, coeff)
        diff = sequencer.build_diff(trial_scope, placed)
        if any(view.appointment_id == target["appointment_id"] for view in diff.moved):
            return target
        await _end_block(session, "DEVT-PROOF-12C")

    raise AssertionError(
        "no in-horizon promise can be forced to move: every candidate's alternatives are taken by "
        "higher-priority jobs. The seed's 08:30-12:30 block is saturated, which is a real property "
        "of the shipped data rather than a fixture bug -- see section 0's contention arithmetic."
    )


async def _capacity_fingerprint(session) -> dict[str, object]:
    """Every row count and value an apply could possibly change, in one snapshot.

    This is what makes "refuses entirely" a **measurement** rather than a claim: a refusal must
    leave all six of these identical. The appointment slot-assignment digest is included because a
    move rewrites `appointments.slot_id` without changing any row count -- a pure count check would
    have missed exactly the failure this test exists to catch.
    """
    counts = (
        await session.execute(
            text(
                """
                SELECT (SELECT count(*) FROM public.appointments)          AS appointments,
                       (SELECT count(*) FROM public.dock_occupancy)        AS occupancy,
                       (SELECT count(*) FROM public.audit_logs)            AS audit,
                       (SELECT count(*) FROM public.notification_outbox)   AS outbox,
                       (SELECT md5(string_agg(appointment_id || '=' || slot_id, ',' ORDER BY
                                              appointment_id))
                          FROM public.appointments)                        AS slot_digest,
                       (SELECT md5(string_agg(occupancy_id::text || '=' || dock_id || '=' ||
                                              lower("window")::text, ',' ORDER BY occupancy_id))
                          FROM public.dock_occupancy)                      AS claim_digest
                """
            )
        )
    ).mappings().first()
    return dict(counts)


async def _propose(session, *, ctx=None, now: datetime = NOW):
    result = await sequencer.propose_facility_schedule(
        session, ctx or _planner(), facility_id=FACILITY, now=now
    )
    return result


# ---------------------------------------------------------------------------------------------
# 1. propose -- the section 5.1 diff and objective, against real seeded capacity
# ---------------------------------------------------------------------------------------------


async def test_propose_produces_a_coherent_diff_with_objective_values_including_churn(
    work_sessionmaker,
):
    """Section 5.1: *"What the planner actually receives (D5) -- a diff, not a schedule."*

    Every assertion below is a structural property of that diff rather than a golden value, because
    the seed is Layer-A data that section 9.1 explicitly allows to be rebased -- a test pinned to
    "SHP1013 moves to 18:30" would stop testing anything the day the generator moves.

    The dock block is what makes `moved` non-empty deterministically: with `DOCK-JAI-D1` out of
    service across the horizon, every appointment on it is infeasible where it stands and Stage 1
    says so -- which is section 5.1's own cascade trigger ("dock status event"), not a contrivance.
    """
    async with work_sessionmaker() as session:
        await _clear_active_runs(session)
        await _block_dock(
            session, BLOCKED_DOCK, event_id="DEVT-PROOF-12A",
            start=NOW - timedelta(hours=1), end=NOW + timedelta(hours=6),
        )

    async with work_sessionmaker() as session:
        result = await _propose(session)

    assert result.code == "PROPOSED", result.model_dump()
    assert result.scheduling_run_id.startswith("SR-")
    assert result.status == "PROPOSED"
    assert result.snapshot_hash, "a proposal with no snapshot token cannot be safely applied"
    assert result.policy_version == "sprint3_constraints_v1"

    # --- run scope: section 5.1's "4 hours or close_time, whichever is sooner" -----------------
    start = datetime.fromisoformat(result.horizon.start_ts)
    end = datetime.fromisoformat(result.horizon.end_ts)
    assert start == NOW
    assert end - start == timedelta(hours=4)
    assert result.horizon.end_reason == "ROLLING_WINDOW"

    diff = result.diff
    counts = result.counts
    assert counts == diff.counts
    total = sum(counts.values())
    assert total == len(result.input_snapshot["jobs"]), (
        "every job in the input snapshot must appear in exactly one bucket of the diff"
    )
    assert total > 0, "the seeded horizon produced no jobs -- the fixture assumption is broken"

    # --- the block really forced movement ------------------------------------------------------
    assert counts["moved"] > 0, "a dock out of service across the horizon moved nothing"
    for view in diff.moved:
        assert view.previous_slot_id and view.previous_start_ts
        assert view.slot_id != view.previous_slot_id
        assert view.delta_minutes is not None
    # Nothing may be placed on the dock that is out of service -- Stage 1's DOCK_UNAVAILABLE, via
    # the same `evaluate_candidate_slot` the driver path uses.
    placed = [*diff.moved, *diff.newly_placed, *[u for u in diff.unchanged if not u.pinned]]
    assert all(view.dock_id != BLOCKED_DOCK for view in placed)

    # --- NFR-006, at proposal time: the plan itself must not double-book a dock ----------------
    by_dock: dict[str, list[tuple[datetime, datetime]]] = {}
    for view in placed:
        window = (
            datetime.fromisoformat(view.claim_start_ts),
            datetime.fromisoformat(view.claim_end_ts),
        )
        for other in by_dock.setdefault(view.dock_id, []):
            assert not (window[0] < other[1] and other[0] < window[1]), (
                f"proposal double-books {view.dock_id}: {window} overlaps {other}"
            )
        by_dock[view.dock_id].append(window)

    # --- the objective: every term present, and the sum being the sum --------------------------
    obj = result.objective
    assert obj.total_cost == (
        obj.lateness_cost + obj.waiting_cost + obj.fallback_dock_cost
        + obj.churn_cost + obj.fairness_cost
    )
    assert obj.churn_count <= obj.promises_moved == counts["moved"]
    assert obj.churn_cost == obj.churn_count * obj.coefficients["P_churn"]
    # D7 ships disabled, so the fairness term is arithmetically absent and section 5.1's four-term
    # formula is what actually ran.
    assert obj.coefficients["w_fairness"] == 0 and obj.fairness_cost == 0
    # Section 5 Stage 2 / D7: "stamp the version onto every decision."
    assert obj.policy_version == result.policy_version
    assert obj.coefficients["wait_per_minute"] == 6
    assert obj.coefficients["fallback_dock"] == 25
    assert obj.coefficients["P_churn"] == 30
    assert obj.coefficients["churn_epsilon_minutes"] == 15

    # --- section 5.1's own rendering -----------------------------------------------------------
    assert f"Unchanged {counts['unchanged']}" in result.explanation
    assert f"Moved {counts['moved']}" in result.explanation
    assert "promises moved" in result.explanation

    # --- the run really is a row --------------------------------------------------------------
    async with work_sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, trigger_reason, requested_by_user_id, escalation_id, "
                    "policy_version, snapshot_hash FROM public.scheduling_runs "
                    "WHERE scheduling_run_id = :id"
                ),
                {"id": result.scheduling_run_id},
            )
        ).mappings().first()
    assert row["status"] == "PROPOSED"
    assert row["trigger_reason"] == "PLANNER_REQUESTED"
    assert row["requested_by_user_id"] == PLANNER_USER
    assert row["escalation_id"] is None  # a planner-requested run carries no incident link
    assert row["snapshot_hash"] == result.snapshot_hash

    # --- NFR-007, against a real cluster -------------------------------------------------------
    # "same snapshot + policy version -> byte-identical ... sequencer proposal." Asserted by running
    # the whole scope build and search twice against the same committed state, rather than by
    # proposing twice (which section 5.1's own debounce rule forbids). Section 5.1 step 5's
    # deterministic tie-break is what buys it; dictionary iteration order is not evidence.
    async with work_sessionmaker() as session:
        coeff = sequencer.Coefficients.from_policy()
        first_scope = await sequencer.build_scope(session, facility_id=FACILITY, now=NOW)
        first = sequencer._search(first_scope, coeff)
        second_scope = await sequencer.build_scope(session, facility_id=FACILITY, now=NOW)
        second = sequencer._search(second_scope, coeff)
    assert {k: (v.slot_id, v.dock_id, v.total) for k, v in first.items()} == {
        k: (v.slot_id, v.dock_id, v.total) for k, v in second.items()
    }
    assert (
        sequencer.build_diff(first_scope, first).model_dump()
        == sequencer.build_diff(second_scope, second).model_dump()
    )

    record_evidence(
        "12. NFR-007 determinism on a real cluster",
        f"two full scope builds + searches over the same committed state produced identical "
        f"placements for {len(first)} job(s)",
    )
    record_evidence(
        "12. propose: section 5.1 diff",
        f"{result.scheduling_run_id} | unchanged {counts['unchanged']} · moved {counts['moved']} · "
        f"newly placed {counts['newly_placed']} · unplaceable {counts['unplaceable']}",
    )
    record_evidence(
        "12. propose: objective (section 5.1 / D7)",
        f"total {obj.total_cost} = lateness {obj.lateness_cost} + waiting {obj.waiting_cost} + "
        f"dock {obj.fallback_dock_cost} + churn {obj.churn_cost} (P_churn x {obj.churn_count}) + "
        f"fairness {obj.fairness_cost}; waiting delta {obj.waiting_minutes_delta} min",
    )


# ---------------------------------------------------------------------------------------------
# 2. RUN_ALREADY_ACTIVE -- section 5.1's debounce, decided by the database
# ---------------------------------------------------------------------------------------------


async def test_a_second_proposal_for_one_facility_is_refused_by_the_partial_unique_index(
    work_sessionmaker,
):
    """Section 5.1: *"allow **at most one active run per facility** (serialised). Without this,
    plan stability is theoretical."* Section 7.5.3 gives it a return value.

    The refusal is the **index's**, not a pre-check's: `insert_proposed_run` uses
    `ON CONFLICT (facility_id) WHERE status = 'PROPOSED' DO NOTHING`, so two coordinators pressing
    the button in the same second produce exactly one run with no SELECT-then-INSERT window between
    them. Proved by counting rows, and by the refusal naming the incumbent.
    """
    async with work_sessionmaker() as session:
        before = await session.scalar(
            text(
                "SELECT count(*) FROM public.scheduling_runs "
                "WHERE facility_id = :f AND status = 'PROPOSED'"
            ),
            {"f": FACILITY},
        )
    assert before == 1, "test 1 should have left exactly one live proposal"

    async with work_sessionmaker() as session:
        refused = await _propose(session)

    assert refused.code == "RUN_ALREADY_ACTIVE"
    assert refused.active_run is not None
    assert refused.active_run["status"] == "PROPOSED"
    assert refused.scheduling_run_id == refused.active_run["scheduling_run_id"]
    # A typed refusal that does not say WHICH run is in the way would send the planner hunting.
    assert refused.active_run["counts"]["moved"] >= 1

    async with work_sessionmaker() as session:
        after = await session.scalar(
            text(
                "SELECT count(*) FROM public.scheduling_runs "
                "WHERE facility_id = :f AND status = 'PROPOSED'"
            ),
            {"f": FACILITY},
        )
    assert after == 1, "the refused proposal still wrote a row"
    record_evidence(
        "12. RUN_ALREADY_ACTIVE (section 5.1 debounce)",
        f"2 proposals requested -> 1 row, refusal names {refused.scheduling_run_id}",
    )


# ---------------------------------------------------------------------------------------------
# 3. get_scheduling_run -- replayable a month later
# ---------------------------------------------------------------------------------------------


async def test_the_stored_run_replays_identically_through_get_scheduling_run(work_sessionmaker):
    """Section 7.5.3: *"The stored run: input snapshot, proposal, objective values, explanation --
    replayable a month later, which is what makes section 8's 'how the business can trust the
    allocation' answerable."*

    Asserted as an equality against the object `propose` returned, not as a shape check: a replay
    that returned a *similar* proposal would be worse than none, because a planner would apply
    something they never reviewed (D5).
    """
    async with work_sessionmaker() as session:
        run_id = await session.scalar(
            text(
                "SELECT scheduling_run_id FROM public.scheduling_runs "
                "WHERE facility_id = :f AND status = 'PROPOSED'"
            ),
            {"f": FACILITY},
        )
        replay = await sequencer.get_scheduling_run(session, _planner(), run_id)
        # The agent may READ a proposal to explain it (section 7.5.3), so an ops persona resolves
        # it too -- through the run's own facility, never a supplied one.
        ops_replay = await sequencer.get_scheduling_run(session, _ops(), run_id)

    assert replay.scheduling_run_id == run_id
    assert replay.status == "PROPOSED"
    assert replay.diff.model_dump() == ops_replay.diff.model_dump()
    assert replay.objective.model_dump() == ops_replay.objective.model_dump()
    assert replay.snapshot_hash == ops_replay.snapshot_hash
    assert replay.explanation == ops_replay.explanation
    assert replay.input_snapshot["jobs"], "the input snapshot did not survive the round trip"
    assert replay.horizon.end_reason == "ROLLING_WINDOW"
    record_evidence(
        "12. get_scheduling_run replay",
        f"{run_id} replayed byte-identically for planner and ops personas "
        f"({len(replay.input_snapshot['jobs'])} jobs in the stored input snapshot)",
    )


# ---------------------------------------------------------------------------------------------
# 4. SNAPSHOT_DRIFT -- section 5.1's second apply rule
# ---------------------------------------------------------------------------------------------


async def test_snapshot_drift_bites_when_capacity_moves_between_propose_and_apply(
    work_sessionmaker,
):
    """Section 5.1: *"Drivers keep booking while the planner reviews, so the proposal carries a
    `snapshot_hash`; on apply, revalidate and re-run on drift."*

    The drift injected is the realistic one: a shipment in the run's own job set has its appointment
    cancelled by somebody else while the planner reads the proposal. That changes the job set's
    membership, so the recomputed digest differs -- and the proposal is refused **before any
    capacity write**, which is measured rather than asserted.
    """
    async with work_sessionmaker() as session:
        run_id = await session.scalar(
            text(
                "SELECT scheduling_run_id FROM public.scheduling_runs "
                "WHERE facility_id = :f AND status = 'PROPOSED'"
            ),
            {"f": FACILITY},
        )
        run = await runs_repo.get_run(session, scheduling_run_id=run_id)
        stored_hash = run["snapshot_hash"]
        victim = run["proposal_json"]["moved"][0]["appointment_id"]

    # --- somebody else acts on the capacity the proposal was computed against -----------------
    async with work_sessionmaker() as session:
        before = await _capacity_fingerprint(session)
        await session.execute(
            text(
                """
                UPDATE public.appointments
                   SET appointment_status = 'CANCELLED', cancelled_at = now(),
                       cancellation_reason = 'proof part 12 drift injection'
                 WHERE appointment_id = :a
                """
            ),
            {"a": victim},
        )
        await session.execute(
            text("DELETE FROM public.dock_occupancy WHERE appointment_id = :a"), {"a": victim}
        )
        await session.commit()
        mutated = await _capacity_fingerprint(session)

    async with work_sessionmaker() as session:
        result = await sequencer.apply_schedule_proposal(
            session,
            _planner(),
            scheduling_run_id=run_id,
            snapshot_hash=stored_hash,
            idempotency_key="proof-12-drift",
            now=NOW,
        )

    assert result.code == "SNAPSHOT_DRIFT", result.model_dump()
    assert result.status == "SUPERSEDED"
    assert result.moved == 0 and result.newly_placed == 0
    assert result.notifications_enqueued == 0
    assert result.drift is not None
    assert result.drift["expected_snapshot_hash"] == stored_hash
    assert result.drift["current_snapshot_hash"] != stored_hash
    assert result.drift["supplied_matches_run"] is True

    async with work_sessionmaker() as session:
        after = await _capacity_fingerprint(session)
        status = await session.scalar(
            text("SELECT status FROM public.scheduling_runs WHERE scheduling_run_id = :id"),
            {"id": run_id},
        )
        reason = await session.scalar(
            text(
                "SELECT superseded_reason FROM public.scheduling_runs "
                "WHERE scheduling_run_id = :id"
            ),
            {"id": run_id},
        )
    # Zero capacity writes: the refusing apply changed nothing the drift injection had not already
    # changed. The run's own lifecycle DID move -- that is the one deliberate exception, so the
    # planner can request the fresh proposal Flow 9 step 4 tells them to.
    assert after == mutated, f"a refused apply wrote capacity: before={mutated} after={after}"
    assert after != before  # sanity: the drift injection itself really landed
    assert status == "SUPERSEDED" and reason == "SNAPSHOT_DRIFT"

    # Test 1's forced outage has done its job; ending it here so the two apply scenarios below each
    # start from a facility with every dock in service and create their own outage.
    async with work_sessionmaker() as session:
        await _end_block(session, "DEVT-PROOF-12A")

    record_evidence(
        "12. SNAPSHOT_DRIFT bite",
        f"{run_id}: {stored_hash[:12]}... -> {result.drift['current_snapshot_hash'][:12]}...; "
        f"0 capacity writes, run retired as SNAPSHOT_DRIFT",
    )


# ---------------------------------------------------------------------------------------------
# 5. PARTIALLY_INFEASIBLE -- section 5.1's first apply rule, bite-proven
# ---------------------------------------------------------------------------------------------


async def test_one_infeasible_placement_refuses_the_whole_apply_and_writes_nothing(
    work_sessionmaker,
):
    """Section 5.1: *"All-or-nothing per run. Partial application breaks the no-overlap and
    feasibility guarantees the run computed. Cherry-picking rows produces a schedule nobody
    validated."* Section 7.5.3: `PARTIALLY_INFEASIBLE` *"refuses entirely"*.

    The infeasibility injected is a **dock block**, and that choice is the point rather than a
    convenience: `snapshot.py` deliberately keeps dock blocks out of the digest (*"blocking one dock
    would otherwise change the digest of every outstanding row on it and mass-refuse in-flight
    confirms"*), so this reaches the apply with a **matching** snapshot and is caught by the Stage-1
    revalidation instead. That is the designed division of labour between the two guards -- the
    digest answers "did capacity membership change", the revalidation answers "is this still
    feasible" -- and this test is what proves both halves are wired.
    """
    async with work_sessionmaker() as session:
        await _clear_active_runs(session)
        forced = await _busiest_dock_in_horizon(session)
        await _block_dock(
            session, forced, event_id="DEVT-PROOF-12B1",
            start=NOW - timedelta(hours=1), end=NOW + timedelta(hours=6),
        )
        result = await _propose(session)
    assert result.code == "PROPOSED"
    run_id, snapshot_hash = result.scheduling_run_id, result.snapshot_hash
    writes = [*result.diff.moved, *result.diff.newly_placed]
    assert writes, "this scenario needs a proposal that actually writes something"
    # The dock must belong to a placement the apply will WRITE. An `unchanged` job's dock is
    # deliberately not revalidated -- the apply writes nothing for it, so a dock failing under an
    # untouched appointment strands that appointment (a capacity incident) without making this
    # proposal invalid. Refusing a good re-sequence because of it would be the wrong trade.
    target_dock = writes[0].dock_id

    try:
        async with work_sessionmaker() as session:
            before = await _capacity_fingerprint(session)
            await _block_dock(
                session, target_dock, event_id="DEVT-PROOF-12B",
                start=NOW - timedelta(hours=1), end=NOW + timedelta(hours=6),
            )

        async with work_sessionmaker() as session:
            refusal = await sequencer.apply_schedule_proposal(
                session,
                _planner(),
                scheduling_run_id=run_id,
                snapshot_hash=snapshot_hash,
                idempotency_key="proof-12-infeasible",
                now=NOW,
            )

        assert refusal.code == "PARTIALLY_INFEASIBLE", refusal.model_dump()
        assert refusal.status == "SUPERSEDED"
        assert refusal.moved == 0 and refusal.newly_placed == 0
        assert refusal.infeasible, "the refusal must name what made the proposal invalid"
        # Flow 9 step 5: "explains which constraint made the whole proposal invalid".
        assert any(row["failure_code"] == "DOCK_UNAVAILABLE" for row in refusal.infeasible)

        async with work_sessionmaker() as session:
            after = await _capacity_fingerprint(session)
        assert after == before, (
            "an apply that refuses entirely still wrote capacity -- all-or-nothing is broken:\n"
            f"before={before}\nafter={after}"
        )

        async with work_sessionmaker() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, superseded_reason FROM public.scheduling_runs "
                        "WHERE scheduling_run_id = :id"
                    ),
                    {"id": run_id},
                )
            ).mappings().first()
        assert row["status"] == "SUPERSEDED"
        assert row["superseded_reason"] == "PARTIALLY_INFEASIBLE"
    finally:
        # In a `finally` so a failing assertion above cannot leave a dock out of service for the
        # tests that follow -- which is exactly how the first run of this file produced a cascade
        # of unrelated failures.
        async with work_sessionmaker() as session:
            await _end_block(session, "DEVT-PROOF-12B")
            await _end_block(session, "DEVT-PROOF-12B1")

    record_evidence(
        "12. PARTIALLY_INFEASIBLE bite (all-or-nothing)",
        f"{run_id}: {len(refusal.infeasible)} of {len(writes)} written placement(s) refused by "
        f"{target_dock} going down -> whole apply refused, capacity fingerprint identical",
    )


# ---------------------------------------------------------------------------------------------
# 6. APPLIED -- the real write primitives, and one notification per moved driver
# ---------------------------------------------------------------------------------------------


async def test_apply_moves_promises_through_the_real_primitives_and_batches_notifications(
    work_sessionmaker,
):
    """Section 7.5.3's `APPLIED` (+ notification batch id) and section 5.1's cascade tail --
    *"planner applies -> notifications batch out."*

    Four things are proved against real rows, and each is a different way an apply could be wrong:

      1. `appointments.slot_id` really moved to the proposed slot;
      2. the D1 capacity claim really moved with it -- one `dock_occupancy` row per appointment, on
         the proposed dock, over the proposed window. A move that rewrote the appointment but not
         the claim would leave the old interval sterilised and the new one unprotected;
      3. one `notification_outbox` row per moved driver, keyed to **this run**, so a second
         re-sequence of the same truck is a second notification rather than a suppressed replay;
      4. the audit trail names the run, so "which proposal moved this truck" is a query.
    """
    async with work_sessionmaker() as session:
        await _clear_active_runs(session)
        # A **narrow** outage, covering exactly one promised slot's window rather than a whole
        # dock's day. Taking the busiest dock out for six hours strands its trucks -- with only
        # 79 slots at this facility they come back `unplaceable`, which is the honest answer but
        # not the one this scenario is about. A single-slot outage is both more realistic (a short
        # maintenance window) and surgical: exactly one promise must move, and every alternative
        # interval in the facility stays available for it to move to.
        # Writes (and leaves in place) the single-slot outage that forces the move.
        target = await _one_movable_promise_with_an_alternative(session)
        forced = str(target["dock_id"])
        result = await _propose(session)
    assert result.code == "PROPOSED"
    assert result.diff.moved, "the forced single-slot outage moved nothing -- fixture broken"
    assert any(v.appointment_id == target["appointment_id"] for v in result.diff.moved)
    run_id = result.scheduling_run_id
    expected_moves = {v.appointment_id: v for v in result.diff.moved}

    async with work_sessionmaker() as session:
        applied = await sequencer.apply_schedule_proposal(
            session,
            _planner(),
            scheduling_run_id=run_id,
            snapshot_hash=result.snapshot_hash,
            idempotency_key="proof-12-apply",
            now=NOW,
        )

    assert applied.code == "APPLIED", (applied.code, applied.infeasible, applied.drift)
    assert applied.status == "APPLIED"
    assert applied.moved == len(result.diff.moved)
    assert applied.newly_placed == len(result.diff.newly_placed)
    # Section 7.5.3: APPLIED returns a notification batch id. One apply is one batch, so it is the
    # run's own id rather than a second identifier that could disagree with it.
    assert applied.notification_batch_id == run_id

    async with work_sessionmaker() as session:
        # (1) + (2): the appointment and its claim both moved, together.
        for appointment_id, view in expected_moves.items():
            row = (
                await session.execute(
                    text(
                        """
                        SELECT a.slot_id, a.appointment_status,
                               o.dock_id, lower(o."window") AS claim_start,
                               upper(o."window") AS claim_end,
                               count(o.occupancy_id) OVER () AS claims
                          FROM public.appointments a
                          LEFT JOIN public.dock_occupancy o ON o.appointment_id = a.appointment_id
                         WHERE a.appointment_id = :a
                        """
                    ),
                    {"a": appointment_id},
                )
            ).mappings().all()
            assert len(row) == 1, f"{appointment_id} holds {len(row)} claims after one apply"
            got = row[0]
            assert got["slot_id"] == view.slot_id
            assert got["dock_id"] == view.dock_id
            assert got["claim_start"] == datetime.fromisoformat(view.claim_start_ts)
            assert got["claim_end"] == datetime.fromisoformat(view.claim_end_ts)
            # The status is deliberately untouched by a move -- see `_apply_move`'s docstring.
            assert got["appointment_status"] in {"PENDING_CONFIRMATION", "CONFIRMED"}

        # (3) one outbox row per moved driver, scoped to this run.
        outbox = (
            await session.execute(
                text(
                    """
                    SELECT related_entity_id, dedupe_key, status, title, body, event_type
                      FROM public.notification_outbox
                     WHERE event_type = 'APPOINTMENT_RESEQUENCED'
                       AND dedupe_key LIKE :scope
                     ORDER BY related_entity_id
                    """
                ),
                {"scope": f"%@{run_id}:%"},
            )
        ).mappings().all()
        assert len(outbox) == applied.notifications_enqueued
        assert applied.notifications_enqueued == applied.moved + applied.newly_placed
        # Every moved driver is told. Newly-placed jobs are told too and are a superset here --
        # their appointment ids are minted during the apply, so they are not knowable from the
        # stored proposal this test holds.
        assert set(expected_moves) <= {r["related_entity_id"] for r in outbox}
        for row in outbox:
            assert "re-sequenced" in row["body"]
            assert "Dock" in row["body"]

        # D6 for the newly-placed half: a proposal may decide WHERE a truck goes; only a human
        # confirms the promise. `_apply_new_placement` therefore writes PENDING_CONFIRMATION, never
        # CONFIRMED, and stamps the shipped `SCHEDULING_TOOL` booking source so "which of these did
        # the sequencer create" is a query rather than an audit-log join.
        for view in result.diff.newly_placed:
            created = (
                await session.execute(
                    text(
                        "SELECT appointment_status, booking_source FROM public.appointments "
                        "WHERE shipment_id = :s AND is_current = 1 "
                        "AND appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED')"
                    ),
                    {"s": view.shipment_id},
                )
            ).mappings().first()
            assert created["appointment_status"] == "PENDING_CONFIRMATION"
            assert created["booking_source"] == "SCHEDULING_TOOL"

        # (4) the audit trail joins the run to the appointment it moved.
        audited = await session.scalar(
            text(
                """
                SELECT count(*) FROM public.audit_logs
                 WHERE action_type = 'RESCHEDULE_APPOINTMENT'
                   AND new_value_json::jsonb ->> 'scheduling_run_id' = :run
                   AND new_value_json::jsonb ->> 'transition' = 'SEQUENCER_MOVED'
                """
            ),
            {"run": run_id},
        )
        assert audited == applied.moved

        run_row = (
            await session.execute(
                text(
                    "SELECT status, applied_by_user_id, applied_at, notifications_enqueued "
                    "FROM public.scheduling_runs WHERE scheduling_run_id = :id"
                ),
                {"id": run_id},
            )
        ).mappings().first()
    assert run_row["status"] == "APPLIED"
    assert run_row["applied_by_user_id"] == PLANNER_USER
    assert run_row["applied_at"] is not None
    assert run_row["notifications_enqueued"] == applied.notifications_enqueued

    # --- the replay: section 7.5 principle 3 --------------------------------------------------
    async with work_sessionmaker() as session:
        fingerprint = await _capacity_fingerprint(session)
        again = await sequencer.apply_schedule_proposal(
            session,
            _planner(),
            scheduling_run_id=run_id,
            snapshot_hash=result.snapshot_hash,
            idempotency_key="proof-12-apply",
            now=NOW,
        )
    assert again.idempotent_replay is True
    assert again.code == "APPLIED" and again.moved == applied.moved
    async with work_sessionmaker() as session:
        assert await _capacity_fingerprint(session) == fingerprint, (
            "a replayed apply wrote a second time"
        )

    async with work_sessionmaker() as session:
        await _end_block(session, "DEVT-PROOF-12C")

    record_evidence(
        "12. APPLIED (real write primitives)",
        f"{run_id}: {applied.moved} moved + {applied.newly_placed} newly placed after {forced} "
        f"went down, {applied.notifications_enqueued} outbox rows in batch "
        f"{applied.notification_batch_id}, {audited} audit rows; replay wrote nothing",
    )


# ---------------------------------------------------------------------------------------------
# 7. Issue #54 -- the ops delegate, and the link it persists
# ---------------------------------------------------------------------------------------------


async def test_the_ops_delegate_links_the_incident_to_the_run_it_produced(work_sessionmaker):
    """Section 7.5.5's `request_sequencer_proposal`: *"the `escalation_id` attached to the resulting
    `scheduling_run_id`, rather than a parallel tool -- the incident and the run stay linkable."*

    Also asserts the two guards that make it safe, because both are places where a thin delegate
    could quietly become a hole:

      * **M15.** The facility comes from the escalation's own row. A caller supplying a different
        one is refused rather than obeyed -- stricter than section 7.5.5's own wording, and the
        reading section 7.5 principle 1 requires.
      * **The lifecycle guard**, mirrored exactly in `ops_copilot._classify_actions`, so the
        co-pilot cannot recommend a button this refuses.
    """
    async with work_sessionmaker() as session:
        await _clear_active_runs(session)
        escalation_id = await session.scalar(
            text(
                "SELECT escalation_id FROM public.escalation_queue "
                "WHERE facility_id = :f ORDER BY escalation_id LIMIT 1"
            ),
            {"f": FACILITY},
        )

    # --- the guard, before the happy path: an unowned incident cannot be worked ---------------
    async with work_sessionmaker() as session:
        with pytest.raises(Exception) as exc:
            await sequencer.request_sequencer_proposal(
                session, _ops(), escalation_id=escalation_id, now=NOW
            )
        assert getattr(exc.value, "code", "") == "NOT_ACKNOWLEDGED"

    async with work_sessionmaker() as session:
        await session.execute(
            text(
                """
                UPDATE public.escalation_queue
                   SET escalation_status = 'ACKNOWLEDGED', owner_user_id = :u, updated_at = :now
                 WHERE escalation_id = :e
                """
            ),
            {"u": OPS_USER, "e": escalation_id, "now": NOW.isoformat()},
        )
        await session.commit()

    # --- M15: a supplied facility that disagrees with the incident is refused -----------------
    async with work_sessionmaker() as session:
        with pytest.raises(Exception) as exc:
            await sequencer.request_sequencer_proposal(
                session, _ops(), escalation_id=escalation_id, facility_id="FAC-GGN-01", now=NOW
            )
        assert getattr(exc.value, "code", "") in {"FORBIDDEN", "NOT_ACKNOWLEDGED"}

    async with work_sessionmaker() as session:
        result = await sequencer.request_sequencer_proposal(
            session, _ops(), escalation_id=escalation_id, now=NOW
        )

    assert result.code == "PROPOSED", result.model_dump()
    assert result.trigger_reason == "CAPACITY_INCIDENT"
    assert result.escalation_id == escalation_id
    assert result.facility_id == FACILITY

    async with work_sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT escalation_id, trigger_reason, requested_by_user_id "
                    "FROM public.scheduling_runs WHERE scheduling_run_id = :id"
                ),
                {"id": result.scheduling_run_id},
            )
        ).mappings().first()
        joined = await runs_repo.latest_run_for_escalation(session, escalation_id=escalation_id)
    assert row["escalation_id"] == escalation_id
    assert row["trigger_reason"] == "CAPACITY_INCIDENT"
    assert row["requested_by_user_id"] == OPS_USER
    # The join the ops console's handoff state renders from (Flow 4 step 4).
    assert joined["scheduling_run_id"] == result.scheduling_run_id

    record_evidence(
        "12. issue #54 delegate link",
        f"{escalation_id} -> {result.scheduling_run_id} "
        f"(trigger CAPACITY_INCIDENT, FK persisted, reverse lookup resolves)",
    )


# ---------------------------------------------------------------------------------------------
# 7b. The pending-proposals list -- a section 7.5.3 catalog addendum, and its scope rule
# ---------------------------------------------------------------------------------------------


async def test_the_pending_run_list_is_scoped_and_finds_the_ops_handoff_run(work_sessionmaker):
    """`03-planner-dock-board/screens.md` section 3's `[ Review proposal (N) ]` count, and Flow 9's
    ops-handoff origin.

    Section 7.5.3 defines three tools and none of them is a list, which is a real gap rather than a
    reason not to build one: Flow 9 says the button *"goes from Inactive-with-`(0)` to active the
    moment either origin produces a `scheduling_run_id`"*, and the **ops-handoff** origin creates
    the run on a different surface -- so the planner board has no id to `get` and no way to learn
    one except by asking. Recorded as a catalog addendum, not folded in silently.

    The M15 assertion is the one that matters here: `facility_id` is a narrowing request, so a
    facility-scoped coordinator naming somebody else's building is refused rather than served.
    """
    async with work_sessionmaker() as session:
        pending = await sequencer.list_scheduling_runs(session, _planner(), facility_id=FACILITY)
        applied = await sequencer.list_scheduling_runs(
            session, _planner(), facility_id=FACILITY, status="APPLIED"
        )
        derived = await sequencer.list_scheduling_runs(session, _planner())

    # Test 7 left exactly one live proposal, and it is the ops-handoff one.
    assert pending.count == 1
    row = pending.runs[0]
    assert row.status == "PROPOSED"
    assert row.trigger_reason == "CAPACITY_INCIDENT"
    assert row.escalation_id is not None
    assert set(row.counts) == {"unchanged", "moved", "newly_placed", "unplaceable"}
    assert row.explanation
    # Omitting `facility_id` resolves to the caller's own facility, never "all" (M15).
    assert derived.facility_id == FACILITY
    assert [r.scheduling_run_id for r in derived.runs] == [row.scheduling_run_id]
    # Test 6's applied run is findable under the audit filter section 8 asks for.
    assert applied.count >= 1 and all(r.status == "APPLIED" for r in applied.runs)

    async with work_sessionmaker() as session:
        with pytest.raises(Exception) as exc:
            await sequencer.list_scheduling_runs(
                session, _planner(), facility_id="FAC-GGN-01"
            )
        assert getattr(exc.value, "code", "") == "FORBIDDEN"

    record_evidence(
        "12. pending-run list (section 7.5.3 addendum)",
        f"{pending.count} PROPOSED at {FACILITY} (ops-handoff run {row.scheduling_run_id}, "
        f"escalation {row.escalation_id}); cross-facility request refused FORBIDDEN",
    )


# ---------------------------------------------------------------------------------------------
# 8. The lazy supersede -- how an unapplied proposal stops blocking a facility
# ---------------------------------------------------------------------------------------------


async def test_a_proposal_whose_horizon_has_passed_stops_blocking_the_next_one(work_sessionmaker):
    """The constraint-versus-clock asymmetry, again -- and the reason `RUN_ALREADY_ACTIVE` is not a
    trap.

    `scheduling_runs_active_per_facility_uidx` is `WHERE status = 'PROPOSED'` and cannot carry a
    time term, so an expired proposal would go on refusing every new one until something wrote to
    it. `supersede_expired_runs` flips it lazily inside the next propose's transaction -- the same
    fix issue #97 applied to lapsed D2 holds under the `dock_occupancy` exclusion constraint, reused
    rather than reinvented.

    Test 7 left a live proposal whose horizon ends at NOW+4h; proposing again four hours later must
    therefore succeed, and must retire the old one with the reason stated.
    """
    async with work_sessionmaker() as session:
        stale = await session.scalar(
            text(
                "SELECT scheduling_run_id FROM public.scheduling_runs "
                "WHERE facility_id = :f AND status = 'PROPOSED'"
            ),
            {"f": FACILITY},
        )
    assert stale, "test 7 should have left a live proposal"

    later = NOW + timedelta(hours=5)
    async with work_sessionmaker() as session:
        fresh = await _propose(session, now=later)

    assert fresh.code == "PROPOSED", fresh.model_dump()
    assert fresh.scheduling_run_id != stale

    async with work_sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, superseded_reason FROM public.scheduling_runs "
                    "WHERE scheduling_run_id = :id"
                ),
                {"id": stale},
            )
        ).mappings().first()
        live = await session.scalar(
            text(
                "SELECT count(*) FROM public.scheduling_runs "
                "WHERE facility_id = :f AND status = 'PROPOSED'"
            ),
            {"f": FACILITY},
        )
        await _clear_active_runs(session)

    assert row["status"] == "SUPERSEDED"
    assert row["superseded_reason"] == "HORIZON_PASSED"
    assert live == 1, "the facility must never hold two live proposals"
    record_evidence(
        "12. lazy supersede of an expired proposal",
        f"{stale} retired as HORIZON_PASSED; {fresh.scheduling_run_id} took the slot",
    )
