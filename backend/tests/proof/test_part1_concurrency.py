"""Section 10 part 1 -- the N=50 concurrency harness.

Design citation: `SOLUTION_DESIGN.md` section 10.1 --

    "Fire N=50 simultaneous `request_slot` calls at one interval from distinct sessions. Assert:
     exactly 1 -> HELD (the D2 outcome -- PENDING_CONFIRMATION only follows a confirm_held_slot
     inside the TTL); 49 -> SLOT_CONFLICT_REFRESH_REQUIRED with fresh options; zero 5xx; zero
     orphaned holds after TTL."

Also section 9.2's first named race (`same_interval_race`), section 0.8 (D2's TTL and the lazy
expiry rule), D1, D2, M6. GitHub issue #44.

## What is actually being proved, and by whom

Not "the Python code branches correctly" -- **PostgreSQL** is the thing under test. The 50 sessions
all reach `holds.create_hold`, which is a bare INSERT into `dock_occupancy`; the only reason 49 of
them fail is the partial GiST exclusion constraint
(`dock_occupancy_dock_id_window_excl`). `allocation.py`'s own comment says it plainly: "This INSERT
is the concurrency decision, not a pre-check."

So this file deliberately calls `allocation.request_slot` -- the real tool entry point -- against a
real cluster, with 50 genuinely distinct `AsyncSession`s on 50 distinct pooled connections. A
shared session would serialise them inside SQLAlchemy and prove nothing.

## Why the TTL check advances a clock instead of sleeping

Section 10.1 asks for "zero orphaned holds after TTL", and the TTL is 90 seconds. Sleeping 90
seconds in CI is both slow and a wall-clock dependency of exactly the kind section 9.1 forbids
("the entire suite starts failing the day after it is written"). `sweep_held_holds` takes `now` as
an argument for this reason, so the deadline is crossed deliberately -- `hold.expires_at + 1s` --
and the result is the same assertion with none of the flakiness.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.errors import AppError
from app.scheduling import holds
from app.scheduling.allocation import RequestSlotCommand, request_slot
from app.scheduling.constraints import load_scheduling_constraints
from tests.proof.evidence import record_evidence
from tests.proof.harness import Contender, RaceFixture, seed_race

pytestmark = pytest.mark.asyncio(loop_scope="session")

CONTENDERS = 50


async def _one_request(sessionmaker, fixture: RaceFixture, contender: Contender):
    """One competitor's whole call, on its own session and its own connection."""
    async with sessionmaker() as session:
        return await request_slot(
            session,
            contender.ctx(),
            shipment_id=contender.shipment_id,
            slot_id=fixture.slot_id,
            command=RequestSlotCommand(
                note="section 10.1 concurrency harness",
                displayed_policy_version=load_scheduling_constraints().policy_version,
            ),
            idempotency_key=f"proof-race-{fixture.run_id}-{contender.index:03d}",
        )


@pytest.fixture(scope="session")
def race_run_id() -> str:
    return uuid4().hex[:8].upper()


@pytest.fixture(scope="session")
def race_results_holder() -> dict:
    """Carries one expensive 50-way race between the assertions that examine it.

    The race is run once and inspected several times rather than re-run per assertion: it is the
    single slowest thing in the suite, and re-running it would also make each assertion look at a
    *different* race, which is precisely how a flaky concurrency test is born.
    """
    return {}


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def race(work_sessionmaker, race_run_id, race_results_holder):
    if race_results_holder:
        return race_results_holder

    async with work_sessionmaker() as session:
        fixture = await seed_race(session, run_id=race_run_id, contenders=CONTENDERS)

    outcomes = await asyncio.gather(
        *(_one_request(work_sessionmaker, fixture, c) for c in fixture.contenders),
        return_exceptions=True,
    )
    race_results_holder.update({"fixture": fixture, "outcomes": list(outcomes)})
    return race_results_holder


