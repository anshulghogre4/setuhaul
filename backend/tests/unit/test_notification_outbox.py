"""Issue #94 -- `notification_outbox`, the section 6.1 transactional outbox.

Design citation: `SOLUTION_DESIGN.md` section 6.1, section 3's module 10, section 7.2's "outbound
event -> notification outbox -> channel adapter", section 7.4 (`NOTIFICATION_UNROUTABLE`), section
7.5.8; `TECH-STACK/TECH_STACK.md` section 6; `ARCHITECTURE/REQUIREMENTS.md` NFR-009 / M9.

These are the mocked-session tests -- catalog integrity, key construction, template rendering, and
the two behaviours that must hold **regardless of the database**: an enqueue never raises, and an
unresolvable recipient becomes an UNROUTABLE row rather than an exception.

The behaviours that are genuinely about what PostgreSQL refuses -- the unique index actually
suppressing a replay, the drain's `FOR UPDATE SKIP LOCKED` claim, the end-to-end
enqueue -> drain -> visible -> marked path -- are in
`backend/tests/proof/test_part3b_notification_outbox.py`, against a real cluster. That split is
deliberate and is the lesson the CHANGELOG records for 2026-09-01: the unit suite sat green through
four production-breaking defects during M5 because a mocked session cannot refuse anything.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def _nested_cm() -> MagicMock:
    """A begin_nested() stand-in: async context manager that no-ops (2026-09-02 -- the
    savepoint wrap added after suite 3 proved bare never-raises poisons the outer txn)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


import pytest

from app.services import notification_outbox as outbox
from app.services import notification_service

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20260902093000_notification_outbox.sql"
)

IST = timezone.utc  # replaced per-test; slot fixtures below are timezone-aware UTC


# ---------------------------------------------------------------------------------------------
# Catalog integrity -- the Python enum and the database CHECK must not drift
# ---------------------------------------------------------------------------------------------


def test_the_migration_check_constraint_lists_exactly_the_python_event_catalog():
    """The one test that catches the whole class of "added an event, forgot the migration".

    A producer emitting an event the CHECK does not permit fails at the INSERT -- and because
    `enqueue_notification` deliberately never raises, that failure would be a logged line and a
    silently missing notification, not an error anyone sees. Parsing the migration is cheap
    insurance against exactly that.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    block = re.search(r"event_type\s+text NOT NULL CHECK \(event_type IN \((.*?)\)\)", sql, re.S)
    assert block is not None, "the event_type CHECK constraint could not be found in the migration"
    in_sql = set(re.findall(r"'([A-Z_]+)'", block.group(1)))
    assert in_sql == set(outbox.EVENT_CATALOG), (
        f"catalog drift: only in SQL={in_sql - set(outbox.EVENT_CATALOG)}, "
        f"only in Python={set(outbox.EVENT_CATALOG) - in_sql}"
    )


def test_every_catalog_category_is_one_the_notifications_table_accepts():
    """The drain copies `category` straight across into `public.notifications`, whose own CHECK
    admits exactly three values. A fourth here would fail at delivery, not at enqueue -- i.e. after
    the business transaction already committed, which is the worst place to find it."""
    assert {spec.category for spec in outbox.EVENT_CATALOG.values()} <= (
        notification_service.NOTIFICATION_CATEGORIES
    )


def test_the_four_high_priority_driver_events_are_all_in_the_catalog():
    """`01-driver-chat/flows-and-states.md`:282-292 names four events as high priority -- the
    capacity-loss / decision-against cases "where a driver who never opens the app still needs to
    know, because they may be driving toward a dock that is no longer theirs"."""
    for event in (
        outbox.PENDING_EXPIRED,
        outbox.APPOINTMENT_REJECTED,
        outbox.OPTION_WITHDRAWN,
        outbox.HOLD_LAPSED,
    ):
        assert event in outbox.EVENT_CATALOG


# ---------------------------------------------------------------------------------------------
# Dedupe keys -- NFR-009's guarantee depends entirely on how these are built
# ---------------------------------------------------------------------------------------------


def test_dedupe_key_identifies_the_event_instance_not_a_calendar_day():
    """Issue #96's recorded lesson, applied in the opposite direction. A day-bucketed key on this
    table would suppress a genuinely new second event and the suppression would look like success
    (`ON CONFLICT DO NOTHING` returns no error)."""
    key = outbox.build_dedupe_key(outbox.APPOINTMENT_CONFIRMED, "APT1014A", "USR-DRV-6")
    assert key == "APPOINTMENT_CONFIRMED:APT1014A:USR-DRV-6"
    assert not re.search(r"\d{4}-?\d{2}-?\d{2}", key), "a date component crept into the dedupe key"


