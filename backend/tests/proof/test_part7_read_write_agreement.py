"""Read/write agreement -- the regression suite for GitHub issue #97.

Design citation: `SOLUTION_DESIGN.md` §0.8 (D2: *"Expiry is lazy plus swept. Every read filters
`state='HELD' AND expires_at > now()`; a sweeper transitions stale rows to `EXPIRED`. Never depend
on the sweeper for correctness -- only for hygiene."*), §4 (*"Held != booked: no `appointments` row
exists yet"*), §5 Stage 3, §6.2 #1, D1, D2, M6, FR-SYS-006, NFR-003.

**Not a seventh part of §10.** §10 defines six parts and this is not one of them; it lives beside
them because it needs the same throwaway cluster and the same fixtures, and because the thing it
proves is the same *kind* of thing -- what PostgreSQL actually does, which no mocked session can
answer. The file is named for its position in the run order, not for a section of the design.

## What broke, and why one test would not have been enough

`find_feasible_slots` offered intervals `request_slot` then refused, on the shared dev database,
with no concurrency involved (issue #97; found by E6.2's race suites, reproduced with a single
unraced request). Two *separate* disagreements shared one root cause -- neither side had a
definition of "this dock interval is taken" that the other also used:

* **A live hold was invisible to the read.** Under the two-phase contract a `HELD` row has no
  `appointments` row at all (§4), and feasibility derived availability from `appointment_slots`
  joined to `appointments`. So an interval another driver was actively holding was offered anyway,
  and the exclusion constraint refused it a moment later.
* **A lapsed hold was invisible to the clock.** The exclusion constraint's predicate is
  `state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')` and contains no time term --
  it cannot, a constraint is evaluated against rows rather than against a clock. So a `HELD` row
  whose TTL passed went on refusing every overlapping insert. Live evidence, 2026-09-01: rows
  758/759 at `DOCK-GGN-D1`, `state='HELD'`, `expires_at` hours past, unswept, because no sweeper is
  running (the EventBridge wiring is still open on issue #20).

The two point in opposite directions -- the first offers too much, the second refuses too much --
which is why the fix is a shared predicate (`app/scheduling/occupancy.py`) rather than a patch to
whichever side was complained about. `test_a_*` and `test_b_*` below pin one direction each, and
both fail against pre-fix code.

## Why the TTL is set by hand instead of waited out

The D2 TTL is 90 seconds. A test that took a hold and then asserted "it is still live" would be
racing its own runtime, and §9.1 forbids exactly that (*"Every test must inject `now` rather than
read the wall clock, or the entire suite starts failing the day after it is written"*). So the
fixtures write `expires_at` directly: a full day out for a live hold, half an hour past for a
lapsed one. The row's *shape* is untouched and still satisfies `dock_occupancy_held_shape_check`
(`state='HELD'` with a non-NULL deadline and a NULL `appointment_id`) -- it is the same row the
production incident had, with the ambiguity of a real clock removed.

That margin, not an injected `now`, is what makes these deterministic, and it is deliberate.
`find_feasible_slots` does take an optional `now` for exactly this purpose, but passing it here
would couple the assertions to a parameter the fix itself introduced -- and a regression test that
cannot even be *called* against pre-fix code cannot demonstrate that it bites. With the deadlines a
day either side of the present, the default wall clock gives the same answer any injected instant
would, so these tests run unchanged against both revisions and fail loudly against the broken one.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling import allocation, holds, snapshot
from app.scheduling.allocation import RequestSlotCommand, request_slot
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import find_feasible_slots
from app.scheduling.occupancy import live_blocking_occupancy_sql
from app.services import planner_service
from app.services.planner_service import get_planner_queue
from tests.proof.evidence import record_evidence
from tests.proof.harness import CONTESTED_DOCK, FACILITY_ID, RaceFixture, seed_race

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Offsets no other proof fixture uses (part 1 takes 0, part 3 takes 480, part 6 takes 960/1440/
# 1920/2400, part 11 takes 8640). Whole multiples of 24 h so each lands at 10:00 facility-local --
# inside FAC-JAI-01's 06:00-22:00 window and below RULE005's 21:00 LAST_NEW_START_TIME, which the
# harness docstring explains is a precondition for the fixture proving anything at all.
#
# This list is a real registry, not a comment: `appointment_slots` carries
# `UNIQUE (dock_id, slot_start_ts, slot_end_ts)` and every fixture here seeds `CONTESTED_DOCK`, so a
# duplicated offset is a UniqueViolation at fixture setup. Add to it when you add a fixture.
OFFSET_LIVE_HOLD = 2880       # 2099-03-03 10:00 IST
OFFSET_LAPSED_HOLD = 4320     # 2099-03-04 10:00 IST
OFFSET_AGREEMENT = 5760       # 2099-03-05 10:00 IST


async def _set_hold_deadline(session, *, occupancy_id: int, expires_at: datetime) -> None:
    """Move one live hold's TTL without touching anything else about the row.

    `state` stays 'HELD' and `appointment_id` stays NULL, so `dock_occupancy_held_shape_check` is
    satisfied and the row remains exactly what `create_hold` wrote -- only its deadline is now
    unambiguous rather than 90 seconds away from whenever the suite happens to be running.
    """
    await session.execute(
        text(
            """
            UPDATE public.dock_occupancy
            SET expires_at = :expires_at
            WHERE occupancy_id = :occupancy_id AND state = 'HELD'
            """
        ),
        {"occupancy_id": occupancy_id, "expires_at": expires_at},
    )
    await session.commit()


async def _take_hold(sessionmaker, fixture: RaceFixture, contender, *, key: str):
    async with sessionmaker() as session:
        return await request_slot(
            session,
            contender.ctx(),
            shipment_id=contender.shipment_id,
            slot_id=fixture.slot_id,
            command=RequestSlotCommand(
                note="issue #97 read/write agreement",
                displayed_policy_version=load_scheduling_constraints().policy_version,
            ),
            idempotency_key=key,
        )


async def _live_claims(session, fixture: RaceFixture, *, now: datetime) -> list[dict]:
    """Every row the shared predicate calls blocking, on the fixture's dock and interval.

    Uses `live_blocking_occupancy_sql` itself rather than a hand-written copy: a test that spelled
    the predicate out again could agree with a broken implementation of it.
    """
    rows = (
        await session.execute(
            text(
                f"""
                SELECT o.occupancy_id, o.state, o.shipment_id, o.appointment_id, o.expires_at
                FROM public.dock_occupancy o
                WHERE o.dock_id = :dock_id
                  AND o."window" && tstzrange(:start, :end, '[)')
                  AND {live_blocking_occupancy_sql(alias="o", now_param="now")}
                ORDER BY o.occupancy_id
                """
            ),
            {
                "dock_id": CONTESTED_DOCK,
                "start": fixture.slot_start,
                "end": fixture.slot_end,
                "now": now,
            },
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# =================================================================================================
# A. A LIVE hold must be invisible to nobody -- neither the read nor the write
# =================================================================================================


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def live_hold_case(work_sessionmaker):
    """Contender 0 holds the contested interval, with a deadline a day out."""
    run_id = f"L{uuid4().hex[:7].upper()}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(
            session,
            run_id=run_id,
            contenders=2,
            start_offset_minutes=OFFSET_LIVE_HOLD,
            alternatives=0,
        )

    holder = fixture.contenders[0]
    # Asked BEFORE the hold exists, so the assertion after it cannot be vacuous. If the contested
    # slot were not offered here, "it is not offered afterwards" would prove nothing at all.
    async with work_sessionmaker() as session:
        before = await find_feasible_slots(
            session, fixture.contenders[1].ctx(), fixture.contenders[1].shipment_id, limit=5
        )

    taken = await _take_hold(work_sessionmaker, fixture, holder, key=f"p7-live-{run_id}")
    assert taken.code == "SLOT_HELD", f"fixture setup failed: {taken.code}"

    deadline = datetime.now(timezone.utc) + timedelta(days=1)
    async with work_sessionmaker() as session:
        await _set_hold_deadline(
            session, occupancy_id=int(taken.hold_id), expires_at=deadline
        )
    return {
        "fixture": fixture,
        "hold_id": int(taken.hold_id),
        "deadline": deadline,
        "options_before": [option.slot_id for option in before.options],
    }


async def test_a_the_contested_slot_was_offered_before_anyone_held_it(live_hold_case):
    """The precondition that makes the next two tests mean something."""
    fixture: RaceFixture = live_hold_case["fixture"]
    assert fixture.slot_id in live_hold_case["options_before"], (
        "the contested slot was never offered even when free, so this fixture cannot show that "
        "holding it removes it"
    )


async def test_a_feasibility_does_not_offer_an_interval_another_shipment_holds(
    live_hold_case, work_sessionmaker
):
    """§4 is why this was broken: a hold has no `appointments` row, and the old candidate scan
    could only see appointments. The offer was therefore made against a table that structurally
    could not know."""
    fixture: RaceFixture = live_hold_case["fixture"]
    asker = fixture.contenders[1]
    # No injected `now`: the hold's deadline is a full day out, so the wall clock is inside the TTL
    # by any measure. See the module docstring for why that margin is the determinism mechanism.
    async with work_sessionmaker() as session:
        result = await find_feasible_slots(session, asker.ctx(), asker.shipment_id, limit=5)
    offered = [option.slot_id for option in result.options]
    record_evidence(
        "7. #97: live hold hidden from feasibility",
        f"{len(offered)} option(s) offered, contested slot present={fixture.slot_id in offered}",
    )
    assert fixture.slot_id not in offered, (
        f"{fixture.slot_id} is held by {fixture.contenders[0].shipment_id} and was still offered "
        f"to {asker.shipment_id} -- issue #97's read side"
    )


async def test_a_request_slot_refuses_the_interval_it_was_not_offered(
    live_hold_case, work_sessionmaker
):
    """The other half of agreement. Feasibility withholding it is only correct if the write really
    would refuse -- otherwise the read has simply become too conservative and capacity is being
    wasted."""
    fixture: RaceFixture = live_hold_case["fixture"]
    asker = fixture.contenders[1]
    refused = await _take_hold(
        work_sessionmaker, fixture, asker, key=f"p7-live-refuse-{fixture.run_id}"
    )
    record_evidence("7. #97: request_slot on a live-held interval", refused.code)
    assert refused.code == "SLOT_CONFLICT_REFRESH_REQUIRED", (
        f"expected a typed conflict, got {refused.code}"
    )
    assert refused.appointment_writes == 0


# =================================================================================================
# B. A LAPSED hold must block nobody -- the constraint-versus-clock half
# =================================================================================================


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def lapsed_hold_case(work_sessionmaker):
    """Contender 0's hold, with its deadline moved into the past and never swept.

    This is the live incident reproduced: `state='HELD'`, `expires_at` long gone, no sweeper.
    """
    run_id = f"X{uuid4().hex[:7].upper()}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(
            session,
            run_id=run_id,
            contenders=2,
            start_offset_minutes=OFFSET_LAPSED_HOLD,
            alternatives=0,
        )

    taken = await _take_hold(
        work_sessionmaker, fixture, fixture.contenders[0], key=f"p7-lapsed-{run_id}"
    )
    assert taken.code == "SLOT_HELD", f"fixture setup failed: {taken.code}"

    lapsed_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    async with work_sessionmaker() as session:
        await _set_hold_deadline(session, occupancy_id=int(taken.hold_id), expires_at=lapsed_at)
        # Proven, not assumed: the row is still HELD. If something had already swept it the rest of
        # this fixture would be testing an EXPIRED row and would pass for the wrong reason.
        state = await session.scalar(
            text("SELECT state FROM public.dock_occupancy WHERE occupancy_id = :id"),
            {"id": int(taken.hold_id)},
        )
        assert state == "HELD", f"the lapsed hold is {state}, not the unswept HELD this needs"
    return {"fixture": fixture, "hold_id": int(taken.hold_id), "lapsed_at": lapsed_at}


async def test_b_feasibility_offers_an_interval_whose_only_claim_is_a_lapsed_hold(
    lapsed_hold_case, work_sessionmaker
):
    """§0.8: a lapsed hold reserves nothing. Withholding the interval would sterilise capacity for
    as long as the sweeper stayed down -- which, as of 2026-09-01, is indefinitely.

    **This one passes against pre-fix code too, and that is the point rather than a weakness.**
    Before the fix it passed because feasibility could not see `dock_occupancy` at all; after it, it
    passes because the shared predicate says a lapsed hold is not blocking. Same answer, opposite
    reasons -- and the reason matters, because the pre-fix version of "offers it" was paired with a
    write path that refused it (`test_b_request_slot_succeeds_...`, which does fail pre-fix). Kept
    as a guard against over-correcting: a fix that made feasibility conservative about *every*
    `dock_occupancy` row would turn every unswept hold into permanently sterilised capacity, and
    this is the assertion that would catch it.
    """
    fixture: RaceFixture = lapsed_hold_case["fixture"]
    asker = fixture.contenders[1]
    # The deadline is 30 minutes in the past, so the wall clock is past it by any measure.
    async with work_sessionmaker() as session:
        result = await find_feasible_slots(session, asker.ctx(), asker.shipment_id, limit=5)
    offered = [option.slot_id for option in result.options]
    record_evidence(
        "7. #97: lapsed hold ignored by feasibility",
        f"contested slot offered={fixture.slot_id in offered}",
    )
    assert fixture.slot_id in offered, (
        "a hold that lapsed 30 minutes ago is still suppressing its interval from the search"
    )


async def test_b_request_slot_succeeds_by_lazily_expiring_the_dead_hold(
    lapsed_hold_case, work_sessionmaker
):
    """The write half, and the one the exclusion constraint cannot do on its own.

    Four things are asserted, because "the claim landed" means all four: the request won; the dead
    row is now EXPIRED *with its deadline cleared* (`dock_occupancy_held_shape_check` requires the
    NULL, so a flip without it would have aborted the transaction); exactly one live claim remains;
    and it belongs to the new holder rather than the old one.
    """
    fixture: RaceFixture = lapsed_hold_case["fixture"]
    asker = fixture.contenders[1]

    granted = await _take_hold(
        work_sessionmaker, fixture, asker, key=f"p7-lapsed-claim-{fixture.run_id}"
    )
    record_evidence("7. #97: request_slot over a lapsed hold", granted.code)
    assert granted.code == "SLOT_HELD", (
        f"a dead hold still refused the interval: {granted.code} {granted.conflict}"
    )

    async with work_sessionmaker() as session:
        old = (
            await session.execute(
                text(
                    "SELECT state, expires_at, appointment_id FROM public.dock_occupancy "
                    "WHERE occupancy_id = :id"
                ),
                {"id": lapsed_hold_case["hold_id"]},
            )
        ).mappings().first()
        assert old is not None, "the lazy expiry deleted the row instead of expiring it"
        assert old["state"] == "EXPIRED", f"the dead hold is still {old['state']}"
        assert old["expires_at"] is None, (
            "EXPIRED with a deadline still attached violates dock_occupancy_held_shape_check"
        )

        live = await _live_claims(session, fixture, now=datetime.now(timezone.utc))
        assert len(live) == 1, (
            f"expected exactly one live claim on the interval, found {len(live)}: "
            f"{[(row['occupancy_id'], row['state']) for row in live]}"
        )
        assert str(live[0]["occupancy_id"]) == granted.hold_id
        assert live[0]["shipment_id"] == asker.shipment_id
        assert live[0]["state"] == "HELD"


async def test_b_the_lazy_expiry_is_audited_and_names_which_path_did_it(
    lapsed_hold_case, work_sessionmaker
):
    """M14: every state change reconstructable. The transition is the sweeper's, so it reuses
    `EXPIRE_HOLD`; `actor` is what tells an auditor a competing claim did it rather than a cron."""
    async with work_sessionmaker() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT action_type, new_value_json
                    FROM public.audit_logs
                    WHERE entity_name = 'dock_occupancy' AND entity_id = :entity_id
                      AND action_type = 'EXPIRE_HOLD'
                    """
                ),
                {"entity_id": str(lapsed_hold_case["hold_id"])},
            )
        ).mappings().all()
    assert rows, "the lazy expiry wrote no EXPIRE_HOLD audit row"
    actors = {json.loads(str(row["new_value_json"])).get("actor") for row in rows}
    record_evidence("7. #97: lazy-expiry audit actor", ", ".join(sorted(a or "?" for a in actors)))
    assert holds.ACTOR_LAZY_CLAIM in actors