async def test_zero_5xx_across_fifty_simultaneous_requests(race):
    """Section 10.1's "zero 5xx", asserted on what the callers actually got back.

    A losing race is a *normal* outcome and must arrive as a typed conflict, never as a raised
    exception or a 5xx AppError. Anything that escaped as an exception is reported with its type
    and message so the failure names the defect rather than just counting it.
    """
    escaped = [o for o in race["outcomes"] if isinstance(o, BaseException)]
    record_evidence("1. concurrency: raised/5xx", f"{len(escaped)} raised, 0 tolerated")
    assert escaped == [], (
        f"{len(escaped)} of {CONTENDERS} requests raised instead of returning a typed outcome: "
        + "; ".join(f"{type(e).__name__}: {e}" for e in escaped[:5])
    )
    server_errors = [
        o
        for o in race["outcomes"]
        if isinstance(o, AppError) and getattr(o, "status_code", 500) >= 500
    ]
    assert server_errors == []


async def test_exactly_one_held_and_forty_nine_conflicts(race):
    outcomes = race["outcomes"]
    assert len(outcomes) == CONTENDERS

    held = [o for o in outcomes if not isinstance(o, BaseException) and o.code == "SLOT_HELD"]
    conflicts = [
        o
        for o in outcomes
        if not isinstance(o, BaseException) and o.code == "SLOT_CONFLICT_REFRESH_REQUIRED"
    ]
    other = [
        o
        for o in outcomes
        if not isinstance(o, BaseException) and o.code not in {"SLOT_HELD", "SLOT_CONFLICT_REFRESH_REQUIRED"}
    ]

    record_evidence(
        "1. concurrency: outcome split",
        f"N={len(outcomes)} -> {len(held)} HELD / {len(conflicts)} SLOT_CONFLICT_REFRESH_REQUIRED "
        f"/ {len(other)} other",
    )
    assert other == [], f"unexpected outcome codes: {[o.code for o in other]}"
    assert len(held) == 1, f"expected exactly 1 HELD, got {len(held)}"
    assert len(conflicts) == CONTENDERS - 1, (
        f"expected {CONTENDERS - 1} SLOT_CONFLICT_REFRESH_REQUIRED, got {len(conflicts)}"
    )


async def test_the_winner_is_held_and_not_pending_confirmation(race):
    """Section 10.1 is explicit that the winning outcome is `HELD`, not `PENDING_CONFIRMATION`:
    "PENDING_CONFIRMATION only follows a `confirm_held_slot` inside the TTL". Section 4 says the
    same from the other side: "Held != booked: no `appointments` row exists yet."
    """
    winner = next(o for o in race["outcomes"] if not isinstance(o, BaseException) and o.code == "SLOT_HELD")
    assert winner.status == "HELD"
    assert winner.appointment_id is None
    assert winner.appointment_writes == 0
    assert winner.hold_id
    assert winner.hold_expires_at
    assert winner.hold_ttl_seconds == 90


async def test_every_loser_gets_fresh_options_not_a_bare_conflict(race):
    """"49 -> `SLOT_CONFLICT_REFRESH_REQUIRED` **with fresh options**" -- the second half of that
    sentence is the part a bare 409 would fail.

    The harness seeds three alternative intervals on a second dock precisely so this assertion is
    not vacuous: if `refreshed_options` came back empty, an empty list would satisfy "is not None"
    while telling the driver nothing.
    """
    conflicts = [
        o
        for o in race["outcomes"]
        if not isinstance(o, BaseException) and o.code == "SLOT_CONFLICT_REFRESH_REQUIRED"
    ]
    for outcome in conflicts:
        assert outcome.appointment_writes == 0
        assert outcome.refreshed_options is not None, outcome.shipment_id
        assert outcome.refreshed_options["options"], (
            f"{outcome.shipment_id} was told to refresh but offered nothing"
        )
        assert outcome.conflict and outcome.conflict.get("reason_code")


