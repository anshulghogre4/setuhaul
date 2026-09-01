"""Section 10 part 3b -- the notification outbox, against a real cluster (issue #94).

Design citation: `SOLUTION_DESIGN.md` section 6.1 (`notification_outbox` -- "Transactional outbox
so a booking and its notification cannot diverge; feeds `operational_messages`"), section 3's
module 10, section 7.2's "outbound event -> notification outbox -> channel adapter", section 7.4
(`NOTIFICATION_UNROUTABLE`), section 7.5.8 (`get_notifications` / `mark_notifications_read`);
`TECH-STACK/TECH_STACK.md` section 6; `ARCHITECTURE/REQUIREMENTS.md` FR-SYS-008, FR-SYS-020,
FR-X-023, NFR-009 / M9 / section 10.3's *"exactly one ... notification"*.

## Why this module exists, and what it retires

`test_part3_idempotency_replay.py` carries a **named skip**,
`test_notification_outbox_receives_exactly_one_row_per_dedupe_key`, whose stated reason is that
*"no `CREATE TABLE notification_outbox` exists anywhere in supabase/migrations/"*. That is now
false: `supabase/migrations/20260902093000_notification_outbox.sql` creates it, and this module
asserts the half of section 10.3's claim that skip could not.

Its sibling's assertion counts `operational_messages`, the table that existed. That assertion stays
exactly as it is and is **not** duplicated here -- the two tables answer different questions under
issue #94's reconciliation (`operational_messages` is the EMAIL channel's delivery record;
`notification_outbox` is the event itself), and collapsing them would put the disconnection back.

## What is asserted here rather than in `tests/unit/test_notification_outbox.py`

Everything that is about what **PostgreSQL** refuses or guarantees, because a mocked session cannot
refuse anything (the CHANGELOG's 2026-09-01 lesson: the unit suite sat green through four
production-breaking M5 defects). Specifically: the unique index really suppressing a replay, both
table CHECK constraints really rejecting a malformed row, the drain's claim/deliver/mark cycle over
real rows, and the RLS lockdown this migration also applies to E3.5's two previously-unprotected
tables.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.execution_context import ExecutionContext, RoleName
from app.services import notification_outbox as outbox
from app.services import notification_service
from tests.proof.evidence import record_evidence

pytestmark = pytest.mark.asyncio(loop_scope="session")

PROOF_USER_ID = "USR-PROOF-OUTBOX"
PROOF_EMAIL = "proof.outbox@proof.invalid"


def _ctx(user_id: str) -> ExecutionContext:
    """A driver context for the feed reads. `get_notifications` scopes on `ctx.user_id` alone
    (section 7.5.8: "This user's notification feed"), so this is the only field that matters."""
    return ExecutionContext(
        request_id="proof-outbox", auth_subject="proof-outbox", user_id=user_id,
        email=PROOF_EMAIL, full_name="Proof Outbox", role_id="ROL001",
        role_name=RoleName.DRIVER, facility_id="FAC-JAI-01",
    )


async def _routable_appointment(session) -> dict[str, str]:
    """A real seeded appointment whose driver this module then gives a login account to.

    Discovered by query rather than hardcoded: appointment ids are Layer-A seed data and stable,
    but a test that names one silently stops testing anything if the generator ever rebases them
    (section 9.1's Layer A/B/C separation makes that a live possibility). `ORDER BY` keeps it
    deterministic, which section 9.1's determinism rule requires of every proof assertion.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, s.driver_id
                FROM public.appointments a
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                WHERE s.driver_id IS NOT NULL
                ORDER BY a.appointment_id
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    assert row is not None, "the seed has no appointment with a driver -- fixture assumption broken"
    return dict(row)


async def _ensure_proof_user(session, driver_id: str) -> str:
    """Give that driver a `public.users` row so recipient resolution can succeed.

    Not inventing operational data (the same judgement `test_part3_idempotency_replay.py`'s own
    `_ensure_replay_user` records): the driver, shipment and appointment are all real seed rows;
    this adds only the identity the notification is addressed to. Most seeded drivers have no login
    account, which is precisely why the UNROUTABLE test below has fixtures available to it.
    """
    await session.execute(
        text(
            """
            INSERT INTO public.users (
              user_id, role_id, employee_code, full_name, email, phone_number,
              password_hash, driver_id, facility_id, is_active
            ) VALUES (
              :user_id, 'ROL001', 'EMP-PROOF-OUTBOX', 'Proof Outbox', :email, NULL,
              'proof-suite-no-login', :driver_id, 'FAC-JAI-01', 1
            )
            ON CONFLICT (user_id) DO NOTHING
            """
        ),
        {"user_id": PROOF_USER_ID, "email": PROOF_EMAIL, "driver_id": driver_id},
    )
    await session.commit()
    # Which user the resolver actually picks is its own decision (`ORDER BY u.user_id LIMIT 1`
    # among active users for that driver). Read it back rather than assume it is ours -- a seeded
    # account for the same driver would legitimately win, and the assertions below must follow the
    # real recipient, not a guess.
    return await session.scalar(
        text(
            "SELECT u.user_id FROM public.users u WHERE u.driver_id = :d AND u.is_active = 1 "
            "ORDER BY u.user_id LIMIT 1"
        ),
        {"d": driver_id},
    )


# ---------------------------------------------------------------------------------------------
# 1. The table exists at all -- the literal thing issue #94 says was never migrated
# ---------------------------------------------------------------------------------------------


async def test_notification_outbox_exists_with_its_uniqueness_and_check_constraints(work_session):
    """Issue #94's headline finding, replayed. The proof suite builds its cluster by replaying
    `supabase/migrations/` in filename order, so this passing means the migration is genuinely in
    the chain -- not merely present as a file."""
    exists = await work_session.scalar(
        text("SELECT to_regclass('public.notification_outbox')")
    )
    assert exists is not None, "20260902093000_notification_outbox.sql did not create the table"

    unique_index = await work_session.scalar(
        text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
            "AND indexname = 'notification_outbox_dedupe_key_uidx'"
        )
    )
    assert unique_index is not None and "UNIQUE" in unique_index, (
        "dedupe_key is not uniquely indexed -- NFR-009's 'exactly 1 notification' has no enforcer"
    )

    checks = set(
        (
            await work_session.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'public.notification_outbox'::regclass AND contype = 'c' "
                    "AND conname LIKE 'notification_outbox_%'"
                )
            )
        ).scalars().all()
    )
    # Six, and the split is worth naming: four are PostgreSQL's auto-named column CHECKs (the
    # enumerations), two are the named two-column invariants the migration adds in its DO block
    # because `ADD CONSTRAINT IF NOT EXISTS` does not exist
    # (supabase-postgres-best-practices/schema-constraints).
    assert checks == {
        "notification_outbox_event_type_check",
        "notification_outbox_category_check",
        "notification_outbox_status_check",
        "notification_outbox_attempts_check",
        "notification_outbox_recipient_required",
        "notification_outbox_delivered_shape",
    }, checks
    record_evidence("3b. notification_outbox table + constraints", f"{len(checks)} CHECKs present")


