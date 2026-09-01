"""`hold_for_information`'s full lifecycle against a real cluster -- GitHub issue #64.

Design citation: `SOLUTION_DESIGN.md` section 7.5.1 (*"`HELD_FOR_INFO` + `new_deadline`. **Pauses
the D9 clock exactly once** per request; a second call returns `HOLD_ALREADY_USED`. Without that
cap, 'hold for info' becomes an unbounded way to sit on capacity"*), section 4 (the promise
lifecycle -- there is no paused state, so a held request stays `PENDING_CONFIRMATION`), D9, M9, M14,
M15, `ARCHITECTURE/REQUIREMENTS.md` **FR-PLN-004**,
`UI-UX/03-planner-dock-board/flows-and-states.md` Flow 4, `edge-cases.md` #6.

**Not one of section 10's six parts**, like parts 7-10 before it: it lives here because it needs the
same throwaway cluster, and because everything it proves is a property of PostgreSQL rather than of
Python.

## Why the unit tests are not enough

`tests/unit/test_planner_write_tools.py` pins the payloads and the refusals against a mocked
session. Three things it structurally cannot reach, all of which are exactly where this feature
would break in production:

* **`audit_logs_action_type_check`.** Sixteen permitted values
  (`20260829134929_d2_held_state_dock_occupancy.sql:290-296`), none of them hold-specific. This tool
  writes `UPDATE` with the discriminator in `new_value_json.transition` precisely because of that
  CHECK -- and a mock evaluates no CHECK, so only a real COMMIT proves the choice was right. The
  migration's own comment records the near-miss that made this worth testing: `CREATE_HOLD` had to
  be added by migration or *"every `create_hold` would have failed at COMMIT ... No unit test could
  have caught it."*
* **`appointments.expires_at` exists and is `timestamptz`.** asyncpg refuses to coerce a `str` into
  a timestamptz parameter (the `DataError` `expiry.py` documents). A mock accepts either.
* **The sweeper's two-deadline CASE actually discriminating.** The whole behavioural content of
  "pauses the D9 clock" is that a held request stops being due at `booked_at + ttl` and becomes due
  at its stored `expires_at` instead. That is a `WHERE` clause evaluated by PostgreSQL over real
  rows, and the assertion below runs it against a held row and an unheld control **in the same
  scan, at the same instant**, and requires opposite answers.

## Why this file never calls `sweep_expired_appointments`

The work database is shared with parts 1, 3, 6, 7 and 8, and this file sorts *before* them
(`part10` < `part11` < `part1_concurrency` -- `'0'` < `'1'` < `'_'`). A full sweep run at a clock
20 minutes in the future would expire every `PENDING_CONFIRMATION` row those parts depend on,
including the winner of section 10.1's 50-way race. So the sweeper is exercised through its two
real components instead: `_pending_candidates` (read-only -- this is where the two-deadline CASE
lives, so it is the assertion that matters) and `_expire_one_pending` (writes exactly the one
appointment it is handed). The batching and commit-per-row behaviour around them is unit-tested.

## Why the fixture ages `booked_at`

A hold sets `new_deadline = now + one further D9 TTL`, so holding a request one second after
booking it extends the deadline by one second -- true, and useless as a test. Section 9.1's rule is
to inject time rather than wait for it; the appointment's own clock is `booked_at`, so the fixture
moves that backwards to simulate a request that has been sitting in the queue for 14 of its 15
minutes, which is when a planner actually reaches for Hold. That is a fixture manipulation of a
column, not a code path: nothing in the application ever rewrites `booked_at`, and
`counter_offer`'s docstring explains at length why it must not.
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
from app.core.settings import get_settings
from app.scheduling import expiry
from app.scheduling.allocation import (
    ConfirmAppointmentCommand,
    HoldForInformationCommand,
    RequestSlotCommand,
    confirm_appointment,
    hold_for_information,
    request_slot,
)
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.holds import confirm_held_slot
from app.scheduling.snapshot import load_appointment_snapshot
from tests.proof import harness
from tests.proof.evidence import record_evidence
from tests.proof.harness import seed_race

pytestmark = pytest.mark.asyncio(loop_scope="session")

# The seeded planner account. `audit_logs.user_id` is NOT NULL REFERENCES users(user_id), so the
# actor a hold is attributed to has to be a real row -- the same hard requirement part 8 documents.
PLANNER_USER_ID = "USR101"
PLANNER_ROLE_ID = "ROL002"

# A whole number of days past the harness's own 2099-03-01 10:00 IST base, following the convention
# part 7 established (2880/4320/5760/7200 -- one day apart, same time of day). 8640 is
# 2099-03-07 10:00 IST: clear of every other part's fixtures, and still inside FAC-JAI-01's seeded
# 06:00-22:00 window and below RULE005's 21:00 LAST_NEW_START_TIME, which the harness's docstring
# requires or Stage 1 would refuse every candidate and this file would prove nothing.
START_OFFSET_MINUTES = 8640

# How aged the fixture requests are when the planner reaches for Hold: 14 minutes into a 15-minute
# D9 window, so one minute of the original clock remains and the extension is unmistakable.
AGE_MINUTES = 14


def _planner_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="proof-part11",
        auth_subject="proof-part11",
        user_id=PLANNER_USER_ID,
        email="priya.mehta@setuhaul.com",
        full_name="Priya Mehta",
        role_id=PLANNER_ROLE_ID,
        role_name=RoleName.WAREHOUSE_PLANNER,
        facility_id=harness.FACILITY_ID,
    )


async def _book_pending(sessionmaker, contender, slot_id: str) -> str:
    """Drive one shipment to `PENDING_CONFIRMATION` through the real two-phase path.

    Not an INSERT: the point of booking through `request_slot` + `confirm_held_slot` is that the
    appointment under test has a genuine `dock_occupancy` claim behind it, so the expiry leg below
    releases real capacity rather than a row nothing was holding.

    Two sessions, one per phase, because that is how the two calls actually arrive in production --
    a driver's hold and their confirm are separate requests, and D2's whole point is that capacity
    survives between them.
    """
    async with sessionmaker() as session:
        held = await request_slot(
            session,
            contender.ctx(),
            shipment_id=contender.shipment_id,
            slot_id=slot_id,
            command=RequestSlotCommand(
                note="issue #64 hold-for-information fixture",
                displayed_policy_version=load_scheduling_constraints().policy_version,
            ),
            idempotency_key=f"proof11-request-{uuid4().hex[:8]}",
        )
    assert held.code == "SLOT_HELD", held.model_dump()

    async with sessionmaker() as session:
        confirmed = await confirm_held_slot(
            session,
            contender.ctx(),
            hold_id=str(held.hold_id),
            idempotency_key=f"proof11-confirm-{uuid4().hex[:8]}",
        )
    assert confirmed.code == "SLOT_REQUESTED", confirmed.model_dump()
    return str(confirmed.appointment_id)


async def _age_booked_at(session, appointment_id: str, minutes: int) -> datetime:
    """Move one appointment's D9 anchor backwards. Returns the new `booked_at`. Commits."""
    aged = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    await session.execute(
        text("UPDATE public.appointments SET booked_at = :ts WHERE appointment_id = :id"),
        {"ts": aged, "id": appointment_id},
    )
    await session.commit()
    return aged