async def test_the_database_holds_exactly_one_claim_on_the_contested_interval(race, work_session):
    """The assertion that does not depend on any Python return value.

    Every previous assertion reads what the application *said*. This one reads what PostgreSQL
    *did*: one capacity-consuming row on that dock for that window, and zero appointments -- a hold
    is a `dock_occupancy` row and nothing else (section 4).
    """
    fixture: RaceFixture = race["fixture"]
    claims = (
        await work_session.execute(
            text(
                """
                SELECT occupancy_id, state, shipment_id, appointment_id, expires_at,
                       lower("window") AS window_start, upper("window") AS window_end
                FROM public.dock_occupancy
                WHERE dock_id = :dock_id
                  AND "window" && tstzrange(:start, :end, '[)')
                  AND state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
                """
            ),
            {
                "dock_id": "DOCK-JAI-D1",
                "start": fixture.slot_start,
                "end": fixture.slot_end,
            },
        )
    ).mappings().all()
    record_evidence(
        "1. concurrency: capacity claims on the contested interval",
        f"{len(claims)} row(s) in dock_occupancy, {[c['state'] for c in claims]}",
    )
    assert len(claims) == 1, f"D1's exclusion constraint admitted {len(claims)} claims"
    claim = claims[0]
    assert claim["state"] == "HELD"
    assert claim["appointment_id"] is None
    assert claim["expires_at"] is not None

    appointments = await work_session.scalar(
        text("SELECT count(*) FROM public.appointments WHERE slot_id = :slot_id"),
        {"slot_id": fixture.slot_id},
    )
    assert int(appointments) == 0, "a hold created an appointments row; section 4 says it must not"


async def test_every_contender_recorded_exactly_one_idempotency_row(race, work_session):
    """M9: 50 distinct keys, 50 stored outcomes -- the winner's and all 49 refusals.

    A conflict that stored nothing would make a retry of the *same* key re-enter the race, which is
    the duplicate-write hazard section 10.3 covers from the other direction.
    """
    fixture: RaceFixture = race["fixture"]
    stored = await work_session.scalar(
        text(
            "SELECT count(*) FROM public.idempotency_requests WHERE idempotency_key LIKE :prefix"
        ),
        {"prefix": f"proof-race-{fixture.run_id}-%"},
    )
    assert int(stored) == CONTENDERS


async def test_a_lapsed_hold_cannot_be_confirmed_even_before_the_sweeper_runs(race, work_session):
    """Section 0.8: "Never depend on the sweeper for correctness -- only for hygiene."

    Read before the sweep, at an instant past the TTL, `live_hold_for_shipment` must already report
    nothing. If this only became true after `sweep_held_holds` ran, a sweeper outage would leave
    lapsed holds confirmable.
    """
    winner = next(o for o in race["outcomes"] if not isinstance(o, BaseException) and o.code == "SLOT_HELD")
    row = (
        await work_session.execute(
            text("SELECT expires_at, state FROM public.dock_occupancy WHERE occupancy_id = :id"),
            {"id": int(winner.hold_id)},
        )
    ).mappings().first()
    assert row is not None and row["state"] == "HELD", "the hold was swept before this check ran"
    expires_at = row["expires_at"]

    live_before = await holds.live_hold_for_shipment(
        work_session, shipment_id=winner.shipment_id, now=expires_at - timedelta(seconds=1)
    )
    assert live_before is not None, "a hold inside its TTL is not visible to the read path"

    live_after = await holds.live_hold_for_shipment(
        work_session, shipment_id=winner.shipment_id, now=expires_at + timedelta(seconds=1)
    )
    assert live_after is None, (
        "a lapsed hold is still being reported as live before the sweeper has run -- "
        "section 0.8's lazy-expiry rule is not being applied"
    )