async def test_b_the_sweeper_still_finds_nothing_to_do_afterwards(
    lapsed_hold_case, work_sessionmaker
):
    """The lazy path must not leave work the scheduled path would redo.

    `sweep_held_holds` guards on `state = 'HELD'`, so an already-EXPIRED row cannot match and no
    second audit row can appear. Swept at an instant just after the old deadline, which is before
    the *new* holder's TTL -- so a non-zero count here would mean the sweeper had either re-expired
    the dead row or wrongly taken the live one.
    """
    fixture: RaceFixture = lapsed_hold_case["fixture"]
    async with work_sessionmaker() as session:
        result = await holds.sweep_held_holds(
            session,
            actor_user_id=fixture.contenders[0].user_id,
            now=lapsed_hold_case["lapsed_at"] + timedelta(seconds=1),
            ttl_seconds=90,
        )
        await session.commit()
    record_evidence("7. #97: sweeper after lazy expiry", f"expired={result.expired}")
    assert result.supported is True
    assert result.expired == 0, (
        f"the sweeper re-expired {result.expired} row(s) the lazy path had already handled"
    )


# =================================================================================================
# NFR-003's budget: the capacity check must not have cost a round trip
# =================================================================================================


class _CountingSession:
    """Counts statements without touching the engine, by standing in front of the session.

    `find_feasible_slots` only ever calls `.execute()`, so wrapping that one method is enough and
    is far less invasive than an engine-level event listener the session fixtures would then have
    to unregister.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.statements = 0

    async def execute(self, *args, **kwargs):
        self.statements += 1
        return await self._inner.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


async def test_the_capacity_check_added_no_round_trip(lapsed_hold_case, work_sessionmaker):
    """NFR-003 (`find_feasible_slots` < 50 ms), defended by structure rather than by a stopwatch.

    A timing assertion measured here would be close to meaningless: the proof cluster holds a few
    dozen `dock_occupancy` rows against production's thousands, so both the wall time and the query
    plan (PostgreSQL will prefer a sequential scan over any index on a table that small, whatever
    indexes exist) describe this fixture rather than the system. What *is* scale-independent, and
    what the repo's own "count the hops" rule asks for, is the number of sequential round trips --
    which is what `COMPARISON-latency` F16 flagged about this function in the first place.

    Four, unchanged by issue #97: shipment (+ driver window), facility (+ rules), current active
    appointment, candidate scan. The capacity predicate rides inside the fourth as a LATERAL rather
    than arriving as a fifth trip or, worse, as one probe per candidate slot -- with `LIMIT 500` on
    that scan, a per-candidate query would have been up to 500 of them.

    The index that keeps the LATERAL cheap at real volumes is the partial GiST index the exclusion
    constraint itself creates on `(dock_id, "window")`, which is why
    `occupancy.live_blocking_occupancy_sql` restates the constraint's own state list verbatim --
    see that function's docstring.
    """
    fixture: RaceFixture = lapsed_hold_case["fixture"]
    asker = fixture.contenders[1]
    async with work_sessionmaker() as session:
        counting = _CountingSession(session)
        await find_feasible_slots(counting, asker.ctx(), asker.shipment_id, limit=5)

    record_evidence(
        "7. #97: find_feasible_slots round trips",
        f"{counting.statements} sequential statements (NFR-003; was 4 before the capacity join)",
    )
    assert counting.statements == 4, (
        f"find_feasible_slots now issues {counting.statements} sequential statements, not 4 -- "
        "the capacity predicate must ride inside the candidate scan, not add a trip"
    )


async def test_the_liveness_predicate_can_use_the_exclusion_constraints_partial_index(
    lapsed_hold_case, work_sessionmaker
):
    """The other half of the NFR-003 argument, and the one that *is* scale-independent.

    The exclusion constraint creates a partial GiST index on `(dock_id, "window")`. What the
    apparently redundant state-list clause in `live_blocking_occupancy_sql` buys was measured on
    PostgreSQL 18.3 (both forms EXPLAINed on a proof cluster, 2026-09-01) and is sharper than
    "the index might not be used":

      naive `A OR (HELD AND expires_at > now)`
        -> BitmapOr of dock_occupancy_dock_id_window_excl AND ix_dock_occupancy_held_expiry,
           where the second arm has NO dock_id and NO window condition -- it reads every live
           hold in the database and rechecks them, once per candidate slot.

      canonical (state list AND the refinement)
        -> Index Scan using dock_occupancy_dock_id_window_excl,
           Index Cond: dock_id = ... AND "window" && ...,  liveness demoted to a Filter.

    So the assertion below is about the shape of the probe, not about this cluster's row counts,
    which is why it can be asserted at all where a timing assertion could not. `enable_seqscan =
    off` only removes the sequential-scan option; it cannot conjure an index the predicate does
    not match, so the plan naming the constraint's index is real evidence.

    Asserting the *plain* `Index Scan` rather than merely the index's name is deliberate: the naive
    form names that index too, inside its BitmapOr. Matching on the name alone would pass against
    exactly the regression this exists to catch.
    """
    fixture: RaceFixture = lapsed_hold_case["fixture"]
    async with work_sessionmaker() as session:
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan_rows = (
            await session.execute(
                text(
                    f"""
                    EXPLAIN
                    SELECT o.occupancy_id
                    FROM public.dock_occupancy o
                    WHERE o.dock_id = :dock_id
                      AND o."window" && tstzrange(:start, :end, '[)')
                      AND {live_blocking_occupancy_sql(alias="o", now_param="now")}
                    """
                ),
                {
                    "dock_id": CONTESTED_DOCK,
                    "start": fixture.slot_start,
                    "end": fixture.slot_end,
                    "now": datetime.now(timezone.utc),
                },
            )
        ).all()
        await session.rollback()

    plan = "\n".join(str(row[0]) for row in plan_rows)
    top = plan.splitlines()[0].strip() if plan else "(empty plan)"
    record_evidence("7. #97: capacity probe plan", top.split("  (cost=")[0])

    assert "Index Scan using dock_occupancy_dock_id_window_excl" in plan, (
        "the capacity probe is no longer a plain index scan on the exclusion constraint's partial "
        f"GiST index. Plan was:\n{plan}"
    )
    # The dock and the window must be the *index condition*, not a post-filter -- that is what
    # bounds the probe to one dock's overlapping rows.
    assert "Index Cond:" in plan and 'dock_id = ' in plan and '"window" &&' in plan, (
        f"dock_id/window are not the index condition:\n{plan}"
    )
    # And explicitly not the BitmapOr the naive predicate produces, whose second arm scans every
    # live hold in the database.
    assert "BitmapOr" not in plan, (
        "the liveness predicate degraded into a BitmapOr; its `expires_at` arm carries no dock or "
        f"window condition and reads every live hold. Plan was:\n{plan}"
    )
    assert "ix_dock_occupancy_held_expiry" not in plan, (
        "the capacity probe is reaching for the global HELD-expiry index, which is unbounded by "
        f"dock. Plan was:\n{plan}"
    )


# =================================================================================================
# C. The general invariant: whatever is offered can be taken
# =================================================================================================


async def test_c_every_offered_option_is_individually_requestable(work_sessionmaker):
    """The property both halves above are instances of, asserted directly.

    One distinct shipment per option, because taking an option consumes it -- asking the *same*
    shipment to take all five would prove only that the first one worked. The options are ranked
    across the whole 48-hour horizon, so this deliberately runs late in the suite, against a
    cluster the earlier parts have already left holds and appointments in: an offer set computed
    over a dirty database is a far stronger test of agreement than one computed over a pristine
    seed, which is precisely the lesson of #97 (the proof suite's own 50-way race behaved perfectly
    on a clean cluster while the shared dev database diverged).
    """
    run_id = f"G{uuid4().hex[:7].upper()}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(
            session,
            run_id=run_id,
            contenders=6,
            start_offset_minutes=OFFSET_AGREEMENT,
            alternatives=4,
        )

    async with work_sessionmaker() as session:
        offered = await find_feasible_slots(
            session, fixture.contenders[0].ctx(), fixture.contenders[0].shipment_id, limit=5
        )
    option_slot_ids = [option.slot_id for option in offered.options]
    assert option_slot_ids, "no options were offered, so this test would be vacuous"

    outcomes: list[tuple[str, str]] = []
    for index, slot_id in enumerate(option_slot_ids):
        contender = fixture.contenders[index]
        async with work_sessionmaker() as session:
            result = await request_slot(
                session,
                contender.ctx(),
                shipment_id=contender.shipment_id,
                slot_id=slot_id,
                command=RequestSlotCommand(
                    note="issue #97 feasible-implies-requestable",
                    displayed_policy_version=load_scheduling_constraints().policy_version,
                ),
                idempotency_key=f"p7-agree-{run_id}-{index:02d}",
            )
        outcomes.append((slot_id, result.code))

    record_evidence(
        "7. #97: feasible => requestable",
        f"{sum(1 for _, code in outcomes if code == 'SLOT_HELD')}/{len(outcomes)} offered options "
        "were requestable",
    )
    refused = [(slot_id, code) for slot_id, code in outcomes if code != "SLOT_HELD"]
    assert not refused, (
        "find_feasible_slots offered intervals request_slot then refused -- issue #97 exactly: "
        f"{refused}"
    )


# =================================================================================================
# D. Issue #98 -- the planner displacement reads, the third party to the same liveness predicate
# =================================================================================================
#
# #97 gave the *claim* path a lazy-expiry leg, and #84 had already established that the
# displacement reads must see exactly what the exclusion constraint sees -- so they carry no
# `expires_at > now()` term. Together those two facts produced a third defect: a planner was
# refused with `DISPLACEMENT_DETECTED` by a hold the very next claim would have silently expired,
# and with no sweeper running (issue #20) that refusal never cleared on its own.
#
# Owner decision (b): the displacement reads lazily expire lapsed holds *first*, in the same
# transaction, and then read -- so #84's invariant stays literally true (after the flip the
# constraint genuinely does not count the row) rather than being weakened into "the read ignores
# some rows the constraint still enforces".
#
# The fixture below builds the one shape in which an appointment and an overlapping hold can
# coexist at all. The exclusion constraint is partial on
# `state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')`, so while an appointment
# holds its own `dock_occupancy` claim nothing overlapping can be inserted. The claim is therefore
# released through `allocation._release_dock_occupancy` -- the production function -- leaving the
# appointment with a slot-derived interval and no claim. That is not a contrivance: it is exactly
# the case `planner_service._conflicts_for`'s own docstring says the displacement check exists for
# (E1.1's D12 worklist rows, and anything whose claim was released).

OFFSET_DISPLACEMENT = 7200  # 2099-03-06 10:00 IST


def _planner_ctx() -> ExecutionContext:
    """`USR102` / Rahul Verma -- the shipped seed's WAREHOUSE_PLANNER at FAC-JAI-01.

    A seeded user rather than a synthesised one because `audit_logs.user_id` is NOT NULL and the
    lazy expiry writes an `EXPIRE_HOLD` row attributed to whoever's read discovered the dead hold.
    """
    return ExecutionContext(
        request_id="proof-p7d",
        auth_subject="proof-p7d",
        user_id="USR102",
        email="rahul.verma@setuhaul.com",
        full_name="Rahul Verma",
        role_id="ROL003",
        role_name=RoleName.WAREHOUSE_PLANNER,
        facility_id=FACILITY_ID,
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def displacement_lapsed_hold_case(work_sessionmaker):
    """A PENDING_CONFIRMATION appointment with a lapsed, unswept hold across its interval."""
    run_id = f"D{uuid4().hex[:7].upper()}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(
            session,
            run_id=run_id,
            contenders=2,
            start_offset_minutes=OFFSET_DISPLACEMENT,
            alternatives=0,
        )

    # 1. Contender 0 takes the interval and converts it into a real appointment, through the real
    #    two-phase path -- hold, then `confirm_held_slot`. Nothing is inserted by hand.
    holder = fixture.contenders[0]
    taken = await _take_hold(work_sessionmaker, fixture, holder, key=f"p7-disp-hold-{run_id}")
    assert taken.code == "SLOT_HELD", f"fixture setup failed: {taken.code}"
    async with work_sessionmaker() as session:
        confirmed = await holds.confirm_held_slot(
            session,
            holder.ctx(),
            hold_id=str(taken.hold_id),
            idempotency_key=f"p7-disp-confirm-{run_id}",
        )
    # `SLOT_REQUESTED`, not "confirmed": section 4 / M7 -- `confirm_held_slot` commits the hold into
    # a PENDING_CONFIRMATION *request*, and only a planner can reach CONFIRMED from there.
    assert confirmed.code == "SLOT_REQUESTED", f"fixture setup failed: {confirmed.code}"
    appointment_id = str(confirmed.appointment_id)

    # 2. Release that appointment's claim, through the production function. This is what makes the
    #    fixture possible at all -- see the section comment above -- and it is a state the live
    #    system genuinely produces.
    async with work_sessionmaker() as session:
        released = await allocation._release_dock_occupancy(session, appointment_id)
        await session.commit()
    assert released, "the appointment held no claim to release; the fixture is not what it claims"

    # 3. An *overlapping, later* slot on the same dock, for the blocking hold to be taken against.
    #    Not the same slot the appointment sits on: `find_feasible_slots` derives availability from
    #    `appointment_slots` joined to `appointments`, so a slot already carrying a
    #    PENDING_CONFIRMATION row is not offered and `request_slot` refuses it --  correctly.
    #    Starting 30 minutes in gives a claim window of 10:30-11:30 against the appointment's
    #    slot-derived 10:00-11:00 (start + `expected_unload_min` 45 + the flat 15-minute
    #    changeover), which is a genuine `&&` overlap on `DOCK-JAI-D1` rather than the abutting
    #    pair `&&` deliberately does not count.
    blocking_slot_id = f"SLOT-PROOFOVL-{run_id}"
    blocking_start = fixture.slot_start + timedelta(minutes=30)
    async with work_sessionmaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO public.appointment_slots (
                  slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts,
                  slot_status, block_reason, created_at
                ) VALUES (
                  :slot_id, :facility_id, :dock_id, :slot_start, :slot_end, 'OPEN', NULL,
                  :created_at
                )
                """
            ),
            {
                "slot_id": blocking_slot_id,
                "facility_id": FACILITY_ID,
                "dock_id": CONTESTED_DOCK,
                "slot_start": blocking_start,
                "slot_end": blocking_start + timedelta(minutes=60),
                "created_at": blocking_start,
            },
        )
        await session.commit()

    # 4. The competing hold itself -- created by `request_slot`, not by an INSERT -- and then aged
    #    past its deadline. This is the live incident's shape: `state` still 'HELD', `expires_at`
    #    long gone, nothing having swept it.
    blocker = fixture.contenders[1]
    async with work_sessionmaker() as session:
        dead = await request_slot(
            session,
            blocker.ctx(),
            shipment_id=blocker.shipment_id,
            slot_id=blocking_slot_id,
            command=RequestSlotCommand(
                note="issue #98 displacement read",
                displayed_policy_version=load_scheduling_constraints().policy_version,
            ),
            idempotency_key=f"p7-disp-dead-{run_id}",
        )
    assert dead.code == "SLOT_HELD", f"fixture setup failed: {dead.code} {dead.conflict}"
    lapsed_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    async with work_sessionmaker() as session:
        await _set_hold_deadline(session, occupancy_id=int(dead.hold_id), expires_at=lapsed_at)
        state = await session.scalar(
            text("SELECT state FROM public.dock_occupancy WHERE occupancy_id = :id"),
            {"id": int(dead.hold_id)},
        )
        assert state == "HELD", f"the blocking hold is {state}, not the unswept HELD this needs"

    return {
        "fixture": fixture,
        "appointment_id": appointment_id,
        "shipment_id": holder.shipment_id,
        "dead_hold_id": int(dead.hold_id),
        "lapsed_at": lapsed_at,
    }