# ---------------------------------------------------------------------------------------------
# 2. Enqueue -> drain -> visible -> marked: the whole path issue #94 says does not connect
# ---------------------------------------------------------------------------------------------


async def test_enqueue_then_drain_puts_exactly_one_notification_in_the_users_feed(
    work_sessionmaker,
):
    """The end-to-end reconciliation: a business event enqueues an outbox row (authoritative), the
    drain delivers it into `public.notifications` (the IN_APP delivery record and read model), and
    `GET /api/v1/notifications`' own service function returns it.

    Before this, `notification_service` read a table nothing wrote to and the outbox did not exist.
    """
    async with work_sessionmaker() as session:
        appointment = await _routable_appointment(session)
        recipient = await _ensure_proof_user(session, appointment["driver_id"])

    # --- produce, inside a transaction the caller commits, exactly as a real producer would ---
    async with work_sessionmaker() as session:
        outbox_id = await outbox.enqueue_notification(
            session,
            event_type=outbox.APPOINTMENT_CONFIRMED,
            appointment_id=appointment["appointment_id"],
        )
        assert outbox_id is not None, "enqueue wrote nothing"
        await session.commit()

    async with work_sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, recipient_user_id, category, title, body, shipment_id, "
                    "notification_id, delivered_at FROM public.notification_outbox "
                    "WHERE outbox_id = :id"
                ),
                {"id": outbox_id},
            )
        ).mappings().first()
        assert row["status"] == "PENDING", "a fresh outbox row must not be delivered yet"
        assert row["recipient_user_id"] == recipient
        assert row["category"] == "APPOINTMENT"
        assert row["shipment_id"] == appointment["shipment_id"]
        assert row["notification_id"] is None and row["delivered_at"] is None

    # --- the feed is still empty for this user: delivery is a separate, retryable step ---
    async with work_sessionmaker() as session:
        before = await notification_service.get_notifications(session, _ctx(recipient))
        assert before["items"] == [], (
            "the feed had rows before the drain ran -- something is writing public.notifications "
            "outside the outbox, which is exactly the disconnection issue #94 is about"
        )

    # --- consume ---
    async with work_sessionmaker() as session:
        result = await outbox.drain_outbox(session)
        assert result.delivered >= 1, result.model_dump()

    async with work_sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, notification_id, delivered_at, attempts "
                    "FROM public.notification_outbox WHERE outbox_id = :id"
                ),
                {"id": outbox_id},
            )
        ).mappings().first()
        assert row["status"] == "DELIVERED"
        assert row["delivered_at"] is not None
        assert row["attempts"] == 1
        notification_id = row["notification_id"]
        assert notification_id == notification_service.in_app_notification_id(outbox_id)

    # --- visible on the surface the shell bell reads ---
    async with work_sessionmaker() as session:
        feed = await notification_service.get_notifications(session, _ctx(recipient))
        ids = [item["notification_id"] for item in feed["items"]]
        assert notification_id in ids, feed
        item = next(i for i in feed["items"] if i["notification_id"] == notification_id)
        assert item["is_read"] == 0
        assert item["related_entity_type"] == "appointments"
        assert item["related_entity_id"] == appointment["appointment_id"]
        assert "Confirmed - Dock" in item["body"] and "Reference" in item["body"]

    # --- marked ---
    async with work_sessionmaker() as session:
        marked = await notification_service.mark_notifications_read(
            session, _ctx(recipient), [notification_id]
        )
        assert marked["marked_count"] == 1 and marked["code"] == "READ"

    async with work_sessionmaker() as session:
        unread = await notification_service.get_notifications(
            session, _ctx(recipient), unread_only=True
        )
        assert notification_id not in [i["notification_id"] for i in unread["items"]]
        # Section 7.5.8: "idempotent; marking an already-read notification read again is a no-op,
        # not an error."
        again = await notification_service.mark_notifications_read(
            session, _ctx(recipient), [notification_id]
        )
        assert again["marked_count"] == 0 and again["code"] == "READ"

    record_evidence(
        "3b. enqueue -> drain -> feed -> marked",
        f"outbox {outbox_id} -> notification {notification_id}, 1 delivered, 1 marked",
    )


