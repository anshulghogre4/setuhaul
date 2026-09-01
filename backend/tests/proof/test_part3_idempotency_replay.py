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

import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.allocation import RequestSlotCommand, request_slot
from app.scheduling.constraints import load_scheduling_constraints
from app.services import escalation_service
from app.services.escalation_service import (
    EscalateExceptionCommand,
    acknowledge_escalation,
    cancel_escalation,
    escalate_exception,
    resolve_escalation,
)
from app.services.eta_service import EtaUpdateCommand, record_eta_update
from tests.proof import harness
from tests.proof.evidence import record_evidence
from tests.proof.harness import Contender, seed_race

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


# ----------------------------------------------------------------------------------------------
# 3. Issue #96 -- the daily dedupe must not hand back a TERMINAL escalation
# ----------------------------------------------------------------------------------------------
#
# Same family as everything above (a dedupe key deciding whether a second event is "the same
# event"), and the same failure shape as the eta_service defect asserted at line 314: a row the
# system had already finished with gets resurrected by the next ordinary write.
#
# `escalate_exception` keys on `<shipment>:<calendar-day>:<type>` and its `ON CONFLICT DO UPDATE`
# never touched `escalation_status`. With a GLOBAL unique index on `dedupe_key`
# (20260812010000:69) the conflict fired against the prior row whatever state it was in -- so once
# a coordinator resolved or cancelled today's case, the driver's next genuinely new problem of the
# same type returned that dead row, which `get_escalation_queue` filters out by design. Nobody ever
# saw it. Found 2026-09-01 by E6.2's race suites 3/4 (issue #43), which pass alone and failed in
# sequence; the suites work around it by rotating the nine escalation types, the product cannot.
#
# Fix (owner-decided option (b), migration 20260901120000): uniqueness is scoped to NON-TERMINAL
# rows via a partial unique index, so a terminal row is simply not a conflict candidate any more.
# Terminal = {RESOLVED, CANCELLED} and nothing else -- SOLUTION_DESIGN.md section 7.4 ("OPEN ->
# ACKNOWLEDGED -> IN_PROGRESS -> RESOLVED (plus CANCELLED)"), REQUIREMENTS.md FR-OPS-006 ("two
# terminal states"), and the CHECK constraint at 20260823100000:49-52 which permits no other value.
#
# These run against the real cluster on purpose. Every assertion below is about what PostgreSQL's
# index inference does, which no mocked session can answer -- and the partial index only exists
# here because the orchestrator replays the migration chain, so a green run IS the migration's
# dry run.

ESCALATION_SOURCE_ROOT = Path(escalation_service.__file__).resolve().parents[1]
# Must stay byte-identical to `escalation_queue_dedupe_key_active_uidx`'s predicate. Asserted
# against the live catalog below, not just against the source strings.
ARBITER_PREDICATE = "ON CONFLICT (dedupe_key) WHERE escalation_status NOT IN ('RESOLVED', 'CANCELLED')"
TERMINAL_STATUSES = ("RESOLVED", "CANCELLED")

# The table an `ON CONFLICT` arbiter belongs to, resolved from the nearest preceding INSERT.
#
# Added 2026-09-02 with issue #94. The scan below used to assume `ON CONFLICT (dedupe_key)` could
# only ever mean `escalation_queue` -- true when it was written, and false the moment
# `20260902093000_notification_outbox.sql` added a second table with a `dedupe_key`.
# `notification_outbox` is upserted with a BARE `ON CONFLICT (dedupe_key)`, and correctly so: its
# unique index (`notification_outbox_dedupe_key_uidx`) is NOT partial, so there is no
# index_predicate to repeat and adding escalation_queue's would make the arbiter match nothing.
# Requiring the predicate everywhere would therefore have failed a correct file.
_INSERT_TARGET = re.compile(r"INSERT INTO\s+public\.(\w+)")