async def test_d_the_queue_row_does_not_report_a_dead_hold_as_a_displacement(
    displacement_lapsed_hold_case, work_sessionmaker
):
    """The read the planner actually looks at.

    Against pre-#98 code this row renders `displacement: CONFLICT` naming `hold:<id>` -- capacity
    nobody holds. It is also the half that cannot be skipped: `conflict_ids` feeds `snapshot_hash`,
    so a queue that still counted the dead hold would hand the planner a digest the write path
    (which does expire it) can no longer reproduce, turning every first confirm into
    `SNAPSHOT_STALE` instead of a displacement refusal.
    """
    case = displacement_lapsed_hold_case
    async with work_sessionmaker() as session:
        queue = await get_planner_queue(
            session, _planner_ctx(), facility_id=FACILITY_ID, limit=200
        )
    row = next(
        (item for item in queue.items if item.appointment_id == case["appointment_id"]), None
    )
    assert row is not None, "the fixture's pending appointment is not in the planner queue at all"
    record_evidence(
        "7. #98: queue displacement over a dead hold",
        f"{row.displacement.status} ({len(row.displacement.conflicts)} conflict(s))",
    )
    assert row.displacement.status == "NONE", (
        "a hold that lapsed 30 minutes ago is still reported as a displacement: "
        f"{row.displacement.conflicts}"
    )