def test_two_different_events_on_one_entity_do_not_collide():
    entity = "APT1014A"
    assert outbox.build_dedupe_key(outbox.APPOINTMENT_CONFIRMED, entity, "U1") != (
        outbox.build_dedupe_key(outbox.APPOINTMENT_CANCELLED, entity, "U1")
    )


def test_one_event_to_two_recipients_is_two_notifications_not_a_duplicate():
    """A dock outage cascade tells every affected driver about the same event. Those are different
    notifications; collapsing them would silently drop all but one driver's warning."""
    assert outbox.build_dedupe_key(outbox.OPTION_WITHDRAWN, "DEVT001", "U1") != (
        outbox.build_dedupe_key(outbox.OPTION_WITHDRAWN, "DEVT001", "U2")
    )


def test_an_unroutable_recipient_still_produces_a_distinct_key_per_entity():
    """Otherwise every unroutable event would collide into one row and section 7.4's
    `NOTIFICATION_UNROUTABLE` would be uncountable -- the failure would hide itself."""
    a = outbox.build_dedupe_key(outbox.PENDING_EXPIRED, "APT1", None)
    b = outbox.build_dedupe_key(outbox.PENDING_EXPIRED, "APT2", None)
    assert a != b and a.endswith(":NONE")


# ---------------------------------------------------------------------------------------------
# Templates -- voice-and-tone.md:8, "sentences that declare operational state are templated"
# ---------------------------------------------------------------------------------------------


def _slot_params() -> dict[str, str]:
    return {
        "dock": "D1", "date": "Tue 4 Aug", "window": "13:00-14:15", "facility": "Jaipur DC",
        "reference": "APT-1042", "reason": "CAPACITY", "actor": "Neha",
    }


@pytest.mark.parametrize("event_type", sorted(outbox.EVENT_CATALOG))
def test_every_catalog_template_renders_from_the_standard_parameter_set(event_type: str):
    """`render_event` is strict on purpose: a half-rendered body ("Dock {dock} has just gone out of
    service") reaching a driver is worse than a producer that fails in development. This asserts the
    standard set this module resolves is genuinely sufficient for every template."""
    title, body = outbox.render_event(event_type, _slot_params())
    assert title and body
    assert "{" not in body and "}" not in body


def test_pending_expired_body_matches_the_push_preview_the_driver_surface_already_ships():
    """`frontend/src/features/driver/screens/push-priming.tsx`:66 renders this exact sentence as the
    notification preview, and `flows-and-states.md`:300 requires push copy and in-app copy to be the
    same template -- *"a notification that says something different from what the app says is a
    second source of truth"*. This is the assertion that keeps the two from drifting."""
    _, body = outbox.render_event(outbox.PENDING_EXPIRED, _slot_params())
    assert body.startswith(
        "No planner responded in time, so Dock D1 - Tue 4 Aug - 13:00-14:15 has been released."
    )


def test_confirmed_is_the_only_template_permitted_to_say_confirmed():
    """voice-and-tone.md's section 4 heading is literally *"CONFIRMED -- the only sentence that may
    say 'confirmed'"*. A rejection or a counter-offer body containing the word would undo the one
    piece of vocabulary discipline the driver surface relies on."""
    for event_type, spec in outbox.EVENT_CATALOG.items():
        says_confirmed = "confirm" in spec.body.lower()
        assert says_confirmed == (event_type == outbox.APPOINTMENT_CONFIRMED), event_type


@pytest.mark.parametrize(
    "event_type",
    [
        outbox.APPOINTMENT_CONFIRMED, outbox.APPOINTMENT_REJECTED, outbox.APPOINTMENT_CANCELLED,
        outbox.PENDING_EXPIRED, outbox.HOLD_LAPSED, outbox.OPTION_WITHDRAWN, outbox.COUNTER_OFFER,
    ],
)
def test_every_appointment_bearing_body_carries_its_date(event_type: str):
    """`frontend/src/components/shell/notifications-panel.tsx`:13 -- *"Every operational time
    carries its dock AND its date. A bare '13:00' is a wrong-day booking waiting to happen: option
    sets span days."* voice-and-tone.md's templates omit the date because they render inside a
    same-day thread; a bell notification read hours later has no such context."""
    assert "{date}" in outbox.EVENT_CATALOG[event_type].body