async def test_a_second_drain_delivers_nothing_because_status_is_the_guard(work_sessionmaker):
    """`drain_outbox` needs no idempotency key: the `status = 'PENDING'` predicate is the guard, the
    same shape `expiry._expire_one_pending` uses. An EventBridge retry of a completed cycle must be
    a no-op, not a second notification in the driver's feed."""
    async with work_sessionmaker() as session:
        result = await outbox.drain_outbox(session)
        assert result.claimed == 0 and result.delivered == 0, result.model_dump()


# ---------------------------------------------------------------------------------------------
# 3. NFR-009 / M9 / section 10.3 -- "exactly one notification", enforced by the database
# ---------------------------------------------------------------------------------------------


async def test_a_replayed_producer_yields_exactly_one_outbox_row_per_dedupe_key(work_sessionmaker):
    """This is the assertion `test_part3_idempotency_replay.py`'s named skip could not make.

    Section 10.3 / section 9.2's `duplicate_retry` row / M9: *"same `dedupe_key` -> Exactly 1
    exception, 1 hold attempt, 1 notification."* The guarantee is
    `notification_outbox_dedupe_key_uidx`'s, not the application's -- so the enqueue is deliberately
    called **three** times, in three separate committed transactions, the way a genuinely retried
    producer would run.
    """
    async with work_sessionmaker() as session:
        appointment = await _routable_appointment(session)
        recipient = await _ensure_proof_user(session, appointment["driver_id"])

    dedupe_key = outbox.build_dedupe_key(
        outbox.PENDING_EXPIRED, appointment["appointment_id"], recipient
    )

    outcomes = []
    for _ in range(3):
        async with work_sessionmaker() as session:
            outcomes.append(
                await outbox.enqueue_notification(
                    session,
                    event_type=outbox.PENDING_EXPIRED,
                    appointment_id=appointment["appointment_id"],
                )
            )
            await session.commit()

    # Since #94's producers were wired into the real write paths (P1-P10, 2026-09-02), an
    # earlier proof test expiring this same appointment may have ALREADY enqueued this event --
    # making the test's own first call a replay. The guarantee under test is the database's
    # ("exactly 1 row per dedupe_key"), not which caller got there first, so assert that:
    # at most one of the three explicit calls inserted, and the count below is exactly 1.
    inserted = [o for o in outcomes if o is not None]
    assert len(inserted) <= 1, f"replays were treated as new events: {outcomes}"

    async with work_sessionmaker() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM public.notification_outbox WHERE dedupe_key = :k"),
            {"k": dedupe_key},
        )
    assert count == 1, f"three producer runs left {count} outbox rows for one event"

    # And the guarantee survives the drain: one outbox row can only ever become one feed row.
    async with work_sessionmaker() as session:
        await outbox.drain_outbox(session)
    async with work_sessionmaker() as session:
        feed_count = await session.scalar(
            text(
                "SELECT count(*) FROM public.notifications n "
                "JOIN public.notification_outbox o ON o.notification_id = n.notification_id "
                "WHERE o.dedupe_key = :k"
            ),
            {"k": dedupe_key},
        )
    assert feed_count == 1, f"one event produced {feed_count} notifications"
    record_evidence("3b. NFR-009 replay: outbox rows per dedupe_key", f"{count} (3 producer runs)")