async def test_d_confirm_is_not_refused_with_displacement_detected_by_a_dead_hold(
    displacement_lapsed_hold_case, work_sessionmaker
):
    """The refusal #98 is named for, exercised through the real section 7.5.1 tool.

    Deliberately self-contained rather than reusing the digest the test above read: it re-renders
    the queue itself, exactly as a planner does before pressing Confirm, so it bites on its own
    against pre-#98 code instead of failing on a missing precondition. Pre-fix that render carries
    the dead hold in `conflicts` and therefore in `snapshot_hash`, and the confirm is refused
    `DISPLACEMENT_DETECTED` -- forever, because nothing else in the system will ever retire the
    hold (the sweeper is not wired; issue #20).
    """
    case = displacement_lapsed_hold_case
    async with work_sessionmaker() as session:
        queue = await get_planner_queue(
            session, _planner_ctx(), facility_id=FACILITY_ID, limit=200
        )
    rendered = next(
        item for item in queue.items if item.appointment_id == case["appointment_id"]
    )

    async with work_sessionmaker() as session:
        result = await allocation.confirm_appointment(
            session,
            _planner_ctx(),
            shipment_id=case["shipment_id"],
            command=allocation.ConfirmAppointmentCommand(
                appointment_id=case["appointment_id"],
                snapshot_hash=rendered.snapshot_hash,
            ),
            idempotency_key="p7-disp-apt-" + case["fixture"].run_id,
        )
    record_evidence("7. #98: confirm over a dead hold", result.code)
    assert result.code == "APPOINTMENT_CONFIRMED", (
        f"expected APPOINTMENT_CONFIRMED, got {result.code}"
    )


