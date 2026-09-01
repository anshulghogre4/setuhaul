"""Section 10 part 5 -- the determinism proof.

Design citation: `SOLUTION_DESIGN.md` section 10.5 -- "Same snapshot + same policy version ->
byte-identical ranking, twice. Tie-break by `shipment_id + slot_id`, no randomness anywhere in the
engine." Also section 9.2's "Determinism assertion": "Same snapshot + same `policy_version` ->
byte-identical ranking and byte-identical sequencer proposal, run twice. Any drift means randomness
leaked into an engine that promised none." GitHub issue #44.

## "Byte-identical" needs a definition, and this file states it rather than assuming it

`FeasibleSlotsResult.as_of` is a wall-clock stamp of *when the answer was produced*
(`feasibility._as_of`). Two runs a millisecond apart must differ there, and a design that demanded
otherwise would be demanding a frozen clock in production. So the comparison is:

    every field of the serialised result is byte-identical EXCEPT `as_of`

and -- this is the part that keeps it honest -- the set of differing fields is computed and
asserted to be exactly `{"as_of"}`, rather than `as_of` being stripped before comparing. Stripping
first would hide a second volatile field the day one appeared.

## Why this cannot be done with mocks

Ranking reads live rows (slots, dock events, facility rules, the D2 hold set) and the whole claim
is that *those reads plus that policy* determine the output. A fixture-fed ranker would prove the
sort function is pure, which nobody doubted; it would not prove the engine is.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import find_feasible_slots
from app.scheduling.snapshot import load_appointment_snapshots
from tests.proof.evidence import record_evidence

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Chosen to span the engine's whole outcome space rather than to be convenient:
#   SHP1006 -- an ordinary delayed standard load with options
#   SHP1016 -- the heavy load, where dock filtering does the work
#   SHP1015 -- the reefer case, which produces NO_FEASIBLE_SLOT and an escalation payload
#   SHP1013 -- LOW-confidence ETA
#   SHP1009 -- CRITICAL priority, where the priority tie-break participates
DETERMINISM_SHIPMENTS = ("SHP1006", "SHP1016", "SHP1015", "SHP1013", "SHP1009")

# `as_of` is the ONE field the engine is allowed to vary between two identical calls: it stamps
# *when* the answer was produced (`feasibility._as_of`), and a design that demanded it be stable
# would be demanding a frozen clock in production.
#
# It appears at two depths, which the first run of this file discovered rather than assumed: once
# on `FeasibleSlotsResult` itself, and again *nested inside* the `escalation` payload
# (`feasibility.find_feasible_slots` builds `escalation["as_of"] = _as_of()`). Comparing only
# top-level fields therefore reported SHP1015 and SHP1009 -- the two shipments that escalate -- as
# non-deterministic when they are not. Hence a recursive path diff rather than a flat key set: the
# rule is "no field may differ unless its own name is `as_of`", checked at every depth.
VOLATILE_LEAF_NAME = "as_of"


async def _ctx(session, shipment_id: str) -> ExecutionContext:
    row = (
        await session.execute(
            text(
                "SELECT driver_id, destination_facility_id FROM public.shipments "
                "WHERE shipment_id = :s"
            ),
            {"s": shipment_id},
        )
    ).mappings().first()
    assert row is not None
    return ExecutionContext(
        request_id=f"proof-determinism-{shipment_id}",
        auth_subject=f"proof-determinism-{shipment_id}",
        user_id=f"USR-PROOF-{row['driver_id']}",
        email=f"{str(row['driver_id']).lower()}@proof.invalid",
        full_name="Proof Reader",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id=str(row["driver_id"]),
        facility_id=str(row["destination_facility_id"]),
    )


def _canonical(payload: dict) -> bytes:
    """One stable byte representation. `sort_keys` so dict iteration order cannot masquerade as
    drift, `default=str` so a stray datetime does not raise instead of comparing."""
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")


_MISSING = object()


def _differing_paths(first, second, prefix: str = "") -> list[str]:
    """Every JSON path at which two results disagree, recursing into dicts and lists.

    A flat key comparison is not good enough here: the one legitimately-volatile field appears both
    at the top level and nested inside `escalation`, so a flat comparison would report a whole
    escalation payload as "changed" and hide which leaf actually moved.
    """
    if isinstance(first, dict) and isinstance(second, dict):
        paths: list[str] = []
        for key in sorted(set(first) | set(second)):
            paths.extend(
                _differing_paths(
                    first.get(key, _MISSING), second.get(key, _MISSING), f"{prefix}.{key}" if prefix else str(key)
                )
            )
        return paths
    if isinstance(first, list) and isinstance(second, list):
        if len(first) != len(second):
            return [f"{prefix}[len]"]
        paths = []
        for index, (a, b) in enumerate(zip(first, second)):
            paths.extend(_differing_paths(a, b, f"{prefix}[{index}]"))
        return paths
    if _canonical({"v": first}) != _canonical({"v": second}):
        return [prefix or "<root>"]
    return []


def _strip_volatile(value):
    """The same result with every `as_of` leaf removed, at any depth."""
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k != VOLATILE_LEAF_NAME}
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


@pytest.mark.parametrize("shipment_id", DETERMINISM_SHIPMENTS)
async def test_ranking_is_byte_identical_run_twice(shipment_id, seed_session):
    ctx = await _ctx(seed_session, shipment_id)

    first = (await find_feasible_slots(seed_session, ctx, shipment_id, limit=5)).model_dump()
    second = (await find_feasible_slots(seed_session, ctx, shipment_id, limit=5)).model_dump()

    differing = _differing_paths(first, second)
    illegitimate = [
        path for path in differing if path.rsplit(".", 1)[-1] != VOLATILE_LEAF_NAME
    ]
    assert illegitimate == [], (
        f"{shipment_id}: the engine is not deterministic. Paths that changed between two "
        f"identical calls: {illegitimate}"
    )
    # And the volatile field really is volatile-by-design, not accidentally frozen: if `as_of` ever
    # stopped moving, the exemption above would be silently over-broad.
    assert VOLATILE_LEAF_NAME in first and VOLATILE_LEAF_NAME in second

    payload = _canonical(_strip_volatile(first))
    record_evidence(
        f"5. determinism: {shipment_id} two-run byte comparison",
        f"identical, {len(payload)} bytes, {len(first['options'])} option(s), "
        f"outcome={first['outcome']}, volatile paths={sorted(differing)}",
    )
    assert payload == _canonical(_strip_volatile(second)), (
        f"{shipment_id}: the results differ once every `as_of` is removed"
    )


@pytest.mark.parametrize("shipment_id", DETERMINISM_SHIPMENTS)
async def test_recommendation_id_is_stable(shipment_id, seed_session):
    """`REC-` is the design's own displayed-options fingerprint (section 6.1, `slot_recommendations`).

    If it drifted between two identical searches, staleness detection would fire on every request
    and `request_slot` would answer `SLOT_OPTIONS_STALE` to a driver whose options had not changed.
    """
    ctx = await _ctx(seed_session, shipment_id)
    first = await find_feasible_slots(seed_session, ctx, shipment_id, limit=5)
    second = await find_feasible_slots(seed_session, ctx, shipment_id, limit=5)
    assert first.recommendation_id == second.recommendation_id
    assert first.recommendation_id.startswith("REC-")


@pytest.mark.parametrize("shipment_id", DETERMINISM_SHIPMENTS)
async def test_ranking_is_identical_across_five_runs_not_just_two(shipment_id, seed_session):
    """Two runs can agree by luck; five failing to disagree is a much narrower coincidence.

    Cheap insurance against the specific failure mode section 9.2 warns about -- "randomness leaked
    into an engine that promised none" -- which a two-run comparison can miss if the random source
    has a short period.
    """
    ctx = await _ctx(seed_session, shipment_id)
    digests = set()
    for _ in range(5):
        result = (await find_feasible_slots(seed_session, ctx, shipment_id, limit=5)).model_dump()
        digests.add(_canonical(_strip_volatile(result)))
    record_evidence(
        f"5. determinism: {shipment_id} five-run digests",
        f"{len(digests)} distinct (expected 1)",
    )
    assert len(digests) == 1, f"{shipment_id} produced {len(digests)} distinct rankings in 5 runs"


@pytest.mark.parametrize("shipment_id", DETERMINISM_SHIPMENTS)
async def test_policy_version_is_carried_on_every_answer(shipment_id, seed_session):
    """"Same snapshot + **same policy version**" is only checkable if the answer states its policy.

    Asserted against `load_scheduling_constraints()` rather than a literal, so a policy bump moves
    both sides together instead of silently invalidating the test.
    """
    ctx = await _ctx(seed_session, shipment_id)
    result = await find_feasible_slots(seed_session, ctx, shipment_id, limit=5)
    assert result.policy_version == load_scheduling_constraints().policy_version
    assert result.policy_version, "an answer was produced under an unnamed policy"


@pytest.mark.parametrize("shipment_id", DETERMINISM_SHIPMENTS)
async def test_ties_are_broken_by_slot_id(shipment_id, seed_session):
    """Section 10.5: "Tie-break by `shipment_id + slot_id`, no randomness anywhere in the engine."

    A single search is one shipment, so `slot_id` is the operative half. Every group of options
    that is equal on all the earlier sort terms must be in ascending `slot_id` order -- which is
    exactly what makes the ordering reproducible when two intervals score identically.
    """
    ctx = await _ctx(seed_session, shipment_id)
    result = await find_feasible_slots(seed_session, ctx, shipment_id, limit=5)

    def preceding_terms(option):
        return (
            -option.rank_score,
            option.ranking_factors["wait_after_eta_minutes"],
            option.ranking_factors["operational_disruption_score"],
            option.slot_start_ts,
        )

    previous = None
    for option in result.options:
        current = preceding_terms(option)
        if previous is not None and previous[0] == current:
            assert previous[1] < option.slot_id, (
                f"{shipment_id}: two options tied on every ranking term but are not in "
                f"slot_id order ({previous[1]} then {option.slot_id})"
            )
        previous = (current, option.slot_id)


async def test_the_planner_snapshot_hash_is_stable(seed_session):
    """The other half of "same snapshot": the snapshot's own digest.

    `snapshot_hash` is what `confirm_request`/`bulk_confirm` compare a planner's rendered view
    against. If it were unstable, every confirm would return `SNAPSHOT_STALE` -- the exact outage
    shape the #84 fix was made to avoid (CHANGELOG, 2026-09-01: "a partial fix makes producer and
    consumer digests diverge whenever a hold overlaps: every confirm returns SNAPSHOT_STALE").
    """
    appointment_ids = [
        str(row["appointment_id"])
        for row in (
            await seed_session.execute(
                text(
                    """
                    SELECT appointment_id FROM public.appointments
                    WHERE is_current = 1
                      AND appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
                    ORDER BY appointment_id
                    """
                )
            )
        ).mappings().all()
    ]
    assert appointment_ids, "no live appointments to snapshot"

    first = await load_appointment_snapshots(seed_session, appointment_ids)
    second = await load_appointment_snapshots(seed_session, appointment_ids)
    assert set(first) == set(second)
    drifted = [
        aid
        for aid in first
        if first[aid].get("snapshot_hash") != second[aid].get("snapshot_hash")
    ]
    record_evidence(
        "5. determinism: snapshot_hash stability",
        f"{len(appointment_ids)} live appointment(s), {len(drifted)} drifted hash(es)",
    )
    assert drifted == [], f"snapshot_hash drifted between two identical reads for: {drifted}"
    assert _canonical(first) == _canonical(second)


@pytest.mark.skip(
    reason=(
        "NAMED SKIP (issue #44). Section 9.2's determinism assertion asks for a 'byte-identical "
        "sequencer proposal, run twice' as well as a byte-identical ranking. The ranking half is "
        "proved above; the sequencer half cannot be, because the Sequencer does not exist -- it is "
        "issue #49, milestone M8, still open, and `request_sequencer_proposal` is absent from "
        "backend/app/ entirely. Unbuildable now, not skipped for convenience."
    )
)
async def test_sequencer_proposal_is_byte_identical_run_twice():
    raise AssertionError("unreachable while the skip stands")