def test_format_slot_fields_renders_facility_local_time_not_utc():
    """The slot columns are `timestamptz` since 20260823060000:40-41, so a UTC instant has to be
    converted, not printed. 07:30Z is 13:00 IST -- if this ever asserts 07:30, every driver-facing
    time in the product is five and a half hours wrong."""
    start = datetime(2026, 8, 4, 7, 30, tzinfo=timezone.utc)
    end = datetime(2026, 8, 4, 8, 45, tzinfo=timezone.utc)
    fields = outbox.format_slot_fields(start, end, "Asia/Kolkata")
    assert fields["window"] == "13:00-14:15"
    assert fields["date"] == "Tue 4 Aug"


def test_format_slot_fields_degrades_rather_than_crashing_on_a_missing_slot_time():
    assert outbox.format_slot_fields(None, None, "Asia/Kolkata") == {
        "date": "date unknown", "window": "time unknown"
    }


# ---------------------------------------------------------------------------------------------
# enqueue_notification -- the two properties that hold regardless of the database
# ---------------------------------------------------------------------------------------------


def _enqueue_session(*, appointment_row=None, recipient="USR-DRV-6", inserted="NOB-ABC"):
    """A session that answers the three reads `enqueue_notification` can make, in order:
    the appointment context (`execute`), the recipient (`scalar`), then the INSERT (`scalar`)."""
    execute_result = MagicMock()
    execute_result.mappings.return_value.first.return_value = appointment_row
    session = AsyncMock()
    session.begin_nested = MagicMock(side_effect=lambda: _nested_cm())
    session.execute = AsyncMock(return_value=execute_result)
    session.scalar = AsyncMock(side_effect=[recipient, inserted])
    session.commit = AsyncMock()
    return session


APPOINTMENT_ROW = {
    "appointment_id": "APT1014A", "shipment_id": "SHP1014", "cancellation_reason": None,
    "slot_start_ts": datetime(2026, 8, 4, 7, 30, tzinfo=timezone.utc),
    "slot_end_ts": datetime(2026, 8, 4, 8, 45, tzinfo=timezone.utc),
    "dock_code": "D1", "facility_id": "FAC-JAI-01", "facility_name": "Jaipur DC",
    "timezone": "Asia/Kolkata",
}


@pytest.mark.asyncio
async def test_enqueue_never_commits():
    """The whole of section 6.1's guarantee. A commit here would make the notification survive a
    rollback of the booking that produced it -- "a booking and its notification cannot diverge"
    read backwards."""
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW)
    await outbox.enqueue_notification(
        session, event_type=outbox.APPOINTMENT_CONFIRMED, appointment_id="APT1014A"
    )
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_resolves_dock_date_window_and_facility_from_the_appointment_alone():
    """Why a producer call site is one line: the notification concern stays in this module rather
    than five lines of joins inside `allocation.py`'s transaction."""
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW)
    await outbox.enqueue_notification(
        session, event_type=outbox.APPOINTMENT_CONFIRMED, appointment_id="APT1014A"
    )
    params = session.scalar.await_args_list[-1].args[1]
    assert params["body"] == (
        "Confirmed - Dock D1 - Tue 4 Aug - 13:00-14:15, Jaipur DC. Reference APT1014A."
    )
    assert params["shipment_id"] == "SHP1014"
    assert params["status"] == outbox.STATUS_PENDING


@pytest.mark.asyncio
async def test_an_unresolvable_recipient_becomes_an_unroutable_row_not_an_exception():
    """Section 7.4: `NOTIFICATION_UNROUTABLE` *"fails **before** any send is attempted, so retrying
    is pointless ... Detect it when the outbox resolves recipients, not when a send fails."* And the
    harder half: a driver with no `users` row must not be able to fail the booking."""
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW, recipient=None)
    result = await outbox.enqueue_notification(
        session, event_type=outbox.PENDING_EXPIRED, appointment_id="APT1014A"
    )
    assert result == "NOB-ABC"
    params = session.scalar.await_args_list[-1].args[1]
    assert params["status"] == outbox.STATUS_UNROUTABLE
    assert params["recipient_user_id"] is None
    assert "NOTIFICATION_UNROUTABLE" in params["last_error"]


@pytest.mark.asyncio
async def test_a_database_failure_inside_enqueue_is_swallowed_and_logged_not_raised():
    """The property that makes this safe to patch into `allocation.py`'s hot path at all. If this
    ever raises, a notification bug becomes a booking outage."""
    session = AsyncMock()
    session.begin_nested = MagicMock(side_effect=lambda: _nested_cm())
    session.execute = AsyncMock(side_effect=RuntimeError("connection reset"))
    assert (
        await outbox.enqueue_notification(
            session, event_type=outbox.APPOINTMENT_CONFIRMED, appointment_id="APT1014A"
        )
        is None
    )