async def test_d_the_dead_hold_ends_expired_rather_than_merely_ignored(
    displacement_lapsed_hold_case, work_sessionmaker
):
    """Owner decision (b), stated as an assertion.

    (a) would have taught the reads to skip lapsed holds while leaving them HELD in the table --
    which keeps the exclusion constraint refusing writes the reads say are fine, i.e. #84 again.
    (b) requires the row to genuinely leave the constraint's set, so this asserts the *table*, not
    the response: EXPIRED, with `expires_at` cleared as `dock_occupancy_held_shape_check` demands.
    """
    case = displacement_lapsed_hold_case
    async with work_sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT state, expires_at FROM public.dock_occupancy "
                    "WHERE occupancy_id = :id"
                ),
                {"id": case["dead_hold_id"]},
            )
        ).mappings().first()
    assert row is not None, "the lazy expiry deleted the row instead of expiring it"
    record_evidence("7. #98: dead hold after a displacement read", str(row["state"]))
    assert row["state"] == "EXPIRED", f"the dead hold is still {row['state']}"
    assert row["expires_at"] is None, (
        "EXPIRED with a deadline still attached violates dock_occupancy_held_shape_check"
    )


async def test_d_the_read_path_expiry_is_audited_and_names_itself(
    displacement_lapsed_hold_case, work_sessionmaker
):
    """M14 again, and the reason #98 got its own actor string rather than reusing #97's.

    "A competing claim expired this" and "a planner's displacement read expired this" are different
    facts about how the system behaved, and an auditor reconstructing a capacity decision needs to
    tell them apart.
    """
    case = displacement_lapsed_hold_case
    async with work_sessionmaker() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT new_value_json
                    FROM public.audit_logs
                    WHERE entity_name = 'dock_occupancy' AND entity_id = :entity_id
                      AND action_type = 'EXPIRE_HOLD'
                    """
                ),
                {"entity_id": str(case["dead_hold_id"])},
            )
        ).mappings().all()
    assert rows, "the read-path lazy expiry wrote no EXPIRE_HOLD audit row"
    actors = {json.loads(str(row["new_value_json"])).get("actor") for row in rows}
    record_evidence(
        "7. #98: read-path expiry audit actor", ", ".join(sorted(a or "?" for a in actors))
    )
    assert holds.ACTOR_LAZY_DISPLACEMENT_READ in actors
    # Exactly one audit row per hold, not one per read: a second render finds `state <> 'HELD'`
    # and updates nothing, so nothing is audited twice.
    assert len(rows) == 1, f"the same hold was audited {len(rows)} times"


async def test_d_the_sweeper_still_finds_nothing_to_do_afterwards(
    displacement_lapsed_hold_case, work_sessionmaker
):
    """Same hygiene property #97's leg has: the lazy path must leave the scheduled path no work."""
    case = displacement_lapsed_hold_case
    async with work_sessionmaker() as session:
        result = await holds.sweep_held_holds(
            session,
            actor_user_id="USR102",
            now=case["lapsed_at"] + timedelta(seconds=1),
            ttl_seconds=90,
        )
        await session.commit()
    record_evidence("7. #98: sweeper after a read-path expiry", f"expired={result.expired}")
    assert result.expired == 0, (
        f"the sweeper re-expired {result.expired} row(s) the displacement read had handled"
    )