async def _row(session, appointment_id: str) -> dict:
    return dict(
        (
            await session.execute(
                text(
                    """
                    SELECT appointment_id, appointment_status, is_current, booked_at, expires_at
                    FROM public.appointments WHERE appointment_id = :id
                    """
                ),
                {"id": appointment_id},
            )
        ).mappings().one()
    )


async def _hold_audit_rows(session, appointment_id: str) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT audit_id, user_id, action_type, entity_name, entity_id,
                       old_value_json, new_value_json, created_at
                FROM public.audit_logs
                WHERE entity_name = 'appointments' AND entity_id = :id
                ORDER BY created_at, audit_id
                """
            ),
            {"id": appointment_id},
        )
    ).mappings().all()
    decoded = []
    for row in rows:
        item = dict(row)
        item["new_value"] = json.loads(item["new_value_json"]) if item["new_value_json"] else None
        item["old_value"] = json.loads(item["old_value_json"]) if item["old_value_json"] else None
        decoded.append(item)
    return decoded


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def held_requests(work_sessionmaker):
    """Three aged `PENDING_CONFIRMATION` requests on their own intervals.

    Session-scoped and built once: booking three shipments through the real two-phase path is the
    expensive part, and the three tests below each consume a different one (held, control, resume)
    so none of them can perturb another's row.
    """
    run_id = uuid4().hex[:6].upper()
    async with work_sessionmaker() as session:
        fixture = await seed_race(
            session,
            run_id=run_id,
            contenders=3,
            start_offset_minutes=START_OFFSET_MINUTES,
            alternatives=2,
        )

    # Each contender takes a different interval -- the contested slot plus the two alternatives --
    # because D1's exclusion constraint would (correctly) refuse three claims on one dock interval.
    slots = (fixture.slot_id, *fixture.alternative_slot_ids)
    appointments = []
    for contender, slot_id in zip(fixture.contenders, slots, strict=True):
        appointment_id = await _book_pending(work_sessionmaker, contender, slot_id)
        async with work_sessionmaker() as session:
            await _age_booked_at(session, appointment_id, AGE_MINUTES)
        appointments.append(appointment_id)

    return {
        "held": appointments[0],
        "control": appointments[1],
        "resume": appointments[2],
        "shipments": {
            appointments[index]: fixture.contenders[index].shipment_id for index in range(3)
        },
    }


# --------------------------------------------------------------------------------------------
# 1. The hold itself
# --------------------------------------------------------------------------------------------


async def test_holding_a_request_moves_its_deadline_and_writes_a_real_audit_row(
    work_session, held_requests
):
    """FR-PLN-004 end to end: the extension lands in `appointments.expires_at`, and the audit row
    survives `audit_logs_action_type_check` and the `users` foreign key at COMMIT."""
    appointment_id = held_requests["held"]
    shipment_id = held_requests["shipments"][appointment_id]
    ttl = get_settings().pending_confirmation_ttl_minutes

    before = await _row(work_session, appointment_id)
    assert before["expires_at"] is None, "fixture request already carries a deadline override"

    result = await hold_for_information(
        work_session,
        _planner_ctx(),
        shipment_id=shipment_id,
        command=HoldForInformationCommand(
            appointment_id=appointment_id,
            question="Is the reefer unit running? The manifest says ambient.",
        ),
        idempotency_key=f"proof11-hold-{uuid4().hex[:8]}",
    )

    assert result.code == "HELD_FOR_INFO"
    # Section 4 has no paused state; a held request is still a pending request.
    assert result.status == "PENDING_CONFIRMATION"
    assert result.extension_minutes == ttl

    after = await _row(work_session, appointment_id)
    assert after["appointment_status"] == "PENDING_CONFIRMATION"
    assert after["expires_at"] is not None
    assert after["expires_at"].isoformat() == result.new_deadline
    # The extension really is forward of where the D9 clock was about to run out -- with one minute
    # left on a 14-minute-old request, the new deadline has to be ~14 minutes further out.
    assert after["expires_at"] > before["booked_at"] + timedelta(minutes=ttl)
    # `booked_at` is untouched: it is the D9 anchor and the request's own history.
    assert after["booked_at"] == before["booked_at"]

    audit = [
        row for row in await _hold_audit_rows(work_session, appointment_id)
        if (row["new_value"] or {}).get("transition") == "HELD_FOR_INFO"
    ]
    assert len(audit) == 1, "the hold wrote no HELD_FOR_INFO audit row (or wrote two)"
    entry = audit[0]
    assert entry["user_id"] == PLANNER_USER_ID          # the FK resolved
    assert entry["action_type"] == "UPDATE"             # inside the sixteen-value CHECK
    assert entry["new_value"]["question"].startswith("Is the reefer unit running?")
    assert entry["new_value"]["new_deadline"] == result.new_deadline
    assert entry["new_value"]["hold_used"] is True
    assert entry["old_value"]["expires_at"] is None
    record_evidence(
        "11. #64: hold extension",
        f"{result.previous_deadline} -> {result.new_deadline} (+{ttl}m, one-shot)",
    )


async def test_a_second_hold_is_refused_and_leaves_the_first_deadline_alone(
    work_session, held_requests
):
    """Section 7.5.1's cap, and `edge-cases.md` #6's reason for it: the deadline the second call
    would have written must not land, or "exactly once" is a comment rather than a property."""
    appointment_id = held_requests["held"]
    shipment_id = held_requests["shipments"][appointment_id]
    before = await _row(work_session, appointment_id)

    with pytest.raises(AppError) as exc:
        await hold_for_information(
            work_session,
            _planner_ctx(),
            shipment_id=shipment_id,
            command=HoldForInformationCommand(
                appointment_id=appointment_id, question="Any update on the reefer?"
            ),
            idempotency_key=f"proof11-hold2-{uuid4().hex[:8]}",
        )
    assert exc.value.code == "HOLD_ALREADY_USED"
    await work_session.rollback()

    after = await _row(work_session, appointment_id)
    assert after["expires_at"] == before["expires_at"]
    holds = [
        row for row in await _hold_audit_rows(work_session, appointment_id)
        if (row["new_value"] or {}).get("transition") == "HELD_FOR_INFO"
    ]
    assert len(holds) == 1, "the refused second hold still wrote an audit row"


# --------------------------------------------------------------------------------------------
# 2. The expiry leg -- the two-deadline CASE, discriminating for real
# --------------------------------------------------------------------------------------------


async def test_the_sweeper_scan_spares_the_held_request_and_takes_the_unheld_control(
    work_session, held_requests
):
    """One scan, one instant, opposite answers -- which is the entire behaviour of "pauses the D9
    clock".

    Both requests were booked 14 minutes ago, so both are past `booked_at + 15` at the instant
    below. The only difference between them is the stored `expires_at` the hold wrote, and
    `expiry._pending_candidates`' CASE is the only thing that can act on it. If that predicate
    regressed to the pre-#64 `booked_at`-only form, the held request would appear here and the hold
    would have bought the driver nothing at all.
    """
    ttl = get_settings().pending_confirmation_ttl_minutes
    held_id = held_requests["held"]
    control_id = held_requests["control"]
    held_row = await _row(work_session, held_id)

    # A minute past the original derived deadline, and comfortably inside the extension.
    now = held_row["booked_at"] + timedelta(minutes=ttl + 1)
    assert now < held_row["expires_at"], "fixture aging left no window to assert in"

    candidates = {
        str(row["appointment_id"])
        for row in await expiry._pending_candidates(
            work_session, deadline=now - timedelta(minutes=ttl), now=now, limit=200
        )
    }
    assert control_id in candidates, "the unheld control was not due -- the fixture is not aged"
    assert held_id not in candidates, (
        "the held request is still due at booked_at + ttl; the extension did nothing"
    )
    record_evidence(
        "11. #64: two-deadline scan",
        f"held={held_id} spared, control={control_id} due, at booked_at+{ttl + 1}m",
    )


async def test_the_held_request_does_expire_once_its_extended_deadline_passes(
    work_session, held_requests
):
    """The other half of the cap: an extension is a *bounded* one, not an escape from D9.

    Expired through `_expire_one_pending` -- the sweeper's real per-row transition, including the
    capacity release and the `PENDING_EXPIRED_UNACTIONED` escalation -- rather than through a full
    sweep, for the reason in this module's docstring.
    """
    held_id = held_requests["held"]
    row = await _row(work_session, held_id)
    now = row["expires_at"] + timedelta(minutes=1)

    candidates = {
        str(candidate["appointment_id"])
        for candidate in await expiry._pending_candidates(
            work_session,
            deadline=now - timedelta(minutes=get_settings().pending_confirmation_ttl_minutes),
            now=now,
            limit=200,
        )
    }
    assert held_id in candidates, "the extension never runs out -- that is unbounded capacity"

    released = await expiry._expire_one_pending(
        work_session, appointment_id=held_id, actor_user_id=PLANNER_USER_ID, now=now
    )
    await work_session.commit()
    assert released is True, "the expiring hold released no dock claim"

    after = await _row(work_session, held_id)
    assert after["appointment_status"] == "EXPIRED"
    assert int(after["is_current"]) == 0
    # D9's "release + escalate": the interval is genuinely free again.
    claims = await work_session.scalar(
        text("SELECT count(*) FROM public.dock_occupancy WHERE appointment_id = :id"),
        {"id": held_id},
    )
    assert int(claims) == 0
    escalations = await work_session.scalar(
        text(
            """
            SELECT count(*) FROM public.escalation_queue
            WHERE dedupe_key = :key AND escalation_type = 'PENDING_EXPIRED_UNACTIONED'
            """
        ),
        {"key": f"PENDING-EXPIRED-{held_id}"},
    )
    assert int(escalations) == 1


# --------------------------------------------------------------------------------------------
# 3. The resume leg -- Flow 4 step 4, the reason the extension exists
# --------------------------------------------------------------------------------------------


async def test_a_held_request_is_still_confirmable_after_its_original_deadline(
    work_session, held_requests
):
    """Flow 4 step 4: the driver answers, and the planner acts on a request that would otherwise
    have lapsed.

    This is the leg that makes the feature worth having, and it is deliberately proven through the
    real `confirm_request` path rather than by re-reading `expires_at`: the hold is only meaningful
    if the *forward* transition still works inside the window it bought, not merely if the sweeper
    leaves the row alone.
    """
    appointment_id = held_requests["resume"]
    shipment_id = held_requests["shipments"][appointment_id]
    ttl = get_settings().pending_confirmation_ttl_minutes

    hold = await hold_for_information(
        work_session,
        _planner_ctx(),
        shipment_id=shipment_id,
        command=HoldForInformationCommand(
            appointment_id=appointment_id, question="Which gate is the driver at?"
        ),
        idempotency_key=f"proof11-resume-hold-{uuid4().hex[:8]}",
    )
    row = await _row(work_session, appointment_id)
    # The original D9 window really has run out; only the extension keeps this row alive.
    assert row["booked_at"] + timedelta(minutes=ttl) < datetime.fromisoformat(hold.new_deadline)

    snapshot = await load_appointment_snapshot(
        work_session, appointment_id, actor_user_id=PLANNER_USER_ID
    )
    result = await confirm_appointment(
        work_session,
        _planner_ctx(),
        shipment_id=shipment_id,
        command=ConfirmAppointmentCommand(
            appointment_id=appointment_id,
            snapshot_hash=snapshot["snapshot_hash"],
            warehouse_confirmation_ref=f"WMS-PROOF11-{uuid4().hex[:6].upper()}",
        ),
        idempotency_key=f"proof11-resume-confirm-{uuid4().hex[:8]}",
    )

    assert result.status == "CONFIRMED"
    after = await _row(work_session, appointment_id)
    assert after["appointment_status"] == "CONFIRMED"
    record_evidence(
        "11. #64: resume path",
        f"{appointment_id} confirmed inside the extension it was held for",
    )