@pytest.mark.asyncio
async def test_an_unknown_event_type_enqueues_nothing_rather_than_writing_a_row_the_check_refuses():
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW)
    assert (
        await outbox.enqueue_notification(
            session, event_type="NOT_AN_EVENT", appointment_id="APT1014A"
        )
        is None
    )
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_replayed_producer_returns_none_because_the_unique_index_suppressed_the_insert():
    """`ON CONFLICT (dedupe_key) DO NOTHING` returns no row. This is M9 / NFR-009 answering, and the
    guarantee is the index's, not this module's -- see the proof suite for the real-cluster half."""
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW, inserted=None)
    assert (
        await outbox.enqueue_notification(
            session, event_type=outbox.APPOINTMENT_CONFIRMED, appointment_id="APT1014A"
        )
        is None
    )


# ---------------------------------------------------------------------------------------------
# The IN_APP channel adapter
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_status", "expected"),
    [
        ("REJECTED", outbox.APPOINTMENT_REJECTED),
        ("EXPIRED", outbox.PENDING_EXPIRED),
        ("CANCELLED", outbox.APPOINTMENT_CANCELLED),
    ],
)
async def test_enqueue_for_transition_maps_each_status_to_its_designed_event(
    target_status, expected
):
    """`allocation._ops_pending_transition` is one function serving reject and expire. The mapping
    lives here so its producer call site stays one line and no notification vocabulary leaks into
    the allocation module."""
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW)
    await outbox.enqueue_for_transition(
        session, target_status=target_status, appointment_id="APT1014A", reason="CAPACITY"
    )
    assert session.scalar.await_args_list[-1].args[1]["event_type"] == expected


@pytest.mark.asyncio
async def test_enqueue_for_transition_is_a_no_op_for_a_status_with_no_designed_event():
    """Inventing a notification for an unmapped status would put unreviewed copy in front of a
    driver -- worse than saying nothing."""
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW)
    assert (
        await outbox.enqueue_for_transition(
            session, target_status="COMPLETED", appointment_id="APT1014A"
        )
        is None
    )
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_option_withdrawn_fans_out_one_notification_per_affected_appointment():
    """Section 5.1: a cascade is ONE escalation but N notifications -- each affected driver is a
    different person who has to be told about their own slot. `build_dedupe_key`'s recipient
    component is what stops those N collapsing into one."""
    session = _enqueue_session(appointment_row=APPOINTMENT_ROW)
    session.scalar = AsyncMock(side_effect=["USR-A", "NOB-1", "USR-B", "NOB-2"])
    assert (
        await outbox.enqueue_option_withdrawn(
            session, appointment_ids=["APT1", "APT2"], dock_code="D5"
        )
        == 2
    )
    keys = [
        call.args[1]["dedupe_key"]
        for call in session.scalar.await_args_list
        if isinstance(call.args[1], dict) and "dedupe_key" in call.args[1]
    ]
    assert len(set(keys)) == 2, keys


def test_the_in_app_notification_id_is_derived_from_its_outbox_row():
    """A second, index-backed defence against a duplicate feed entry, independent of the drain's
    row lock."""
    assert notification_service.in_app_notification_id("NOB-1A2B3C") == "NTF-1A2B3C"


@pytest.mark.asyncio
async def test_the_in_app_adapter_writes_the_feed_row_and_does_not_commit():
    """The drain owns the transaction: the `notifications` insert and the outbox row's transition to
    DELIVERED commit together, so the feed can never hold a notification the outbox thinks is still
    pending."""
    session = AsyncMock()
    session.begin_nested = MagicMock(side_effect=lambda: _nested_cm())
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    row = {
        "outbox_id": "NOB-1A2B3C", "recipient_user_id": "USR-DRV-6", "category": "APPOINTMENT",
        "title": "Slot confirmed", "body": "Confirmed - Dock D1.",
        "related_entity_type": "appointments", "related_entity_id": "APT1014A",
    }
    assert await notification_service.deliver_in_app_notification(session, row) == "NTF-1A2B3C"
    session.commit.assert_not_awaited()
    params = session.execute.await_args.args[1]
    assert params["user_id"] == "USR-DRV-6"
    assert params["notification_id"] == "NTF-1A2B3C"


def test_the_in_app_adapter_is_the_only_registered_channel_and_the_others_are_named_gaps():
    """Section 3's module 10 keeps "a pluggable channel adapter". v1 registers IN_APP only: there is
    no SES client and no VAPID key pair in this codebase, and section 6.1 specifies no
    push-subscription table -- so EMAIL and WEB_PUSH are absent by decision, not half-built."""
    assert list(outbox.CHANNEL_ADAPTERS) == ["IN_APP"]
    assert outbox.CHANNEL_ADAPTERS["IN_APP"]() is notification_service.deliver_in_app_notification