# =================================================================================================
# E. Issue #88 -- the queue row and the refusal must name the same conflict set
# =================================================================================================
#
# The last member of the same family. #97/#98 were about the *interval* leg of "this dock time is
# taken"; this is about the other leg the write path always counted and the read never did.
#
# `snapshot.displacement_conflicts` -- what `confirm_request` refuses on -- returns
# `conflicts + dock_blocks`. `get_planner_queue`'s displacement column carried only the first half,
# so a planner could be refused `DISPLACEMENT_DETECTED` for a dock taken offline under them that
# their screen had said nothing about. Section 7.3 calls that column "the single most important
# field" and builds the whole 30-second decision on it, so a preview that under-reports it is a
# correctness gap, not a cosmetic one.
#
# The fix is the same shape as #97's: **one predicate, two consumers.** The block leg now lives in
# `snapshot._DOCK_BLOCK_CONFLICTS_SQL` over `snapshot._TARGET_CTE`, and both the recomputation and
# `snapshot.load_dock_block_conflicts` (which the queue read calls) are assembled from those two
# literals. A test that spelled the predicate out again could agree with a broken implementation of
# it, so the first test below asserts the *sharing* structurally and the rest exercise both
# consumers against a real cluster.
#
# The hash assertion is the subtle one and the reason #88 was not a quick patch: the block must
# stay OUT of `snapshot_hash`. In it, blocking one dock would change the digest of every
# outstanding row on that dock and mass-refuse in-flight confirms with `SNAPSHOT_STALE` -- turning
# a targeted refusal into a facility-wide one, and hiding the specific reason the planner needs to
# read. Part 5's determinism assertions rest on the same property.