async def test_zero_orphaned_holds_after_the_ttl(race, work_sessionmaker):
    """Section 10.1's last clause. The clock is advanced deliberately; nothing sleeps.

    Three things are asserted, because "zero orphaned holds" means all three:
      1. the sweep transitions exactly the one lapsed hold, in place, to EXPIRED;
      2. no row is left in state HELD afterwards;
      3. the interval is genuinely released -- proved by a *new* contender successfully taking it,
         not by reading a column. A row labelled EXPIRED that still blocked capacity would satisfy
         (1) and (2) and still be an orphan.
    """
    fixture: RaceFixture = race["fixture"]
    winner_hold_id = int(
        next(o for o in race["outcomes"] if not isinstance(o, BaseException) and o.code == "SLOT_HELD").hold_id
    )

    async with work_sessionmaker() as session:
        expires_at = await session.scalar(
            text("SELECT expires_at FROM public.dock_occupancy WHERE occupancy_id = :id"),
            {"id": winner_hold_id},
        )
        assert expires_at is not None
        after_ttl = expires_at + timedelta(seconds=1)

        result = await holds.sweep_held_holds(
            session,
            actor_user_id=fixture.contenders[0].user_id,
            now=after_ttl,
            ttl_seconds=90,
        )
        await session.commit()

    record_evidence(
        "1. concurrency: holds swept after TTL",
        f"expired={result.expired} ttl_seconds={result.ttl_seconds} "
        f"deferred_or_lost={result.deferred_or_lost}",
    )
    assert result.supported is True
    assert result.expired == 1, f"sweep expired {result.expired} holds, expected 1"
    assert [h.hold_id for h in result.holds] == [str(winner_hold_id)]

    async with work_sessionmaker() as session:
        still_held = await session.scalar(
            text(
                """
                SELECT count(*) FROM public.dock_occupancy
                WHERE dock_id = :dock_id
                  AND "window" && tstzrange(:start, :end, '[)')
                  AND state = 'HELD'
                """
            ),
            {"dock_id": "DOCK-JAI-D1", "start": fixture.slot_start, "end": fixture.slot_end},
        )
        assert int(still_held) == 0

        swept_row = (
            await session.execute(
                text(
                    "SELECT state, expires_at FROM public.dock_occupancy WHERE occupancy_id = :id"
                ),
                {"id": winner_hold_id},
            )
        ).mappings().first()
        # In place, not deleted: migration 20260829134929's own reasoning -- the partial predicate
        # exists so a lapsed hold stops consuming capacity while remaining readable as evidence.
        assert swept_row is not None, "the sweeper deleted the row instead of expiring it"
        assert swept_row["state"] == "EXPIRED"
        assert swept_row["expires_at"] is None

    # (3) The interval really is free again. A second contender that lost the original race now
    # takes the same slot and must win outright.
    retry_contender = fixture.contenders[1]
    async with work_sessionmaker() as session:
        retry = await request_slot(
            session,
            retry_contender.ctx(),
            shipment_id=retry_contender.shipment_id,
            slot_id=fixture.slot_id,
            command=RequestSlotCommand(
                note="post-TTL re-acquisition",
                displayed_policy_version=load_scheduling_constraints().policy_version,
            ),
            idempotency_key=f"proof-race-{fixture.run_id}-retry",
        )
    record_evidence(
        "1. concurrency: interval re-acquirable after TTL",
        f"re-request returned {retry.code}",
    )
    assert retry.code == "SLOT_HELD", (
        f"the interval was not released after the TTL: {retry.code} "
        f"{getattr(retry, 'conflict', None)}"
    )


async def test_audit_trail_names_every_hold_transition(race, work_session):
    """M14: "every state change reconstructable". The winner's hold produced a CREATE_HOLD row and
    its lapse produced an EXPIRE_HOLD row -- both against `dock_occupancy`, both with the actor.

    This is also the check that would have caught the `audit_logs_action_type_check` defect the #53
    dry run found (CHANGELOG 2026-09-01): the CHECK admitted thirteen action types, none of them
    hold-related, so every `create_hold` would have died at COMMIT.
    """
    winner = next(o for o in race["outcomes"] if not isinstance(o, BaseException) and o.code == "SLOT_HELD")
    rows = (
        await work_session.execute(
            text(
                """
                SELECT action_type, user_id
                FROM public.audit_logs
                WHERE entity_name = 'dock_occupancy' AND entity_id = :entity_id
                ORDER BY audit_id
                """
            ),
            {"entity_id": str(winner.hold_id)},
        )
    ).mappings().all()
    actions = [str(row["action_type"]) for row in rows]
    assert "CREATE_HOLD" in actions, f"no CREATE_HOLD audit row for hold {winner.hold_id}"
    assert "EXPIRE_HOLD" in actions, f"no EXPIRE_HOLD audit row for hold {winner.hold_id}"
