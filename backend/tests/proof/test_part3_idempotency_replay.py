"""Section 10 part 3 -- idempotency replay of the seeded duplicate.

Design citation: `SOLUTION_DESIGN.md` section 10.3 --

    "Replay the seeded duplicate (`THR001`/`THR009`, same `dedupe_key`) -> exactly one exception,
     one booking attempt, one notification."

Also section 9.2's `duplicate_retry` row ("THR001 / THR009, same `dedupe_key` -> Exactly 1
exception, 1 hold attempt, 1 notification"), M9, and the database guide section 6's "Duplicate
driver message" case. GitHub issue #44.

## What the seeded duplicate actually is

`THR001` and `THR009` are two chat threads for the same driver (`DRV006`) and the same shipment
(`SHP1006`), opened 62 seconds apart, carrying the *same message text* and the *same*
`driver_exceptions.dedupe_key` (`DRV006-SHP1006-20260804-0934`). The second is the messaging-layer
retry. `EXC009` -- the exception attached to the retry -- is seeded with
`exception_status = 'DUPLICATE'`, and `MSG015` with `is_duplicate = 1`.

So there are two things worth proving, and the file proves both:

1. **The seed's own duplicate marking is intact** -- one dedupe key, two rows, exactly one of them
   counted as live work. If that ever silently became two live exceptions, every downstream SLA and
   queue count would double-report a single delay.
2. **A live replay through the real write path produces one of everything** -- the same retry
   delivered twice must not create a second exception, a second booking, or a second notification.

## The honest gap in "one notification"

Section 6.1 lists `notification_outbox` as a table to add ("Transactional outbox so a booking and
its notification cannot diverge"). It does not exist in `supabase/migrations/` -- verified by grep,
2026-09-01. The live analogue is `operational_messages`, which is what the notification assertion
below actually counts; the outbox-specific half is a named skip rather than a silent omission.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.allocation import RequestSlotCommand, request_slot
from app.scheduling.constraints import load_scheduling_constraints
from app.services.eta_service import EtaUpdateCommand, record_eta_update
from tests.proof.evidence import record_evidence
from tests.proof.harness import seed_race

pytestmark = pytest.mark.asyncio(loop_scope="session")

SEEDED_DEDUPE_KEY = "DRV006-SHP1006-20260804-0934"
DUPLICATE_SHIPMENT = "SHP1006"
DUPLICATE_DRIVER = "DRV006"
# The message text and external id of the original (THR001/MSG001) and its retry (THR009/MSG015).
ORIGINAL_EXTERNAL_ID = "wa-9001"
RETRY_EXTERNAL_ID = "wa-9009"

# The replay's own declared ETA. Deliberately different from the seeded 11:20 so the assertion
# "exactly one exception" cannot pass by accident because nothing changed.
REPLAY_ETA = "2026-08-04T11:45:00+05:30"

REPLAY_USER_ID = "USR-PROOF-DRV006"


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="proof-idempotency-replay",
        auth_subject="proof-idempotency-replay",
        user_id=REPLAY_USER_ID,
        email="proof.drv006@proof.invalid",
        full_name="Proof DRV006",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id=DUPLICATE_DRIVER,
        facility_id="FAC-JAI-01",
    )


async def _ensure_replay_user(session) -> None:
    """DRV006 has no seeded login account, and `audit_logs.user_id` is NOT NULL REFERENCES users.

    Adding the account is not inventing operational data: the driver, the shipment, the threads and
    the exceptions are all real seed rows; this is only the identity the write path attributes its
    audit entry to.
    """
    await session.execute(
        text(
            """
            INSERT INTO public.users (
              user_id, role_id, employee_code, full_name, email, phone_number,
              password_hash, driver_id, facility_id, is_active
            ) VALUES (
              :user_id, 'ROL001', 'EMP-PROOF-DRV006', 'Proof DRV006',
              'proof.drv006@proof.invalid', NULL, 'proof-suite-no-login',
              :driver_id, 'FAC-JAI-01', 1
            )
            ON CONFLICT (user_id) DO NOTHING
            """
        ),
        {"user_id": REPLAY_USER_ID, "driver_id": DUPLICATE_DRIVER},
    )
    await session.commit()


# ----------------------------------------------------------------------------------------------
# 1. The seeded duplicate itself
# ----------------------------------------------------------------------------------------------


async def test_the_seeded_retry_shares_one_dedupe_key_across_two_threads(seed_session):
    rows = (
        await seed_session.execute(
            text(
                """
                SELECT exception_id, thread_id, exception_status, dedupe_key
                FROM public.driver_exceptions
                WHERE dedupe_key = :key
                ORDER BY exception_id
                """
            ),
            {"key": SEEDED_DEDUPE_KEY},
        )
    ).mappings().all()
    threads = {str(row["thread_id"]) for row in rows}
    assert threads == {"THR001", "THR009"}, f"the seeded duplicate pair changed shape: {threads}"


async def test_only_one_of_the_seeded_pair_counts_as_live_work(seed_session):
    """Section 9.2's `duplicate_retry`: "Exactly 1 exception".

    Two rows exist -- the retry is preserved as evidence, which is right -- but exactly one of them
    is not marked DUPLICATE. A dedupe key that produced two live exceptions would double every
    queue count and every SLA clock derived from it.
    """
    live = (
        await seed_session.execute(
            text(
                """
                SELECT exception_id, exception_status
                FROM public.driver_exceptions
                WHERE dedupe_key = :key
                  AND exception_status <> 'DUPLICATE'
                """
            ),
            {"key": SEEDED_DEDUPE_KEY},
        )
    ).mappings().all()
    assert len(live) == 1, f"expected exactly one non-duplicate exception, got {live}"
    assert str(live[0]["exception_id"]) == "EXC001"


async def test_the_retry_message_is_flagged_and_the_original_is_not(seed_session):
    rows = (
        await seed_session.execute(
            text(
                """
                SELECT external_message_id, is_duplicate, thread_id
                FROM public.chat_messages
                WHERE external_message_id IN (:original, :retry)
                """
            ),
            {"original": ORIGINAL_EXTERNAL_ID, "retry": RETRY_EXTERNAL_ID},
        )
    ).mappings().all()
    flags = {str(row["external_message_id"]): int(row["is_duplicate"]) for row in rows}
    assert flags == {ORIGINAL_EXTERNAL_ID: 0, RETRY_EXTERNAL_ID: 1}


async def test_exactly_one_booking_exists_for_the_duplicated_shipment(seed_session):
    """"one booking attempt" -- one live appointment for SHP1006 despite the doubled message."""
    count = await seed_session.scalar(
        text(
            """
            SELECT count(*) FROM public.appointments
            WHERE shipment_id = :shipment_id
              AND is_current = 1
              AND appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
            """
        ),
        {"shipment_id": DUPLICATE_SHIPMENT},
    )
    assert int(count) == 1


# ----------------------------------------------------------------------------------------------
# 2. A live replay through the real write path
# ----------------------------------------------------------------------------------------------


async def test_replaying_the_same_retry_writes_exactly_one_of_everything(work_sessionmaker):
    """The section 10.3 assertion proper: the same delivery, twice, changes the database once.

    Counted before, between and after -- an absolute count would pass trivially if the seed already
    happened to hold the right number, whereas a *delta* of zero on the second call is the property
    idempotency actually claims.
    """
    async with work_sessionmaker() as session:
        await _ensure_replay_user(session)

    key = f"proof-dupe-{uuid4().hex[:10]}"
    command = EtaUpdateCommand(
        declared_eta_ts=REPLAY_ETA,
        delay_reason_code="TRAFFIC",
        confidence_code="MEDIUM",
        reported_delay_min=60,
        exception_type="TRAFFIC",
        description="Traffic after Shahpura. Reaching around 11:45.",
        thread_id="THR001",
        confirmed=True,
        confirmation_eta_ts=REPLAY_ETA,
        client_message_id=RETRY_EXTERNAL_ID + "-proof",
    )

    async def counts(session) -> dict[str, int]:
        return {
            "eta_updates": int(
                await session.scalar(
                    text(
                        "SELECT count(*) FROM public.eta_updates WHERE shipment_id = :s"
                    ),
                    {"s": DUPLICATE_SHIPMENT},
                )
            ),
            "exceptions": int(
                await session.scalar(
                    text(
                        "SELECT count(*) FROM public.driver_exceptions WHERE shipment_id = :s"
                    ),
                    {"s": DUPLICATE_SHIPMENT},
                )
            ),
            "chat_messages": int(
                await session.scalar(
                    text(
                        """
                        SELECT count(*) FROM public.chat_messages
                        WHERE thread_id IN (
                            SELECT thread_id FROM public.chat_threads WHERE shipment_id = :s
                        )
                        """
                    ),
                    {"s": DUPLICATE_SHIPMENT},
                )
            ),
            # The live notification table. `notification_outbox` (section 6.1) does not exist --
            # see this module's docstring and the named skip below.
            "notifications": int(
                await session.scalar(
                    text(
                        "SELECT count(*) FROM public.operational_messages WHERE shipment_id = :s"
                    ),
                    {"s": DUPLICATE_SHIPMENT},
                )
            ),
            "idempotency": int(
                await session.scalar(
                    text(
                        "SELECT count(*) FROM public.idempotency_requests WHERE idempotency_key = :k"
                    ),
                    {"k": key},
                )
            ),
        }

    async with work_sessionmaker() as session:
        before = await counts(session)

    async with work_sessionmaker() as session:
        first = await record_eta_update(
            session, ctx=_driver_ctx(), shipment_id=DUPLICATE_SHIPMENT, command=command,
            idempotency_key=key,
        )
    assert first.get("idempotent_replay") is False

    async with work_sessionmaker() as session:
        after_first = await counts(session)

    async with work_sessionmaker() as session:
        second = await record_eta_update(
            session, ctx=_driver_ctx(), shipment_id=DUPLICATE_SHIPMENT, command=command,
            idempotency_key=key,
        )
    assert second.get("idempotent_replay") is True, "the replay was not recognised as a replay"

    async with work_sessionmaker() as session:
        after_second = await counts(session)

    # The first delivery does its work: one ETA row, one chat message, one idempotency record.
    assert after_first["eta_updates"] == before["eta_updates"] + 1
    assert after_first["chat_messages"] == before["chat_messages"] + 1
    assert after_first["idempotency"] == 1
    # And it does NOT open a second exception: SHP1006 already has an open one (EXC001), which the
    # service updates in place. "Exactly one exception" is a property of the data, not of the call
    # count, so it is asserted as a zero delta rather than as "== 1".
    assert after_first["exceptions"] == before["exceptions"], (
        "the ETA write opened a second exception for a shipment that already had a live one"
    )
    assert after_first["notifications"] == before["notifications"]

    record_evidence(
        "3. idempotency: eta replay row deltas",
        "first call " + str({k: after_first[k] - before[k] for k in before})
        + " / replay " + str({k: after_second[k] - after_first[k] for k in before}),
    )
    # The replay changes nothing at all.
    assert after_second == after_first, (
        "replaying the same dedupe key wrote again:\n"
        f"  first : {after_first}\n"
        f"  second: {after_second}"
    )


async def test_replayed_exception_carries_exactly_one_live_row_for_the_shipment(work_session):
    """After the replay, `SHP1006` must still have exactly one exception that is not a duplicate.

    The strongest form of "exactly one exception": not "the count did not change", but "the count
    is one" -- the seed's EXC009 is DUPLICATE, and an ETA write must not promote it or add a third
    live row.

    **This assertion currently FAILS, and it is failing correctly** -- see the message below. It is
    deliberately left as a hard failure rather than an xfail: issue #44's own rollback note says
    "If it fails, the failure identifies which upstream milestone needs rework -- do not weaken the
    assertions to make it pass."
    """
    rows = (
        await work_session.execute(
            text(
                """
                SELECT exception_id, exception_status, dedupe_key
                FROM public.driver_exceptions
                WHERE shipment_id = :s AND exception_status <> 'DUPLICATE'
                ORDER BY exception_id
                """
            ),
            {"s": DUPLICATE_SHIPMENT},
        )
    ).mappings().all()
    record_evidence(
        "3. idempotency: live exceptions on SHP1006 after replay",
        f"{len(rows)} (expected 1) -> "
        + str([(r["exception_id"], r["exception_status"], r["dedupe_key"]) for r in rows]),
    )
    assert len(rows) == 1, (
        f"SHP1006 has {len(rows)} live exceptions, expected 1: {[dict(r) for r in rows]}\n"
        "\n"
        "ROOT CAUSE (product defect, reported not fixed by this suite):\n"
        "  backend/app/services/eta_service.py, the `open_exc` lookup inside record_eta_update:\n"
        "      WHERE driver_id = :driver_id AND shipment_id = :shipment_id\n"
        "        AND exception_status NOT IN ('CLOSED', 'RESOLVED')\n"
        "      ORDER BY reported_at DESC LIMIT 1\n"
        "  1. 'DUPLICATE' is not excluded, so the seeded retry row (EXC009) is selected as 'the\n"
        "     open exception' and UPDATEd in place -- its status flips DUPLICATE -> OPEN and its\n"
        "     dedupe_key is overwritten with the new client_message_id. A row the system had\n"
        "     already identified as a duplicate is resurrected into live work by the next\n"
        "     ordinary ETA update on that shipment.\n"
        "  2. ORDER BY reported_at DESC picks the duplicate *preferentially*, because a messaging\n"
        "     retry always carries a later timestamp than the message it duplicates.\n"
        "  3. 'CANCELLED' is likewise not excluded, and 'CLOSED' -- which IS excluded -- is not a\n"
        "     value driver_exceptions_exception_status_check even permits\n"
        "     (OPEN/NEEDS_INFORMATION/SLOT_OPTIONS_SHARED/WAITING_CONFIRMATION/RESOLVED/\n"
        "      ESCALATED/DUPLICATE/CANCELLED).\n"
        "  Consequence: SOLUTION_DESIGN.md section 9.2's `duplicate_retry` guarantee ('Exactly 1\n"
        "  exception') is violated, and the dedupe_key linking the retry to its original is lost."
    )


async def test_a_replayed_request_slot_makes_exactly_one_booking_attempt(work_sessionmaker):
    """"one booking attempt", proved on the booking path rather than inferred from the ETA path.

    M9's own hazard: a retried `request_slot` must not take a second interval. The same key is
    replayed against a fresh contested slot and the database is then asked how many capacity claims
    exist -- one, and it is the same `hold_id` both calls returned.
    """
    run_id = uuid4().hex[:8].upper()
    async with work_sessionmaker() as session:
        # A private slot for this test: 8 hours after the part-1 fixture so the two never share an
        # interval on the same dock.
        fixture = await seed_race(session, run_id=run_id, contenders=1, start_offset_minutes=480)

    contender = fixture.contenders[0]
    key = f"proof-booking-replay-{run_id}"
    command = RequestSlotCommand(
        note="section 10.3 booking replay",
        displayed_policy_version=load_scheduling_constraints().policy_version,
    )

    async with work_sessionmaker() as session:
        first = await request_slot(
            session, contender.ctx(), shipment_id=contender.shipment_id,
            slot_id=fixture.slot_id, command=command, idempotency_key=key,
        )
    async with work_sessionmaker() as session:
        second = await request_slot(
            session, contender.ctx(), shipment_id=contender.shipment_id,
            slot_id=fixture.slot_id, command=command, idempotency_key=key,
        )

    assert first.code == "SLOT_HELD"
    assert second.code == "SLOT_HELD"
    assert second.idempotent_replay is True
    assert second.hold_id == first.hold_id, "the retry produced a SECOND hold on the same interval"

    async with work_sessionmaker() as session:
        claims = await session.scalar(
            text(
                """
                SELECT count(*) FROM public.dock_occupancy
                WHERE shipment_id = :s
                  AND state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
                """
            ),
            {"s": contender.shipment_id},
        )
        stored = await session.scalar(
            text("SELECT count(*) FROM public.idempotency_requests WHERE idempotency_key = :k"),
            {"k": key},
        )
    record_evidence(
        "3. idempotency: booking replay",
        f"2 calls, hold_id {first.hold_id} both times, {claims} capacity claim(s), "
        f"{stored} idempotency row(s)",
    )
    assert int(claims) == 1, f"one booking attempt produced {claims} capacity claims"
    assert int(stored) == 1


@pytest.mark.skip(
    reason=(
        "NAMED SKIP, not a silent omission (issue #44). Section 10.3's 'one notification' is "
        "asserted above against `operational_messages`, the table that actually exists. The "
        "outbox-specific half of the claim -- section 6.1's `notification_outbox`, 'a "
        "transactional outbox so a booking and its notification cannot diverge' -- cannot be "
        "asserted because that table has never been created: no `CREATE TABLE "
        "notification_outbox` exists anywhere in supabase/migrations/ (verified by grep "
        "2026-09-01). This is an unbuilt design element, not a failing one."
    )
)
async def test_notification_outbox_receives_exactly_one_row_per_dedupe_key():
    raise AssertionError("unreachable while the skip stands")