# 2099-03-08 10:00 IST. **Not 8640** -- `test_part11_hold_for_information.py` claimed that
# offset (its `START_OFFSET_MINUTES`) while this was being written, and `appointment_slots`
# carries `UNIQUE (dock_id, slot_start_ts, slot_end_ts)`, so two fixtures on `DOCK-JAI-D1` at
# the same instant is a UniqueViolation at setup rather than an interference nobody notices.
# Each fixture in this suite owns a distinct day on the contested dock; keep it that way.
OFFSET_DOCK_BLOCK = 10080  # 2099-03-08 10:00 IST


async def test_e_the_block_predicate_is_one_literal_shared_by_both_consumers():
    """Structural, and deliberately first: everything below is only meaningful if this holds.

    Asserts the shared fragment is present verbatim in every statement that answers "is this dock
    blocked", rather than three strings that happen to agree today. A future edit that copies the
    predicate into one of them fails here, before the behavioural tests get a chance to pass by
    coincidence.
    """
    fragment = snapshot._DOCK_BLOCK_CONFLICTS_SQL
    assert fragment.strip(), "the shared dock-block fragment is empty"
    for name, statement in (
        ("write path", snapshot._snapshot_sql(include_holds=False)),
        ("write path (holds)", snapshot._snapshot_sql(include_holds=True)),
        ("queue read", snapshot._DOCK_BLOCKS_ONLY_SQL),
    ):
        assert fragment in statement, f"{name} no longer uses the shared dock-block fragment"
    # And the same interval derivation, so the two consumers cannot disagree about *which* window a
    # block has to overlap to count.
    assert snapshot._TARGET_CTE in snapshot._DOCK_BLOCKS_ONLY_SQL
    assert snapshot._TARGET_CTE in snapshot._snapshot_sql(include_holds=False)
    record_evidence("7. #88: dock-block predicate", "one shared literal, three statements")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def dock_block_case(work_sessionmaker):
    """A PENDING_CONFIRMATION appointment whose dock is then taken offline across its interval.

    Built through the production paths end to end -- `request_slot` then `confirm_held_slot` for the
    request, then `planner_service.block_dock` for the outage -- rather than by inserting a
    `dock_status_events` row by hand. That matters: `block_dock` is what a planner actually presses,
    it writes the row *and* opens the `CAPACITY_EVENT_CASCADE`, and it deliberately does **not**
    delete the `dock_occupancy` claims it strands (section 7.4). A hand-written row would have
    proved the query and not the product.

    The queue is rendered **before** the block as well, and that render is the precondition the hash
    assertion rests on: without it, "the digest did not change" could not be told apart from "there
    was never a digest to change".
    """
    run_id = f"B{uuid4().hex[:7].upper()}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(
            session,
            run_id=run_id,
            contenders=1,
            start_offset_minutes=OFFSET_DOCK_BLOCK,
            alternatives=0,
        )

    holder = fixture.contenders[0]
    taken = await _take_hold(work_sessionmaker, fixture, holder, key=f"p7-block-hold-{run_id}")
    assert taken.code == "SLOT_HELD", f"fixture setup failed: {taken.code}"
    async with work_sessionmaker() as session:
        confirmed = await holds.confirm_held_slot(
            session,
            holder.ctx(),
            hold_id=str(taken.hold_id),
            idempotency_key=f"p7-block-confirm-{run_id}",
        )
    assert confirmed.code == "SLOT_REQUESTED", f"fixture setup failed: {confirmed.code}"
    appointment_id = str(confirmed.appointment_id)

    # The pre-block render. Its digest is what the planner would have sent, and what the write path
    # must still be able to reproduce after the dock goes down.
    async with work_sessionmaker() as session:
        before_queue = await get_planner_queue(
            session, _planner_ctx(), facility_id=FACILITY_ID, limit=200
        )
    before = next(
        (item for item in before_queue.items if item.appointment_id == appointment_id), None
    )
    assert before is not None, "the fixture's pending appointment is not in the planner queue"
    assert before.displacement.status == "NONE", (
        "the row is already conflicted before the dock was blocked: "
        f"{before.displacement.conflicts}"
    )

    # The block itself, across the appointment's own interval, through the section 7.5.1 tool.
    async with work_sessionmaker() as session:
        blocked = await planner_service.block_dock(
            session,
            _planner_ctx(),
            dock_id=CONTESTED_DOCK,
            window_start=before.interval_start - timedelta(minutes=15),
            window_end=before.interval_end + timedelta(minutes=15),
            reason="issue #88 displacement preview",
            idempotency_key=f"p7-block-{run_id}",
        )
    assert blocked.code == "BLOCKED", f"fixture setup failed: {blocked.code}"

    return {
        "fixture": fixture,
        "appointment_id": appointment_id,
        "shipment_id": holder.shipment_id,
        "dock_event_id": blocked.dock_status_event_id,
        "before": before,
    }