def _ops_ctx(*, user_id: str, request_id: str) -> ExecutionContext:
    """A facility-scoped coordinator for `harness.FACILITY_ID`.

    `user_id` is a REAL row from `seed_race`'s fixture rather than a synthetic string: only
    `acknowledge_escalation` needs it (it writes `owner_user_id`, which carries an FK to
    `public.users` since 20260825210000), but reusing one identity across all four tools keeps the
    `resolved_by_user_id` values meaningful too. That column has no FK, checked in the migrations,
    so this is for readability rather than to satisfy the database.
    """
    return ExecutionContext(
        request_id=request_id,
        auth_subject=request_id,
        user_id=user_id,
        email="proof.ops.96@proof.invalid",
        full_name="Proof Coordinator",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id=harness.FACILITY_ID,
    )


async def _escalate(session_factory, ctx, shipment_id: str, *, reason: str, severity: str = "HIGH"):
    async with session_factory() as session:
        return await escalate_exception(
            session,
            ctx,
            EscalateExceptionCommand(
                shipment_id=shipment_id,
                # LOW_CONFIDENCE_ETA rather than NO_FEASIBLE_SLOT so nothing here can be confused
                # with the escalations the determinism and scenario parts assert on.
                escalation_type="LOW_CONFIDENCE_ETA",
                payload={"reason": reason},
                severity_code=severity,
            ),
        )


async def _row(session_factory, escalation_id: str) -> dict:
    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT * FROM public.escalation_queue WHERE escalation_id = :eid"),
                {"eid": escalation_id},
            )
        ).mappings().first()
    assert row is not None, f"{escalation_id} vanished from escalation_queue"
    return dict(row)