# ---------------------------------------------------------------------------------------------
# 4. Section 7.4 -- NOTIFICATION_UNROUTABLE, detected at recipient resolution
# ---------------------------------------------------------------------------------------------


async def test_an_unresolvable_recipient_becomes_an_unroutable_row_and_never_reaches_a_feed(
    work_sessionmaker,
):
    """Section 7.4: *"this fails **before** any send is attempted, so retrying is pointless ...
    Detect it when the outbox resolves recipients, not when a send fails."*

    Two things are proved: the row is written (so the failure is visible and countable rather than
    an exception that vanished into a log), and the drain never claims it (so it does not burn
    retries on something that cannot succeed).
    """
    async with work_sessionmaker() as session:
        orphan = (
            await session.execute(
                text(
                    """
                    SELECT a.appointment_id, a.shipment_id
                    FROM public.appointments a
                    JOIN public.shipments s ON s.shipment_id = a.shipment_id
                    WHERE s.driver_id IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM public.users u
                        WHERE u.driver_id = s.driver_id AND u.is_active = 1
                      )
                    ORDER BY a.appointment_id
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()
    assert orphan is not None, (
        "every seeded driver now has a login account -- this fixture assumption no longer holds"
    )

    async with work_sessionmaker() as session:
        outbox_id = await outbox.enqueue_notification(
            session,
            event_type=outbox.HOLD_LAPSED,
            appointment_id=orphan["appointment_id"],
        )
        await session.commit()
    assert outbox_id is not None, "an unroutable event was dropped instead of being recorded"

    async with work_sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, recipient_user_id, last_error FROM public.notification_outbox "
                    "WHERE outbox_id = :id"
                ),
                {"id": outbox_id},
            )
        ).mappings().first()
    assert row["status"] == "UNROUTABLE"
    assert row["recipient_user_id"] is None
    assert "NOTIFICATION_UNROUTABLE" in row["last_error"]

    async with work_sessionmaker() as session:
        result = await outbox.drain_outbox(session)
    assert result.claimed == 0, "the drain claimed an UNROUTABLE row it can never deliver"
    record_evidence("3b. section 7.4 NOTIFICATION_UNROUTABLE", "recorded, not raised; drain skips")


# ---------------------------------------------------------------------------------------------
# 5. What PostgreSQL actually refuses -- the half a mocked session cannot test
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "columns", "values", "params"),
    [
        (
            "an event_type outside the designed catalog",
            "status, recipient_user_id",
            "'PENDING', :recipient",
            {"event_type": "NOT_A_DESIGNED_EVENT"},
        ),
        (
            "a PENDING row with no recipient (notification_outbox_recipient_required)",
            "status, recipient_user_id",
            "'PENDING', NULL",
            {"event_type": "APPOINTMENT_CONFIRMED"},
        ),
        (
            "DELIVERED with no delivered_at (notification_outbox_delivered_shape)",
            "status, recipient_user_id",
            "'DELIVERED', :recipient",
            {"event_type": "APPOINTMENT_CONFIRMED"},
        ),
    ],
)
async def test_the_database_refuses_a_malformed_outbox_row(
    work_sessionmaker, label, columns, values, params
):
    """Written as raw SQL on purpose. `enqueue_notification` deliberately never raises, so a
    constraint it violates would surface only as a logged line -- these assert the constraints
    themselves, which are what stops a future producer (or a hand-run fix-up) writing a row the
    drain can never act on."""
    async with work_sessionmaker() as session:
        recipient = await session.scalar(
            text("SELECT user_id FROM public.users ORDER BY user_id LIMIT 1")
        )
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    f"""
                    INSERT INTO public.notification_outbox (
                      outbox_id, dedupe_key, event_type, category, title, body, {columns}
                    ) VALUES (
                      :outbox_id, :dedupe_key, :event_type, 'APPOINTMENT', 't', 'b', {values}
                    )
                    """
                ),
                {
                    "outbox_id": f"NOB-REFUSE-{abs(hash(label)) % 10**8}",
                    "dedupe_key": f"REFUSE:{label}",
                    "recipient": recipient,
                    **params,
                },
            )
        await session.rollback()


# ---------------------------------------------------------------------------------------------
# 6. The security defect this migration also fixes
# ---------------------------------------------------------------------------------------------


async def test_all_three_notification_tables_are_locked_down(work_session):
    """E3.5's `notifications` and `notification_preferences` shipped with **no RLS and no revoke**,
    unlike every table in the baseline (20260805201923:614-641). Supabase's "Securing your API"
    guide (fetched 2026-09-02): *"tables created in `public` receive SELECT, INSERT, UPDATE, and
    DELETE privileges for `anon`, `authenticated`, and `service_role` by default ... These grants
    make new objects reachable through the Data API, even when you don't intend to expose them."*

    Concretely, before this migration: any signed-in user could read any other user's notification
    feed through PostgREST, because `get_notifications`' `user_id = ctx.user_id` predicate only ever
    protected the FastAPI path.
    """
    tables = ("notification_outbox", "notifications", "notification_preferences")
    rls = dict(
        (
            await work_session.execute(
                text(
                    "SELECT relname, relrowsecurity FROM pg_class "
                    "WHERE relnamespace = 'public'::regnamespace AND relname = ANY(:names)"
                ),
                {"names": list(tables)},
            )
        ).all()
    )
    assert all(rls.get(name) is True for name in tables), rls

    leaked = (
        await work_session.execute(
            text(
                "SELECT table_name, grantee, privilege_type "
                "FROM information_schema.role_table_grants "
                "WHERE table_schema = 'public' AND table_name = ANY(:names) "
                "AND grantee IN ('anon', 'authenticated')"
            ),
            {"names": list(tables)},
        )
    ).all()
    assert leaked == [], f"anon/authenticated still hold grants: {leaked}"
    record_evidence("3b. RLS lockdown (outbox + E3.5's two)", "3/3 enabled, 0 anon/auth grants")