async def test_e_the_queue_row_shows_the_dock_block_the_confirm_would_refuse_on(
    dock_block_case, work_sessionmaker
):
    """The defect, stated as the read a planner actually looks at.

    Against pre-#88 code this row renders `displacement: NONE` -- there is no overlapping *claim*,
    only an outage -- while `confirm_request` refuses it. The `conflict_type` is asserted because
    "another truck is booked here" and "there is no dock" are different harms with different
    recoveries, and an untyped list said the same sentence for both.
    """
    case = dock_block_case
    async with work_sessionmaker() as session:
        queue = await get_planner_queue(
            session, _planner_ctx(), facility_id=FACILITY_ID, limit=200
        )
    row = next(
        (item for item in queue.items if item.appointment_id == case["appointment_id"]), None
    )
    assert row is not None, "the fixture's pending appointment left the planner queue"
    record_evidence(
        "7. #88: queue row after block_dock",
        f"{row.displacement.status} "
        f"({[c.get('conflict_type') for c in row.displacement.conflicts]})",
    )
    assert row.displacement.status == "CONFLICT", (
        "the dock under this request was taken offline and the row still says no displacement -- "
        "issue #88's under-report"
    )
    blocks = [c for c in row.displacement.conflicts if c.get("conflict_type") == "DOCK_BLOCKED"]
    assert blocks, f"no DOCK_BLOCKED conflict on the row: {row.displacement.conflicts}"
    assert blocks[0]["dock_event_id"] == case["dock_event_id"]
    assert blocks[0]["dock_id"] == CONTESTED_DOCK


async def test_e_confirm_refuses_exactly_what_the_row_warned_about(
    dock_block_case, work_sessionmaker
):
    """Agreement, in the direction that matters: the refusal names the same event the row did.

    This is the property the whole family is about. Before #88 both halves of this test passed
    individually -- the row said NONE and the confirm said DISPLACEMENT_DETECTED -- and it was
    precisely their *disagreement* that nothing could see.
    """
    case = dock_block_case
    async with work_sessionmaker() as session:
        queue = await get_planner_queue(
            session, _planner_ctx(), facility_id=FACILITY_ID, limit=200
        )
    rendered = next(
        item for item in queue.items if item.appointment_id == case["appointment_id"]
    )

    async with work_sessionmaker() as session:
        with pytest.raises(AppError) as exc:
            await allocation.confirm_appointment(
                session,
                _planner_ctx(),
                shipment_id=case["shipment_id"],
                command=allocation.ConfirmAppointmentCommand(
                    appointment_id=case["appointment_id"],
                    snapshot_hash=rendered.snapshot_hash,
                ),
                idempotency_key="p7-block-refused-" + case["fixture"].run_id,
            )
    record_evidence("7. #88: confirm over a blocked dock", exc.value.code)
    assert exc.value.code == "DISPLACEMENT_DETECTED", (
        f"expected DISPLACEMENT_DETECTED, got {exc.value.code}"
    )
    refused = json.loads(str(exc.value.detail))["conflicts"]
    refused_events = {c.get("dock_event_id") for c in refused if c.get("dock_event_id")}
    shown_events = {
        c.get("dock_event_id") for c in rendered.displacement.conflicts if c.get("dock_event_id")
    }
    assert refused_events and refused_events == shown_events, (
        f"the refusal named {refused_events} and the row showed {shown_events} -- issue #88 is "
        "exactly that these two sets were allowed to differ"
    )


async def test_e_blocking_a_dock_does_not_invalidate_the_outstanding_snapshot(
    dock_block_case, work_sessionmaker
):
    """The hash-exclusion sub-item, against real rows rather than a constructed digest.

    The same appointment rendered before and after `block_dock` must carry the **same**
    `snapshot_hash`. If the block were inside the digest, the refusal above would arrive as
    `SNAPSHOT_STALE` instead -- and because the write path checks displacement *first* precisely so
    that cannot happen, every planner holding a row on that dock would be told "something moved"
    rather than "this dock is down".

    Both halves are asserted in one render so neither can pass for the wrong reason: an
    implementation that dropped the block from the *column* as well would satisfy the hash equality
    and fail the second assertion.
    """
    case = dock_block_case
    before = case["before"]
    async with work_sessionmaker() as session:
        queue = await get_planner_queue(
            session, _planner_ctx(), facility_id=FACILITY_ID, limit=200
        )
    after = next(item for item in queue.items if item.appointment_id == case["appointment_id"])

    record_evidence(
        "7. #88: snapshot_hash across a block",
        "unchanged" if after.snapshot_hash == before.snapshot_hash else "CHANGED",
    )
    assert after.snapshot_hash == before.snapshot_hash, (
        "block_dock changed this row's snapshot_hash -- every outstanding confirm on this dock "
        "would now be refused SNAPSHOT_STALE instead of DISPLACEMENT_DETECTED"
    )
    assert before.displacement.status == "NONE" and after.displacement.status == "CONFLICT", (
        "the displacement column did not change across the block, so the hash assertion above is "
        "vacuous"
    )