async def _fixture_shipment(work_sessionmaker, *, tag: str) -> Contender:
    """One private driver/user/shipment for an escalation test. No slots, deliberately.

    *Why not a seeded shipment.* `resolve_escalation` also sweeps `driver_exceptions` for the same
    shipment, so pointing these tests at SHP1006 would silently mutate the rows the four tests
    above assert on.

    *Why not `harness.seed_race`.* It also inserts an OPEN `appointment_slots` row on
    `DOCK-JAI-D1`, and every other 2099 fixture in this suite runs `find_feasible_slots` over a
    rolling horizon on that same dock -- three spare open slots would silently change the option
    counts parts 1, 5 and 6 record as evidence. These tests never book anything, so the slot is
    pure contamination. The driver/user/shipment triple below is the subset that is actually
    needed: `escalate_exception` reads `shipments`, and `acknowledge_escalation` writes
    `owner_user_id`, which carries an FK to `public.users`.
    """
    suffix = f"{tag}{uuid4().hex[:8].upper()}"
    contender = Contender(
        index=0,
        user_id=f"USR-96-{suffix}",
        driver_id=f"DRV-96-{suffix}",
        shipment_id=f"SHP-96-{suffix}",
    )
    # The ETA sits in 2099 for the same reason harness.py's does: nothing here can ever collide
    # with the shipped seed's 2026-08-04 fixtures, which parts 2, 4 and 5 assert on to the row.
    eta = harness.CONTESTED_START
    async with work_sessionmaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO public.drivers (
                  driver_id, carrier_id, driver_name, phone, licence_number,
                  home_base_city, driver_status
                ) VALUES (
                  :driver_id, :carrier_id, :name, :phone, :licence, 'Jaipur', 'ACTIVE'
                )
                """
            ),
            {
                "driver_id": contender.driver_id,
                "carrier_id": harness.CARRIER_ID,
                "name": f"Proof 96 {suffix}",
                "phone": f"+91-96{suffix}",
                "licence": f"LIC-96-{suffix}",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO public.users (
                  user_id, role_id, employee_code, full_name, email, phone_number,
                  password_hash, driver_id, facility_id, is_active
                ) VALUES (
                  :user_id, :role_id, :employee_code, :full_name, :email, NULL,
                  'proof-suite-no-login', :driver_id, :facility_id, 1
                )
                """
            ),
            {
                "user_id": contender.user_id,
                "role_id": harness.DRIVER_ROLE_ID,
                "employee_code": f"EMP-96-{suffix}",
                "full_name": f"Proof 96 {suffix}",
                "email": f"{contender.driver_id.lower()}@proof.invalid",
                "driver_id": contender.driver_id,
                "facility_id": harness.FACILITY_ID,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO public.shipments (
                  shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                  origin_name, origin_city, destination_facility_id, customer_name,
                  product_category, load_weight_kg, pallet_count, required_dock_type,
                  temperature_control_required, priority_code, planned_departure_ts,
                  actual_departure_ts, original_eta_ts, latest_eta_ts,
                  expected_unload_min, current_status, created_at, updated_at
                ) VALUES (
                  :shipment_id, :order_reference, :carrier_id, :driver_id, :vehicle_id,
                  'Proof Origin', 'Jaipur', :facility_id, 'Proof Customer',
                  'GENERAL', :load_weight_kg, 10, 'STANDARD',
                  0, 'NORMAL', :departure, :departure, :eta, :eta,
                  :unload_min, 'IN_TRANSIT', :created_at, :created_at
                )
                """
            ),
            {
                "shipment_id": contender.shipment_id,
                "order_reference": f"ORD-96-{suffix}",
                "carrier_id": harness.CARRIER_ID,
                "driver_id": contender.driver_id,
                "vehicle_id": harness.VEHICLE_ID,
                "facility_id": harness.FACILITY_ID,
                "load_weight_kg": harness.LOAD_WEIGHT_KG,
                "departure": eta - timedelta(hours=6),
                "eta": eta,
                "unload_min": harness.EXPECTED_UNLOAD_MIN,
                "created_at": eta - timedelta(hours=6),
            },
        )
        await session.commit()
    return contender


async def test_escalating_again_after_a_resolve_opens_a_new_case(work_sessionmaker):
    """RESOLVED is terminal: the next same-day, same-type escalation is a NEW OPEN row.

    The old row must come through completely untouched -- not merely "still RESOLVED", but every
    column byte-for-byte what it was, `dedupe_key` and `resolved_at` included. Compared as whole
    rows rather than field by field so a future change that quietly rewrites, say, `updated_at` or
    `payload_json` on the closed case fails here instead of being discovered in production.
    """
    contender = await _fixture_shipment(work_sessionmaker, tag="R")
    ctx = _ops_ctx(user_id=contender.user_id, request_id="proof-96-resolve")

    first = await _escalate(work_sessionmaker, ctx, contender.shipment_id, reason="first problem")
    assert first["escalation_status"] == "OPEN"

    async with work_sessionmaker() as session:
        resolved = await resolve_escalation(
            session, ctx, first["escalation_id"], resolution_note="Handled at the gate",
            reason_code="ISSUE_FIXED",
        )
    assert resolved["code"] == "RESOLVED"
    closed_before = await _row(work_sessionmaker, first["escalation_id"])
    assert closed_before["escalation_status"] == "RESOLVED"
    assert closed_before["resolved_at"] is not None

    second = await _escalate(
        work_sessionmaker, ctx, contender.shipment_id, reason="a genuinely different problem"
    )

    assert second["dedupe_key"] == first["dedupe_key"], (
        "the two escalations did not even share a dedupe key, so this test proved nothing -- "
        "the UTC calendar day rolled over mid-test (escalate_exception reads the wall clock)"
    )
    assert second["escalation_id"] != first["escalation_id"], (
        "issue #96: the resolved case was handed back instead of a new one being opened.\n"
        f"  returned {second['escalation_id']} with status {second['escalation_status']!r}"
    )
    assert second["escalation_status"] == "OPEN"
    assert second["payload"]["reason"] == "a genuinely different problem"

    assert await _row(work_sessionmaker, first["escalation_id"]) == closed_before, (
        "the resolved escalation was modified by a later escalate_exception call"
    )
    record_evidence(
        "3. issue #96: escalate after RESOLVE",
        f"{first['escalation_id']} stays RESOLVED, new {second['escalation_id']} OPEN, "
        f"shared dedupe_key {second['dedupe_key']}",
    )


async def test_escalating_again_after_a_cancel_opens_a_new_case(work_sessionmaker):
    """CANCELLED is the *other* terminal state (FR-OPS-006), and is asserted separately.

    Not folded into the test above with a parametrize: `cancel_escalation` is a different code
    path with a different reason-code vocabulary and a mandatory Idempotency-Key, and #96's whole
    cause was one status being handled and another not.
    """
    contender = await _fixture_shipment(work_sessionmaker, tag="C")
    ctx = _ops_ctx(user_id=contender.user_id, request_id="proof-96-cancel")

    first = await _escalate(work_sessionmaker, ctx, contender.shipment_id, reason="raised in error")
    async with work_sessionmaker() as session:
        cancelled = await cancel_escalation(
            session, ctx, first["escalation_id"], reason_code="CREATED_IN_ERROR",
            idempotency_key=f"proof-96-cancel-{uuid4().hex[:10]}",
        )
    assert cancelled["code"] == "CANCELLED"
    closed_before = await _row(work_sessionmaker, first["escalation_id"])
    assert closed_before["escalation_status"] == "CANCELLED"

    second = await _escalate(work_sessionmaker, ctx, contender.shipment_id, reason="real this time")

    assert second["dedupe_key"] == first["dedupe_key"], "UTC day rolled over mid-test"
    assert second["escalation_id"] != first["escalation_id"], (
        "issue #96: the cancelled case was handed back instead of a new one being opened"
    )
    assert second["escalation_status"] == "OPEN"
    assert await _row(work_sessionmaker, first["escalation_id"]) == closed_before, (
        "the cancelled escalation was modified by a later escalate_exception call"
    )
    record_evidence(
        "3. issue #96: escalate after CANCEL",
        f"{first['escalation_id']} stays CANCELLED, new {second['escalation_id']} OPEN",
    )


async def test_a_non_terminal_escalation_is_still_refreshed_in_place(work_sessionmaker):
    """The half of the behaviour that must NOT change, asserted as hard as the half that did.

    While the prior case is live, a repeat escalation still collapses onto it: same row, refreshed
    payload/severity, and exactly one non-terminal row per dedupe key -- enforced by the partial
    unique index, not by application logic. The `ACKNOWLEDGED` leg is the guard against the
    rejected option (a) sneaking back in: an owned, mid-lifecycle case must be refreshed, never
    reset to `OPEN`, or a coordinator would silently lose a claim they had already made.
    """
    contender = await _fixture_shipment(work_sessionmaker, tag="L")
    ctx = _ops_ctx(user_id=contender.user_id, request_id="proof-96-live")

    first = await _escalate(
        work_sessionmaker, ctx, contender.shipment_id, reason="first report", severity="HIGH"
    )
    second = await _escalate(
        work_sessionmaker, ctx, contender.shipment_id, reason="more detail", severity="MEDIUM"
    )

    assert second["escalation_id"] == first["escalation_id"], (
        "a live escalation was duplicated instead of refreshed -- the partial index predicate no "
        "longer matches the ON CONFLICT arbiter"
    )
    assert second["escalation_status"] == "OPEN"
    assert second["payload"]["reason"] == "more detail"
    assert second["severity_code"] == "MEDIUM"

    async with work_sessionmaker() as session:
        acknowledged = await acknowledge_escalation(
            session, ctx, first["escalation_id"], idempotency_key=f"proof-96-ack-{uuid4().hex[:10]}"
        )
    assert acknowledged["code"] == "ACKNOWLEDGED"

    third = await _escalate(
        work_sessionmaker, ctx, contender.shipment_id, reason="third report", severity="LOW"
    )
    assert third["escalation_id"] == first["escalation_id"]
    assert third["escalation_status"] == "ACKNOWLEDGED", (
        "an acknowledged escalation was reset to OPEN -- that is option (a), which was rejected"
    )
    assert third["payload"]["reason"] == "third report"

    async with work_sessionmaker() as session:
        live = int(
            await session.scalar(
                text(
                    """
                    SELECT count(*) FROM public.escalation_queue
                    WHERE dedupe_key = :key AND escalation_status NOT IN ('RESOLVED', 'CANCELLED')
                    """
                ),
                {"key": first["dedupe_key"]},
            )
        )
    assert live == 1, f"{live} non-terminal escalations share one dedupe key; the index allows one"
    record_evidence(
        "3. issue #96: repeat escalation while live",
        f"3 calls -> 1 row {first['escalation_id']}, status ACKNOWLEDGED preserved, "
        f"{live} non-terminal row(s) per key",
    )


async def test_the_partial_index_that_makes_all_of_the_above_true_actually_exists(seed_session):
    """A behavioural pass proves nothing if the index it rests on was never created.

    Read from `pg_index`/`pg_get_expr` on the *pristine* seed database -- so this asserts what
    migration 20260901120000 produces on a clean replay, not what the tests above happened to
    leave behind. Two facts, and both matter: the partial index is present with the exact terminal
    predicate, and the old global `UNIQUE (dedupe_key)` is gone. If the second were still there,
    every assertion above would pass for the wrong reason (PostgreSQL would infer the full index
    and dedupe globally again).
    """
    row = (
        await seed_session.execute(
            text(
                """
                SELECT ic.relname AS index_name,
                       i.indisunique,
                       pg_get_expr(i.indpred, i.indrelid) AS predicate
                FROM pg_index i
                JOIN pg_class ic ON ic.oid = i.indexrelid
                WHERE i.indrelid = 'public.escalation_queue'::regclass
                  AND ic.relname = 'escalation_queue_dedupe_key_active_uidx'
                """
            )
        )
    ).mappings().first()
    assert row is not None, (
        "escalation_queue_dedupe_key_active_uidx is missing -- migration 20260901120000 did not "
        "replay, and every ON CONFLICT (dedupe_key) in backend/app would raise 42P10"
    )
    assert row["indisunique"] is True, "the index exists but is not UNIQUE, so it enforces nothing"
    predicate = str(row["predicate"])
    for status in TERMINAL_STATUSES:
        assert status in predicate, f"{status} is not in the index predicate: {predicate}"
    assert "OPEN" not in predicate and "ACKNOWLEDGED" not in predicate, (
        f"the predicate names a non-terminal status, which inverts the rule: {predicate}"
    )

    leftovers = (
        await seed_session.execute(
            text(
                """
                SELECT ic.relname AS index_name
                FROM pg_index i
                JOIN pg_class ic ON ic.oid = i.indexrelid
                WHERE i.indrelid = 'public.escalation_queue'::regclass
                  AND i.indisunique
                  AND i.indpred IS NULL
                  AND i.indnkeyatts = 1
                  AND i.indkey[0] = (
                    SELECT a.attnum FROM pg_attribute a
                    WHERE a.attrelid = 'public.escalation_queue'::regclass
                      AND a.attname = 'dedupe_key' AND NOT a.attisdropped
                  )
                """
            )
        )
    ).mappings().all()
    assert leftovers == [], (
        "a GLOBAL unique index on dedupe_key survived the migration "
        f"({[r['index_name'] for r in leftovers]}) -- terminal rows are still conflict candidates"
    )
    record_evidence("3. issue #96: index predicate", f"{row['index_name']} WHERE {predicate}")


async def test_no_bare_on_conflict_dedupe_key_is_left_anywhere_in_the_backend():
    """Static guard: every arbiter on `dedupe_key` must repeat the index predicate.

    Not a style rule. PostgreSQL's `index_predicate` is what "allows inference of partial unique
    indexes" (postgresql.org/docs/current/sql-insert.html, ON CONFLICT Clause, checked 2026-09-01
    against the PostgreSQL 18 the proof cluster runs); a bare `ON CONFLICT (dedupe_key)` no longer
    matches any index on this table and raises 42P10 at runtime. Two of the three writers
    (`planner_service._open_capacity_cascade`, `expiry.py`'s PENDING_EXPIRED_UNACTIONED insert) are
    not on the escalate path at all, so nothing else in this suite would have caught them -- and
    the expiry one fires from a scheduled sweep where a 42P10 is a silent, total outage of M8's
    escalate leg.

    Scoped to arbiters whose INSERT actually targets `escalation_queue`, resolved per site rather
    than assumed. `driver_exceptions` also has a `dedupe_key` but has never been unique-indexed
    (20260807184700's own header note) and nothing upserts on it; `notification_outbox`
    (20260902093000, issue #94) does upsert on one, and does so with a deliberately BARE arbiter
    because its unique index is not partial -- repeating escalation_queue's predicate there would
    match no index at all and cause the very 42P10 this guard exists to prevent. The narrowing is
    therefore a correction, not a relaxation: every escalation_queue site is still checked.
    """
    offenders: list[str] = []
    sites = 0
    skipped_other_tables: list[str] = []
    for path in sorted(ESCALATION_SOURCE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        start = 0
        while (found := source.find("ON CONFLICT (dedupe_key)", start)) != -1:
            start = found + 1
            line = source.count("\n", 0, found) + 1
            # The nearest preceding `INSERT INTO public.<table>` is the statement this arbiter
            # belongs to. Nearest-preceding is sound here because every one of these is a single
            # `text("""...""")` literal, so no other INSERT can sit between the two.
            inserts = list(_INSERT_TARGET.finditer(source, 0, found))
            target = inserts[-1].group(1) if inserts else None
            if target != "escalation_queue":
                skipped_other_tables.append(
                    f"{path.relative_to(ESCALATION_SOURCE_ROOT)}:{line} -> {target}"
                )
                continue
            sites += 1
            if not source.startswith(ARBITER_PREDICATE, found):
                offenders.append(f"{path.relative_to(ESCALATION_SOURCE_ROOT)}:{line}")
    assert sites > 0, "the scan found no escalation_queue dedupe_key arbiter -- it has stopped working"
    assert offenders == [], (
        "these ON CONFLICT (dedupe_key) arbiters do not carry the partial index's predicate and "
        f"will raise 42P10 at runtime: {offenders}\n  expected: {ARBITER_PREDICATE}"
    )
    record_evidence("3. issue #96: arbiter sites carrying the predicate", f"{sites}/{sites}")
    if skipped_other_tables:
        # Reported, never silent: a site that lands here because someone renamed the INSERT (rather
        # than because it genuinely targets another table) would otherwise stop being checked
        # without anyone noticing.
        record_evidence(
            "3. issue #96: dedupe_key arbiters on other tables (not checked)",
            "; ".join(skipped_other_tables),
        )


# ---------------------------------------------------------------------------------------------
# The named skip this file used to carry, retired 2026-09-02 (issue #94)
# ---------------------------------------------------------------------------------------------
#
# `test_notification_outbox_receives_exactly_one_row_per_dedupe_key` sat here as one of this
# suite's three named skips, with the reason *"that table has never been created: no `CREATE TABLE
# notification_outbox` exists anywhere in supabase/migrations/ (verified by grep 2026-09-01)"*.
# `20260902093000_notification_outbox.sql` creates it, so the reason is no longer true and a skip
# carrying a false reason is worse than no skip at all.
#
# The assertion it stood in for now exists for real, against the same replayed cluster, in
# `tests/proof/test_part3b_notification_outbox.py` --
# `test_a_replayed_producer_yields_exactly_one_outbox_row_per_dedupe_key` (three committed producer
# runs, one surviving row, one feed entry). It lives in its own module rather than here because it
# needs a different fixture set (a routable recipient, a drain cycle) and because the two halves of
# section 10.3's "one notification" now genuinely measure different tables: this file's
# `operational_messages` count and that file's `notification_outbox` count, which issue #94's
# reconciliation makes two distinct facts rather than one duplicated.
#
# The `operational_messages` assertion above is deliberately left exactly as it was.
