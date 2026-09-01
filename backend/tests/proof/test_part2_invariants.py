"""Section 10 part 2 -- the six invariant queries, run against the shipped seed.

Design citation: `SOLUTION_DESIGN.md` section 10.2; section 6.2 #7 (the two known weight
violations); section 6.2 #9 (`slot_status` and `dock_status_events` disagree in the shipped data);
section 5 Stage 1 (rule absence is permission). GitHub issue #44.

**The expected result of each query is declared here, not discovered.** Section 10.2's whole point
is that the invariants return *exactly* a known set, so an assertion of "0 or the known two" is the
test; an assertion of "whatever it returned last time" would be a snapshot, not an invariant.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.proof.evidence import record_evidence
from tests.proof.invariants import (
    ACTIVE_APPOINTMENT_STATUSES,
    CAPACITY_CONSUMING_STATES,
    INVARIANTS,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# Section 6.2 #7's table, transcribed. These are the only violations section 10.2 permits.
KNOWN_WEIGHT_VIOLATIONS = {
    ("APT1005", "SHP1005", 20500, "DOCK-JAI-D3", 20000),
    ("APT1014A", "SHP1014", 21000, "DOCK-JAI-D1", 20000),
}


async def _run(session, name: str) -> list[dict]:
    rows = (
        await session.execute(
            text(INVARIANTS[name]),
            {
                "capacity_states": list(CAPACITY_CONSUMING_STATES),
                "active_statuses": list(ACTIVE_APPOINTMENT_STATUSES),
            },
        )
    ).mappings().all()
    violations = [dict(row) for row in rows]
    record_evidence(f"2. invariants: {name}", f"{len(violations)} violation(s)")
    return violations


async def test_inv1_no_overlapping_dock_occupancy(seed_session):
    """The headline invariant. D1's GiST exclusion constraint should make this unfalsifiable.

    Zero rather than "the backfill's known conflicts": migration 20260823060000 routes an
    overlapping backfill row to the D12 `REQUIRES_TIME_RESOLUTION` worklist *instead of* inserting
    it, so a conflicting appointment never becomes a conflicting occupancy row. That is the design
    working, and it is asserted separately below.
    """
    violations = await _run(seed_session, "inv1_no_overlapping_dock_occupancy")
    assert violations == [], f"D1's exclusion constraint was violated: {violations}"


async def test_inv1_the_constraint_that_makes_it_unfalsifiable_actually_exists(seed_session):
    """A zero-row query proves nothing if the constraint behind it was never created.

    Asserts the partial GiST exclusion constraint by name and by predicate, because
    `allocation.ALLOCATION_CONFLICT_CONSTRAINTS` matches on that exact string to turn a race into
    `SLOT_CONFLICT_REFRESH_REQUIRED` rather than a 500.
    """
    row = (
        await seed_session.execute(
            text(
                """
                SELECT conname, contype, pg_get_constraintdef(oid) AS definition
                FROM pg_constraint
                WHERE conrelid = 'public.dock_occupancy'::regclass
                  AND conname = 'dock_occupancy_dock_id_window_excl'
                """
            )
        )
    ).mappings().first()
    assert row is not None, "dock_occupancy_dock_id_window_excl is missing"
    # `pg_constraint.contype` is PostgreSQL's internal `"char"` type; asyncpg hands it back as
    # bytes, not str. Normalised rather than compared to b'x' so the assertion reads as the domain
    # fact it is ("this is an EXCLUDE constraint"), not as a driver detail.
    contype = row["contype"]
    contype = contype.decode() if isinstance(contype, (bytes, bytearray)) else str(contype)
    assert contype == "x", "the constraint exists but is not an EXCLUDE constraint"
    definition = " ".join(str(row["definition"]).split())
    normalised = definition.replace('"', "").lower()
    assert "using gist" in normalised, definition
    assert "dock_id with =" in normalised, definition
    assert "window with &&" in normalised, definition
    for state in CAPACITY_CONSUMING_STATES:
        assert state.lower() in normalised, f"{state} is not in the exclusion predicate: {definition}"
    # A partial exclusion constraint, not a total one -- that WHERE clause is what lets the M8
    # sweeper flip a lapsed hold to EXPIRED in place instead of deleting it (migration
    # 20260829134929's own header block).
    assert " where " in normalised, f"the exclusion constraint has no state predicate: {definition}"


async def test_inv2_no_shipment_with_more_than_one_active_appointment(seed_session):
    violations = await _run(seed_session, "inv2_no_shipment_with_two_active_appointments")
    assert violations == [], f"a shipment holds more than one live claim: {violations}"


# Measured against the shipped seed, 2026-09-01, PostgreSQL 18.3. Every one of these three is a
# DELIBERATE seeded fixture, named in the database guide's own section 6 case table:
#   * APT1005 / DEVT001 -- section 6.2 #9's D3 case. The guide's "Dock breakdown" row
#     (`SHP1005 / DEVT001`) exists precisely so a CONFIRMED appointment becomes infeasible; the
#     design says so in as many words: "SLOT-JAI-030 (09:00-10:00) is still OPEN, overlaps the
#     outage, and is exactly where APT1005 sits -- which is how the seeded SHP1005 stranding case
#     arises."
#   * APT1002 / DEVT003 -- the guide's "Unload overrun" row (`SHP1002 / DEVT003`). The overrun IS
#     the D2 capacity-reduction event overlapping the truck's own in-progress slot.
#   * APT1004 / DEVT003 -- the downstream truck the overrun delays, i.e. the guide's "Late arrival
#     already at yard" case (`SHP1004 / THR008`) seen from the dock's side.
KNOWN_OUTAGE_OVERLAPS = {
    ("APT1002", "DEVT003"),
    ("APT1004", "DEVT003"),
    ("APT1005", "DEVT001"),
}


async def test_inv3_active_appointments_over_a_dock_outage_are_exactly_the_seeded_fixtures(
    seed_session,
):
    """Section 10.2: "No confirmed appointment overlaps a `dock_status_events` outage window."

    **This invariant is FALSE against the shipped seed, by design, in three places** -- and the
    three are the seeded cases the scenario replay in part 4 depends on existing. So the assertion
    here is a set equality against the documented three, exactly the instrument section 10.2 itself
    prescribes for the weight invariant ("must return exactly the two known violations ... and
    nothing else"). It is not a softening: an extra overlap fails, and a *missing* one fails too,
    because a vanished fixture would silently gut the dock-breakdown and unload-overrun scenarios.

    The literal zero-row form of section 10.2's sentence is asserted separately, below, as a strict
    xfail -- so the contradiction between the design's wording and the shipped data is visible on
    every run rather than quietly resolved here.
    """
    violations = await _run(seed_session, "inv3_no_active_appointment_over_a_dock_outage")
    observed = {(str(row["appointment_id"]), str(row["dock_event_id"])) for row in violations}
    record_evidence("2. invariants: inv3 rows returned", sorted(observed))
    assert observed == KNOWN_OUTAGE_OVERLAPS, (
        "live appointments overlapping a dock event are not the documented seeded set.\n"
        f"  unexpected: {sorted(observed - KNOWN_OUTAGE_OVERLAPS)}\n"
        f"  missing:    {sorted(KNOWN_OUTAGE_OVERLAPS - observed)}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "OPEN DESIGN CONTRADICTION, reported not fixed (issue #44). Section 10.2 states "
        "'No confirmed appointment overlaps a dock_status_events outage window' as an "
        "unqualified invariant, but the shipped seed contains three such overlaps ON PURPOSE -- "
        "they are the database guide section 6's own 'Dock breakdown' (SHP1005/DEVT001, and "
        "section 6.2 #9 names it explicitly), 'Unload overrun' (SHP1002/DEVT003) and the "
        "downstream truck it delays (SHP1004). Either section 10.2 needs the same 'exactly the "
        "known violations' carve-out it already gives the weight invariant, or the seed's "
        "breakdown/overrun fixtures have to go. This xfail is strict, so it fails loudly the "
        "moment either side changes."
    ),
)
async def test_inv3_literal_section_10_2_wording_zero_overlaps(seed_session):
    violations = await _run(seed_session, "inv3_no_active_appointment_over_a_dock_outage")
    assert violations == [], (
        "a live appointment sits inside a dock outage window "
        f"({len(violations)} row(s)): {violations}"
    )


async def test_inv4_no_late_start_without_a_recorded_approval(seed_session):
    """Only at facilities that define LAST_NEW_START_TIME -- FAC-GGN-01 does not."""
    violations = await _run(seed_session, "inv4_no_late_start_without_approval")
    assert violations == [], f"unapproved post-cutoff start: {violations}"


async def test_inv4_absent_rule_is_unrestricted_not_inherited(seed_session):
    """The invariant's own scoping, proved rather than asserted in a comment.

    Section 5 Stage 1: "an absent rule is unrestricted". FAC-GGN-01 must have no
    LAST_NEW_START_TIME row -- if it ever gains one, invariant 4 starts constraining a facility the
    design says is unconstrained, and this test is what says so out loud.
    """
    rows = (
        await seed_session.execute(
            text(
                """
                SELECT facility_id, count(*) AS n
                FROM public.facility_rules
                WHERE rule_type = 'LAST_NEW_START_TIME' AND active_flag = 1
                GROUP BY facility_id
                """
            )
        )
    ).mappings().all()
    defining = {str(row["facility_id"]) for row in rows}
    assert "FAC-JAI-01" in defining, "the facility that defines the rule no longer does"
    assert "FAC-GGN-01" not in defining, (
        "FAC-GGN-01 gained a LAST_NEW_START_TIME rule; section 10.2's carve-out no longer describes "
        "the data"
    )


async def test_inv5_every_reefer_load_sits_on_a_refrigerated_dock(seed_session):
    violations = await _run(seed_session, "inv5_every_reefer_load_on_a_refrigerated_dock")
    assert violations == [], f"a temperature-controlled load is on a non-reefer dock: {violations}"


async def test_inv6_returns_exactly_the_two_known_section_6_2_7_violations(seed_session):
    """Section 10.2's one non-zero expectation, asserted as a set equality in both directions.

    A missing row means the seed drifted and the known defect vanished (which would silently delete
    a fixture other tests rely on); an extra row means a NEW violation appeared. Both are failures,
    which is why this is `==` on a set and not `>=` or a count.
    """
    violations = await _run(seed_session, "inv6_no_load_over_its_dock_weight_limit")
    observed = {
        (
            str(row["appointment_id"]),
            str(row["shipment_id"]),
            int(row["load_weight_kg"]),
            str(row["dock_id"]),
            int(row["max_vehicle_weight_kg"]),
        )
        for row in violations
    }
    record_evidence(
        "2. invariants: inv6 rows returned",
        sorted(f"{a} ({s_} {w} kg > {d} {m} kg)" for a, s_, w, d, m in observed),
    )
    assert observed == KNOWN_WEIGHT_VIOLATIONS, (
        "section 10.2 requires exactly the two known section 6.2 #7 violations.\n"
        f"  unexpected: {sorted(observed - KNOWN_WEIGHT_VIOLATIONS)}\n"
        f"  missing:    {sorted(KNOWN_WEIGHT_VIOLATIONS - observed)}"
    )


async def test_inv6_both_violations_reached_the_d12_worklist(seed_session):
    """D15/D12: a weight violation "needs a *different dock*, not a different hour", so both rows
    "enter the D12 worklist as `REQUIRES_DOCK_REASSIGNMENT` for planner action".

    This is the other half of invariant 6 and it is the half that proves nothing was silently
    fixed: the violation is still in the data (above) *and* a human has been told about it.
    """
    rows = (
        await seed_session.execute(
            text(
                """
                SELECT escalation_id, shipment_id, escalation_status, payload_json
                FROM public.escalation_queue
                WHERE escalation_type = 'REQUIRES_DOCK_REASSIGNMENT'
                ORDER BY escalation_id
                """
            )
        )
    ).mappings().all()
    escalated_shipments = {str(row["shipment_id"]) for row in rows}
    assert escalated_shipments == {"SHP1005", "SHP1014"}, (
        f"D12 dock-reassignment worklist does not match the known violations: {escalated_shipments}"
    )
    assert all(str(row["escalation_status"]) == "OPEN" for row in rows), (
        "a backfill worklist item was created already-closed"
    )


async def test_the_d12_time_resolution_worklist_matches_the_section_6_2_1_overruns(seed_session):
    """Section 6.2 #1's four over-running appointments, and where the backfill put them.

    Not one of section 10.2's six, but it is the assertion that keeps invariant 1 honest: invariant
    1 can only be zero because the backfill *declined* to insert the conflicting rows, so the count
    of what it declined has to be checked somewhere or "no overlaps" degenerates into "no data".
    """
    rows = (
        await seed_session.execute(
            text(
                """
                SELECT shipment_id, payload_json
                FROM public.escalation_queue
                WHERE escalation_type = 'REQUIRES_TIME_RESOLUTION'
                ORDER BY escalation_id
                """
            )
        )
    ).mappings().all()
    claims = await seed_session.scalar(text("SELECT count(*) FROM public.dock_occupancy"))
    active = await seed_session.scalar(
        text(
            """
            SELECT count(*) FROM public.appointments
            WHERE appointment_status = ANY(:active_statuses)
            """
        ),
        {"active_statuses": list(ACTIVE_APPOINTMENT_STATUSES)},
    )
    # Every active appointment either got a claim or got a time-resolution worklist item; the two
    # numbers must add up exactly, or the backfill lost a booking.
    record_evidence(
        "2. invariants: D1 backfill accounting",
        f"{claims} dock_occupancy claims + {len(rows)} REQUIRES_TIME_RESOLUTION "
        f"= {active} active appointments",
    )
    assert int(claims) + len(rows) == int(active), (
        f"backfill accounting does not balance: {claims} claims + {len(rows)} deferred "
        f"!= {active} active appointments"
    )
