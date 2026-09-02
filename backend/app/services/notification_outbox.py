"""Module 10's transactional outbox -- the producer half (issue #94).

Design citation: `SOLUTION_DESIGN.md` section 6.1 (`notification_outbox` -- "Transactional outbox
so a booking and its notification cannot diverge; feeds `operational_messages`"), section 3's
module 10, section 7.2's "outbound event -> notification outbox -> channel adapter" path, section
7.4 (`NOTIFICATION_FAILED` / `NOTIFICATION_UNROUTABLE`), section 7.5.8 (`get_notifications` is "a
read extension of the outbox it already tracks delivery through"), and
`TECH-STACK/TECH_STACK.md` section 6 ("The outbox row is written **in the same transaction** as the
business change; delivery is a separate, retryable step").
Requirements: `ARCHITECTURE/REQUIREMENTS.md` FR-SYS-008, FR-SYS-020, FR-OPS-002, FR-OPS-006,
FR-X-023, NFR-009 (M9's "1 notification").

## The three artifacts, and which one is authoritative

Issue #94's real question. Three notification artifacts existed and none connected:

* `notification_outbox` -- designed in section 6.1, never migrated until
  `supabase/migrations/20260902093000_notification_outbox.sql`. **Authoritative.** The only
  notification artifact ever written inside a business transaction.
* `notifications` / `notification_preferences` -- built by E3.5
  (`20260825211500_e35_notifications_and_search.sql`), read by `notification_service.py` through
  `GET /api/v1/notifications`, with **zero writers** anywhere. Now the **IN_APP channel's delivery
  record and read model**, written only by this module's drain.
* `operational_messages` -- built in the baseline, 5 Layer-A seed rows, **zero readers or writers**
  in `backend/app/`. Now the **EMAIL channel's** delivery record per TECH_STACK section 6
  ("Delivery status lands in `operational_messages`"). **Its adapter is not implemented in v1** --
  there is no SES client anywhere in this codebase -- so `CHANNEL_ADAPTERS` registers IN_APP only
  and the seam is named rather than faked.

Full reasoning, including why `dedupe_key` is globally unique here when issue #96 just removed
exactly that from `escalation_queue`, is in the migration's header.

## The two halves, and why they are not one function

`enqueue_notification` runs **inside the caller's transaction and never commits**. That is the
whole of section 6.1's guarantee: if the booking rolls back, so does its notification, with no
compensating logic anywhere. `drain_outbox` runs **after**, in its own transactions, and is
therefore allowed to fail, retry, and be slow without ever touching a business write.

Collapsing them -- delivering inline at enqueue time -- would put a `notifications` INSERT inside
the same transaction as a `dock_occupancy` claim, lengthening the hold on the row that D1's
exclusion constraint serialises every concurrent booker against. That is the exact opposite of
what E4.4's session-hold work did, and it would trade a correctness property for nothing.

## What is deliberately NOT an outbox event

The outbox is for section 7.2's **"new system-initiated message class"** -- *"events the driver
must be told about without having sent a message ... A purely request/response assistant cannot
satisfy that line in the brief."* So:

* **An ETA acknowledgement is not an outbox event.** `record_eta_update` answers a message the
  driver just sent; its reply is the tool's own return value on the same turn. Routing it through
  a 1-minute drain would make a synchronous answer arrive late and twice.
* **"Hold about to lapse (10s)" is not an outbox event** either
  (`01-driver-chat/flows-and-states.md`:280 lists it as in-app-only, no push). It is a client-side
  countdown over the `expires_at` the server already sent -- see `frontend/.../flags.ts` on the
  90-second countdown reading `dock_occupancy.expires_at`. A server event for it would race the
  countdown it duplicates.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ids import new_id

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------------
# Event catalog
# ------------------------------------------------------------------------------------------
# Every value here is also a value in the migration's `event_type` CHECK constraint, and the two
# lists must stay identical -- `test_notification_outbox.py` asserts that by parsing the migration,
# so a value added to one and forgotten in the other fails a test rather than a production write.

APPOINTMENT_CONFIRMED = "APPOINTMENT_CONFIRMED"
APPOINTMENT_REJECTED = "APPOINTMENT_REJECTED"
APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
# Issue #49. Added by `20260902160000_scheduling_runs.sql`, which extends the CHECK constraint.
# See EVENT_CATALOG below for why none of the other eleven could carry this fact.
APPOINTMENT_RESEQUENCED = "APPOINTMENT_RESEQUENCED"
PENDING_EXPIRED = "PENDING_EXPIRED"
HOLD_LAPSED = "HOLD_LAPSED"
OPTION_WITHDRAWN = "OPTION_WITHDRAWN"
COUNTER_OFFER = "COUNTER_OFFER"
THREAD_TAKEN_OVER = "THREAD_TAKEN_OVER"
ESCALATION_OPENED = "ESCALATION_OPENED"
ESCALATION_RESOLVED = "ESCALATION_RESOLVED"
ESCALATION_CANCELLED = "ESCALATION_CANCELLED"

CATEGORY_APPOINTMENT = "APPOINTMENT"
CATEGORY_ESCALATION = "ESCALATION"
CATEGORY_SYSTEM = "SYSTEM"

STATUS_PENDING = "PENDING"
STATUS_DELIVERED = "DELIVERED"
STATUS_UNROUTABLE = "UNROUTABLE"
STATUS_FAILED = "FAILED"

# After this many drain attempts a row is FAILED rather than retried forever. Five cycles of the
# 1-minute EventBridge cadence (TECH_STACK section 6: "Same mechanism as section 5's sweeper"), so
# roughly five minutes of transient-fault tolerance. No exponential backoff and no `available_at`
# column: a backoff schedule is machinery for a queue under load, and this one carries single
# figures of rows per hour against a 5-concurrent-user product.
MAX_DELIVERY_ATTEMPTS = 5

# The drain's per-cycle bound. Same reasoning as `EXPIRY_SWEEP_BATCH_LIMIT`: an EventBridge API
# destination times an invocation out at 5 seconds, so an unbounded sweep would be killed mid-way
# on a backlog. Each row commits on its own, so a timeout loses no completed work.
DEFAULT_DRAIN_BATCH_LIMIT = 100


@dataclass(frozen=True)
class EventSpec:
    """One design-enumerated outbound event: its category, its templates, what it points at.

    `title` and `body` are `str.format` templates, not prose to be generated.
    `UI-UX/00-foundations/voice-and-tone.md`:8 -- *"Sentences that declare operational state are
    templated. The assistant writes the glue around them."* -- and:300, *"Push copy uses the same
    templates as in-app ... a notification that says something different from what the app says is
    a second source of truth."* The LLM never writes any of this.
    """

    category: str
    title: str
    body: str
    entity_type: str
    #: `True` when voice-and-tone.md carries this exact wording; `False` marks the ones composed
    #: here in the same register because the doc's eight negative-path templates do not cover them.
    #: `Source: assumption, untested` -- the same honesty convention E3.5's migration used for the
    #: three `category` values section 7.5.8 never named.
    sourced: bool = True


# `{dock}`, `{date}`, `{window}`, `{facility}` are resolved by `_appointment_context` from the real
# appointment -> slot -> dock -> facility chain. **`{date}` is mandatory in every appointment-bearing
# body**, and that is not a style choice: `frontend/src/components/shell/notifications-panel.tsx`:13
# states the rule -- *"Every operational time carries its dock AND its date. A bare '13:00' is a
# wrong-day booking waiting to happen: option sets span days."* voice-and-tone.md's negative-path
# templates omit the date because they render inside a same-day chat thread; a bell notification
# read three hours later has no such context, so the date is added here. That divergence is
# deliberate and is the one place these templates are not byte-identical to the doc's.
EVENT_CATALOG: dict[str, EventSpec] = {
    APPOINTMENT_CONFIRMED: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Slot confirmed",
        # voice-and-tone.md section "4 - CONFIRMED", the only sentence permitted to say "confirmed".
        body="Confirmed - Dock {dock} - {date} - {window}, {facility}. Reference {reference}.",
        entity_type="appointments",
    ),
    APPOINTMENT_REJECTED: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Slot request rejected",
        # No REJECTED template exists among voice-and-tone.md's eight negative-path templates --
        # a real gap in the doc, recorded rather than papered over. Composed in the same register:
        # names the cause (section 7.5.1 makes `reason_code` an enum *because* it is rendered to
        # the driver) and gives the next action, per that section's U32 rule.
        body=(
            "The warehouse could not take Dock {dock} - {date} - {window} ({reason}). "
            "I can look for fresh options now."
        ),
        entity_type="appointments",
        sourced=False,
    ),
    APPOINTMENT_CANCELLED: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Appointment cancelled",
        body=(
            "Dock {dock} - {date} - {window} at {facility} has been cancelled ({reason}). "
            "I can look for fresh options now."
        ),
        entity_type="appointments",
        sourced=False,
    ),
    PENDING_EXPIRED: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Slot released - no planner response",
        # voice-and-tone.md:115-121 `PENDING_EXPIRED`, verbatim but for the added date. The same
        # sentence is already the notification preview in
        # `frontend/src/features/driver/screens/push-priming.tsx`:66, which is exactly the
        # single-source-of-truth property flows-and-states.md:300 asks for.
        body=(
            "No planner responded in time, so Dock {dock} - {date} - {window} has been released. "
            "This has been escalated to operations, and I can look for fresh options now."
        ),
        entity_type="appointments",
    ),
    HOLD_LAPSED: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Hold lapsed",
        # voice-and-tone.md:107-113 `HOLD_LAPSED`, plus the date.
        body=(
            "That hold has lapsed - Dock {dock} - {date} - {window} is available to other drivers "
            "again. Nothing has been lost; I can look again right now."
        ),
        entity_type="dock_occupancy",
    ),
    OPTION_WITHDRAWN: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Option withdrawn - dock out of service",
        # voice-and-tone.md:130-135 `OPTION_WITHDRAWN`, plus the date. FR-SYS-020's "dock down".
        body=(
            "Dock {dock} has just gone out of service, so the {date} - {window} option is no "
            "longer available."
        ),
        entity_type="appointments",
    ),
    APPOINTMENT_RESEQUENCED: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Your dock slot has moved",
        # SOLUTION_DESIGN.md section 5.1's cascade path ends "planner applies -> notifications batch
        # out", and its own diff example annotates a moved row "(communicated -- driver will be
        # notified)". No existing catalog value can carry that fact honestly, which is why this is a
        # twelfth rather than a borrowed eleventh (the migration's step 9 states all three reasons):
        # APPOINTMENT_CONFIRMED's dedupe key is already spent by the original confirmation, so the
        # move would be silently suppressed; COUNTER_OFFER says "nothing is held yet", which is
        # false once the apply has re-claimed the interval; OPTION_WITHDRAWN asserts a dock outage,
        # which is one possible cause and not the fact being reported.
        #
        # Composed in voice-and-tone.md's register rather than quoted from it -- the doc's eight
        # negative-path templates do not cover a re-sequence -- so `sourced=False`. It follows that
        # file's two governing rules for this class of message: it declares the new operational
        # state rather than apologising for the old one, and it carries the dock AND the date
        # (notifications-panel.tsx:13 -- "a bare '13:00' is a wrong-day booking waiting to happen").
        body=(
            "The facility has re-sequenced your slot. You are now on Dock {dock} - {date} - "
            "{window} at {facility}."
        ),
        entity_type="appointments",
        sourced=False,
    ),
    COUNTER_OFFER: EventSpec(
        category=CATEGORY_APPOINTMENT,
        title="Counter-offer from the warehouse",
        body=(
            "The warehouse has offered Dock {dock} - {date} - {window} instead. "
            "Nothing is held yet - review it to accept or decline."
        ),
        entity_type="appointments",
        sourced=False,
    ),
    THREAD_TAKEN_OVER: EventSpec(
        category=CATEGORY_ESCALATION,
        title="Someone from Operations has joined",
        # voice-and-tone.md:169-174 `HUMAN_JOINED` (U47). FR-OPS-002: "driver told on both
        # transitions". The doc's own rendering is a divider rather than a bubble; the bell
        # notification carries the same words in sentence form.
        body="{actor} from Operations has joined your conversation.",
        entity_type="chat_threads",
        sourced=False,
    ),
    ESCALATION_OPENED: EventSpec(
        category=CATEGORY_ESCALATION,
        title="Passed to operations",
        # voice-and-tone.md:155-161 `NO_FEASIBLE_SLOT` -> escalation: *"I've passed this to
        # operations. Reference ESC-4471. Someone will contact you directly."* -- and the doc's own
        # rule underneath it: "Always carry a reference and a promise of contact. An escalation
        # without a reference feels like being dropped."
        body=(
            "I've passed this to operations. Reference {reference}. "
            "Someone will contact you directly."
        ),
        entity_type="escalation_queue",
    ),
    ESCALATION_RESOLVED: EventSpec(
        category=CATEGORY_ESCALATION,
        title="Escalation resolved",
        # FR-OPS-006: "two terminal states, two driver consequences, each requiring a reason code".
        # The two consequences are why RESOLVED and CANCELLED are separate events and not one
        # "escalation closed" with a status field -- the driver is told different things.
        body="Operations has resolved {reference} ({reason}).",
        entity_type="escalation_queue",
        sourced=False,
    ),
    ESCALATION_CANCELLED: EventSpec(
        category=CATEGORY_ESCALATION,
        title="Escalation cancelled",
        body="Operations has cancelled {reference} ({reason}). No further action is planned.",
        entity_type="escalation_queue",
        sourced=False,
    ),
}


#: `appointments.appointment_status` -> the event a driver is told about when it is reached.
#:
#: Lives here rather than in `allocation.py` on purpose. `_ops_pending_transition` is one function
#: serving both `reject_request` (section 7.5.1: "REJECTED + released interval + driver
#: notification", FR-PLN-003) and `expire_request`, so without this map its producer call site
#: would need a conditional -- notification vocabulary leaking into the allocation module, which is
#: the boundary `AGENTS.md`'s "business rules belong in services" rule exists to keep.
#:
#: `EXPIRED` maps to `PENDING_EXPIRED` because both routes to that status mean the same thing to
#: the driver -- nobody actioned the request in time -- and voice-and-tone.md has exactly one
#: template for it. `CONFIRMED` is deliberately absent: it is produced by `_apply_confirmation`,
#: which is a different seam shared with `bulk_confirm`.
EVENT_FOR_TRANSITION: dict[str, str] = {
    "REJECTED": APPOINTMENT_REJECTED,
    "EXPIRED": PENDING_EXPIRED,
    "CANCELLED": APPOINTMENT_CANCELLED,
}


# ------------------------------------------------------------------------------------------
# Dedupe keys
# ------------------------------------------------------------------------------------------


def build_dedupe_key(
    event_type: str,
    entity_id: str,
    recipient_user_id: str | None,
    dedupe_scope: str | None = None,
) -> str:
    """The exactly-once key. **EVENT INSTANCE, never a calendar day.**

    NFR-009 / M9 / section 10.3 -- *"duplicate `dedupe_key` -> 1 exception, 1 booking attempt,
    1 notification"* -- is delivered by the unique index over this value, not by any check in
    Python. That only holds if the key identifies the event: issue #96 is the recorded case of a
    day-bucketed key silently swallowing a genuinely new event, and the whole reason this is a
    single named constructor rather than an f-string at each call site.

    The recipient is part of the key because one event legitimately notifies more than one person
    (a cascade tells every affected driver about the same dock outage) and those are different
    notifications, not duplicates of one. `NONE` for an unroutable recipient keeps the row unique
    and countable instead of colliding every unroutable event for the same entity into one.

    `dedupe_scope` (added for issue #49) names the **occurrence** when the same event can genuinely
    happen to the same entity more than once. The sequencer is the case that needs it: two applied
    proposals can both move one appointment, and those are two real notifications, not a replay --
    without a scope the second would be silently suppressed by
    `notification_outbox_dedupe_key_uidx`, which is the day-bucket failure mode issue #96 recorded,
    reached from a different direction. It defaults to `None` and appends nothing when absent, so
    every existing producer's key is **byte-identical** to what it was before this parameter
    existed (`test_notification_outbox.py` pins that, parametrised over the catalog).
    """
    scope = f"@{dedupe_scope}" if dedupe_scope else ""
    return f"{event_type}:{entity_id}{scope}:{recipient_user_id or 'NONE'}"


def render_event(event_type: str, params: dict[str, Any]) -> tuple[str, str]:
    """Templated title/body for an event. Raises `KeyError` on an unknown event or missing field.

    Deliberately strict. A silently half-rendered notification ("Dock {dock} has just gone out of
    service") is worse than a producer that fails loudly at development time, and every template's
    fields are resolved by this module from real rows rather than passed in by a caller.
    """
    spec = EVENT_CATALOG[event_type]
    return spec.title, spec.body.format(**params)


# ------------------------------------------------------------------------------------------
# Context resolution -- everything a template needs, from one id
# ------------------------------------------------------------------------------------------
#
# These reads exist so a producer call site is ONE line. A patch into `allocation.py` that had to
# assemble dock code, local date, window, facility name and recipient itself would be five lines of
# notification concern inside the allocation transaction, which is how a module boundary rots.


async def _appointment_context(session: AsyncSession, appointment_id: str) -> dict[str, Any] | None:
    """appointment -> slot -> dock -> facility, in one round trip.

    `slot_start_ts`/`slot_end_ts` have been `timestamptz` since
    `20260823060000_d1_correctness_bedrock.sql`:40-41, so these come back as aware `datetime`s and
    the local rendering below is a real conversion rather than string surgery on a `+05:30` suffix.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.cancellation_reason,
                       sl.slot_start_ts, sl.slot_end_ts,
                       d.dock_code,
                       f.facility_id, f.facility_name, f.timezone
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.docks d ON d.dock_id = sl.dock_id
                JOIN public.facilities f ON f.facility_id = sl.facility_id
                WHERE a.appointment_id = :appointment_id
                """
            ),
            {"appointment_id": appointment_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def _driver_user_for_shipment(session: AsyncSession, shipment_id: str) -> str | None:
    """The `public.users` row belonging to this shipment's driver, or None.

    None is a legitimate answer, not an error: section 7.4's `NOTIFICATION_UNROUTABLE` is precisely
    "the recipient record cannot be resolved", and its instruction is to *"detect it when the outbox
    resolves recipients, not when a send fails"*. The caller turns None into an UNROUTABLE row; it
    must never turn it into an exception, because that exception would roll back the booking.

    `is_active = 1` is part of the predicate: a deactivated user's account cannot receive anything,
    so resolving to it would produce a DELIVERED row nobody can ever read.
    """
    return await session.scalar(
        text(
            """
            SELECT u.user_id
            FROM public.shipments s
            JOIN public.users u ON u.driver_id = s.driver_id
            WHERE s.shipment_id = :shipment_id AND u.is_active = 1
            ORDER BY u.user_id
            LIMIT 1
            """
        ),
        {"shipment_id": shipment_id},
    )


def _local(moment: datetime, tz_name: str | None) -> datetime:
    """Facility-local rendering. Falls back to IST, which is what every seeded facility is.

    `facilities.timezone` defaults to `Asia/Kolkata` (baseline:30) and voice-and-tone.md's own note
    on time rendering says the zone label never appears while that stays true -- so this is a
    conversion for correctness at 6 facilities, not a display feature.
    """
    try:
        return moment.astimezone(ZoneInfo(tz_name or "Asia/Kolkata"))
    except Exception:  # pragma: no cover - an unknown tz name in data, not a code path
        return moment.astimezone(ZoneInfo("Asia/Kolkata"))


def format_slot_fields(
    start: datetime | None, end: datetime | None, tz_name: str | None
) -> dict[str, str]:
    """`{date}` and `{window}` as the templates expect them.

    `Tue 4 Aug` and `13:00-14:15` -- the exact shapes voice-and-tone.md's own examples use
    ("Dock D1 - Tue 4 Aug - 13:00-14:15"). Not ISO: these are read by a driver on a phone.
    """
    if start is None or end is None:
        return {"date": "date unknown", "window": "time unknown"}
    local_start = _local(start, tz_name)
    local_end = _local(end, tz_name)
    return {
        # %-d is not portable to Windows; lstrip('0') is the portable "no leading zero" form.
        "date": f"{local_start:%a} {local_start:%d}".replace(" 0", " ") + f" {local_start:%b}",
        "window": f"{local_start:%H:%M}-{local_end:%H:%M}",
    }


# ------------------------------------------------------------------------------------------
# The producer -- runs INSIDE the caller's transaction
# ------------------------------------------------------------------------------------------


async def enqueue_notification(
    session: AsyncSession,
    *,
    event_type: str,
    appointment_id: str | None = None,
    shipment_id: str | None = None,
    escalation_id: str | None = None,
    recipient_user_id: str | None = None,
    reason: str | None = None,
    actor: str | None = None,
    dock_code: str | None = None,
    extra: dict[str, Any] | None = None,
    dedupe_scope: str | None = None,
) -> str | None:
    """Write one outbox row in the caller's transaction. **Never commits, never raises.**

    This is the whole of section 6.1's guarantee and both halves of that sentence matter:

    * **Never commits** -- the row lives or dies with the business write it accompanies. A caller
      that rolls back has no orphan notification and needs no compensating delete.
    * **Never raises** -- a notification is not worth failing a booking for. Every failure path
      below either writes an UNROUTABLE row (recipient could not be resolved: section 7.4's own
      instruction) or logs and returns None (template/context failure). The one thing this must not
      do is turn a successful dock claim into a 500 because a facility name was null.

      The exception handler is deliberately broad for that reason. It is NOT a swallow-and-forget:
      it logs at `exception` level with the event type and entity, so the failure is in the same
      place every other backend fault is.

    Returns the new `outbox_id`, or None when the event was already enqueued (a replay -- this is
    NFR-009's "1 notification" answering) or could not be built at all.

    **M15**: `recipient_user_id`, when passed, must be a server-derived id -- an
    `ExecutionContext.user_id` or a value this module resolved. It is never a client-supplied
    argument on any tool in section 7.5, and no endpoint in `app/api/` accepts one.
    """
    try:
        spec = EVENT_CATALOG.get(event_type)
        if spec is None:
            logger.error("notification outbox: unknown event_type %r; nothing enqueued", event_type)
            return None

        params: dict[str, Any] = {
            "reason": reason or "no reason given",
            "actor": actor or "Someone",
            "dock": dock_code or "-",
            "facility": "the facility",
            "reference": escalation_id or appointment_id or shipment_id or "-",
            "date": "date unknown",
            "window": "time unknown",
        }
        params.update(extra or {})

        resolved_shipment = shipment_id
        entity_id = escalation_id or appointment_id or shipment_id

        # Escalation-only events (resolve/cancel/take-over producers pass escalation_id and a
        # reason, nothing else) must resolve their shipment from the escalation row, or the
        # recipient lookup below has nothing to walk and the row lands UNROUTABLE. Found on
        # production 2026-09-02: six ESCALATION_RESOLVED/CANCELLED rows with shipment_id NULL,
        # every one for a shipment whose driver DOES have an active users row.
        if escalation_id is not None and resolved_shipment is None:
            resolved_shipment = await session.scalar(
                text("SELECT shipment_id FROM public.escalation_queue WHERE escalation_id = :id"),
                {"id": escalation_id},
            )

        if appointment_id is not None:
            context = await _appointment_context(session, appointment_id)
            if context is None:
                logger.error(
                    "notification outbox: appointment %s not found; %s not enqueued",
                    appointment_id, event_type,
                )
                return None
            resolved_shipment = resolved_shipment or context["shipment_id"]
            params["dock"] = dock_code or context["dock_code"] or "-"
            params["facility"] = context["facility_name"]
            params["reference"] = escalation_id or appointment_id
            if reason is None and context.get("cancellation_reason"):
                params["reason"] = context["cancellation_reason"]
            params.update(
                format_slot_fields(
                    context["slot_start_ts"], context["slot_end_ts"], context["timezone"]
                )
            )
            params.update(extra or {})  # an explicit override still wins over the resolved value

        # Recipient: the caller's server-derived id if it gave one, else this shipment's driver.
        # Every event in the catalog today is driver-facing -- see this module's docstring on why
        # a newly opened escalation notifies the driver rather than a coordinator.
        if recipient_user_id is None and resolved_shipment is not None:
            recipient_user_id = await _driver_user_for_shipment(session, resolved_shipment)

        title, body = render_event(event_type, params)

        if entity_id is None:
            logger.error("notification outbox: %s has no entity id; nothing enqueued", event_type)
            return None

        outbox_id = new_id("NOB")
        status = STATUS_PENDING if recipient_user_id else STATUS_UNROUTABLE
        last_error = (
            None
            if recipient_user_id
            else (
                "NOTIFICATION_UNROUTABLE: no active public.users row for this shipment's driver "
                "(section 7.4 -- detected at recipient resolution, before any send)"
            )
        )

        # SAVEPOINT, not a bare statement (2026-09-02, found by #42's suite 3 the hard way):
        # "never raises" alone is NOT transaction-safe -- a failed INSERT (e.g. the table not
        # yet migrated on this database) aborts the ENCLOSING transaction even when Python
        # swallows the exception, and the caller's next statement dies with
        # InFailedSQLTransactionError -- turning a missing notification into a 500 on the
        # business write this module exists never to fail. begin_nested() scopes the damage
        # to this write alone, making the deploy-order genuinely safe in both directions.
        async with session.begin_nested():
                inserted = await session.scalar(
                    text(
                        """
                    INSERT INTO public.notification_outbox (
                      outbox_id, dedupe_key, event_type, category, recipient_user_id, shipment_id,
                      related_entity_type, related_entity_id, title, body, payload_json,
                      status, last_error
                    ) VALUES (
                      :outbox_id, :dedupe_key, :event_type, :category, :recipient_user_id, :shipment_id,
                      :related_entity_type, :related_entity_id, :title, :body,
                      CAST(:payload_json AS jsonb), :status, :last_error
                    )
                    -- The replay answer. A producer running twice for one event writes nothing the
                    -- second time and gets no error, which is exactly M9's "1 notification" and is
                    -- enforced by `notification_outbox_dedupe_key_uidx`, not by this module.
                    ON CONFLICT (dedupe_key) DO NOTHING
                    RETURNING outbox_id
                    """
                ),
                {
                    "outbox_id": outbox_id,
                    "dedupe_key": build_dedupe_key(
                        event_type, entity_id, recipient_user_id, dedupe_scope
                    ),
                    "event_type": event_type,
                    "category": spec.category,
                    "recipient_user_id": recipient_user_id,
                    "shipment_id": resolved_shipment,
                    "related_entity_type": spec.entity_type,
                    "related_entity_id": entity_id,
                    "title": title,
                    "body": body,
                    "payload_json": json.dumps(
                        {k: v for k, v in params.items() if isinstance(v, (str, int, float, bool))},
                        default=str,
                    ),
                    "status": status,
                    "last_error": last_error,
                },
            )
        if inserted is None:
            logger.info(
                "notification outbox: %s for %s already enqueued (replay); nothing written",
                event_type, entity_id,
            )
        return inserted
    except Exception:
        # See the docstring: a notification must never be the reason a booking fails.
        logger.exception(
            "notification outbox: enqueue failed for %s (appointment=%s shipment=%s escalation=%s)",
            event_type, appointment_id, shipment_id, escalation_id,
        )
        return None


# ------------------------------------------------------------------------------------------
# The consumer -- runs AFTER the business transaction, in its own
# ------------------------------------------------------------------------------------------

#: A channel adapter takes one claimed outbox row and returns the id of whatever delivery record it
#: created, or raises to have the row retried. Section 3's module 10: *"The outbox keeps a pluggable
#: channel adapter, so adding [SMS] later is not a rewrite."*
ChannelAdapter = Callable[[AsyncSession, dict[str, Any]], Awaitable[str]]


def _in_app_adapter() -> ChannelAdapter:
    """Imported lazily so `notification_service` can stay free of any dependency on this module.

    The direction of the dependency is the point: the outbox knows about its channels, a channel
    knows nothing about the outbox. That is what lets an SES adapter be added later without either
    file learning about the other.
    """
    from app.services import notification_service

    return notification_service.deliver_in_app_notification


#: v1 delivers IN_APP only, and the absences are load-bearing rather than unfinished:
#:
#: * **EMAIL (SES)** -- TECH_STACK section 6 designs it; there is no `boto3` SES client, no sender
#:   identity and no template anywhere in `backend/` (grep, 2026-09-02). An adapter that logged
#:   "would have emailed" would make `operational_messages.delivery_status = 'SENT'` a lie, and
#:   section 7.4's whole point is *"a confirmation nobody received is not a confirmation."*
#: * **WEB_PUSH (VAPID)** -- TECH_STACK section 6 designs it; there is no VAPID key pair, no
#:   subscription store, and no service-worker `push` listener on the client (grep across
#:   `frontend/src/`, 2026-09-02). Section 6.1 does **not** specify a push-subscription table, so
#:   building one here would be inventing schema the design does not have.
#:
#: Both are recorded as named gaps on issue #94 rather than stubbed.
CHANNEL_ADAPTERS: dict[str, Callable[[], ChannelAdapter]] = {"IN_APP": _in_app_adapter}


@dataclass
class DrainResult:
    """What one drain cycle did. Shaped like `SweepResult` so both jobs report alike."""

    as_of: str
    claimed: int = 0
    delivered: int = 0
    failed: int = 0
    batch_limit: int = DEFAULT_DRAIN_BATCH_LIMIT
    batch_limit_reached: bool = False

    def model_dump(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "claimed": self.claimed,
            "delivered": self.delivered,
            "failed": self.failed,
            "batch_limit": self.batch_limit,
            "batch_limit_reached": self.batch_limit_reached,
        }


async def drain_outbox(
    session: AsyncSession, *, limit: int = DEFAULT_DRAIN_BATCH_LIMIT, now: datetime | None = None
) -> DrainResult:
    """Deliver pending outbox rows. Commits per row. Safe to run concurrently with itself.

    `FOR UPDATE ... SKIP LOCKED` is the concurrency mechanism
    (supabase-postgres-best-practices/lock-skip-locked; PostgreSQL "SELECT", FOR UPDATE clause):
    two overlapping drains take disjoint rows instead of one blocking on the other. That matters
    less for throughput here than for the EventBridge budget -- a blocked drain burns its 5-second
    invocation waiting, then gets retried into the same wait.

    **One row per transaction**, exactly like the expiry sweeper: a single row whose adapter throws
    must not roll back the deliveries that already succeeded in the same cycle.

    Idempotency under retry needs no key: the `status = 'PENDING'` predicate is the guard. A
    replayed drain finds the rows it already delivered no longer matching and does nothing.
    """
    moment = now or datetime.now(timezone.utc)
    result = DrainResult(as_of=moment.isoformat(), batch_limit=limit)

    claimed = (
        await session.execute(
            text(
                """
                SELECT outbox_id, event_type, category, recipient_user_id,
                       related_entity_type, related_entity_id, title, body, attempts
                FROM public.notification_outbox
                WHERE status = 'PENDING'
                ORDER BY created_at
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"limit": limit},
        )
    ).mappings().all()
    rows = [dict(r) for r in claimed]
    result.claimed = len(rows)
    result.batch_limit_reached = len(rows) >= limit
    # The claiming SELECT opened a transaction and holds a row lock on every row above. Release it
    # before the per-row work: each row re-reads and re-locks itself below, so holding the batch
    # lock across the whole cycle would only serialise a second drain against rows this one may
    # never reach.
    await session.commit()

    for row in rows:
        try:
            delivered = await _deliver_one(session, row, moment=moment)
        except Exception:
            await session.rollback()
            logger.exception("notification outbox: delivery crashed for %s", row["outbox_id"])
            delivered = False
        if delivered:
            result.delivered += 1
        else:
            result.failed += 1

    logger.info(
        "notification outbox drain: claimed=%d delivered=%d failed=%d batch_limit_reached=%s",
        result.claimed, result.delivered, result.failed, result.batch_limit_reached,
    )
    return result


async def _deliver_one(session: AsyncSession, row: dict[str, Any], *, moment: datetime) -> bool:
    """One row, one transaction. Returns whether it reached DELIVERED.

    Re-reads the row `FOR UPDATE` rather than trusting the batch snapshot: between the claim above
    and this call, a concurrent drain may already have delivered it. The `status = 'PENDING'`
    predicate on the re-read is what makes that a silent no-op instead of a double-send -- the same
    predicate-is-the-guard shape `expiry._expire_one_pending` uses for the same reason.
    """
    outbox_id = row["outbox_id"]
    locked = (
        await session.execute(
            text(
                """
                SELECT outbox_id, event_type, category, recipient_user_id,
                       related_entity_type, related_entity_id, title, body, attempts
                FROM public.notification_outbox
                WHERE outbox_id = :outbox_id AND status = 'PENDING'
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"outbox_id": outbox_id},
        )
    ).mappings().first()
    if locked is None:
        await session.commit()
        return False

    payload = dict(locked)
    attempts = int(payload["attempts"]) + 1

    try:
        adapter = CHANNEL_ADAPTERS["IN_APP"]()
        notification_id = await adapter(session, payload)
    except Exception as exc:
        # Terminal only after MAX_DELIVERY_ATTEMPTS. Section 7.4's `NOTIFICATION_FAILED` -- *"a
        # confirmation nobody received is not a confirmation"* -- says a FAILED send must raise an
        # escalation. That leg is NOT wired here: raising it needs a write into
        # `escalation_queue`, which belongs to `escalation_service`, and this pass does not own
        # that file. Recorded as a named gap on issue #94 with the exact hook point, rather than
        # half-built. The row is FAILED, countable, and carries its own error text.
        terminal = attempts >= MAX_DELIVERY_ATTEMPTS
        await session.execute(
            text(
                """
                UPDATE public.notification_outbox
                SET attempts = :attempts,
                    last_error = :last_error,
                    status = CASE WHEN :terminal THEN 'FAILED' ELSE 'PENDING' END
                WHERE outbox_id = :outbox_id
                """
            ),
            {
                "outbox_id": outbox_id,
                "attempts": attempts,
                "last_error": f"{type(exc).__name__}: {exc}"[:1000],
                "terminal": terminal,
            },
        )
        await session.commit()
        logger.warning(
            "notification outbox: delivery attempt %d/%d failed for %s (%s)%s",
            attempts, MAX_DELIVERY_ATTEMPTS, outbox_id, type(exc).__name__,
            " -- now FAILED, NOTIFICATION_FAILED escalation NOT raised (issue #94 gap)"
            if terminal else "",
        )
        return False

    await session.execute(
        text(
            """
            UPDATE public.notification_outbox
            SET status = 'DELIVERED',
                delivered_at = :delivered_at,
                attempts = :attempts,
                last_error = NULL,
                notification_id = :notification_id
            WHERE outbox_id = :outbox_id
            """
        ),
        {
            "outbox_id": outbox_id,
            "delivered_at": moment,
            "attempts": attempts,
            "notification_id": notification_id,
        },
    )
    await session.commit()
    return True


async def enqueue_for_transition(
    session: AsyncSession,
    *,
    target_status: str,
    appointment_id: str,
    shipment_id: str | None = None,
    reason: str | None = None,
) -> str | None:
    """One-line producer seam for `allocation._ops_pending_transition`'s REJECTED/EXPIRED split.

    An unmapped status is a deliberate no-op rather than an error: `_ops_pending_transition` is
    reachable with statuses that carry no driver-facing consequence, and inventing a notification
    for one would put an unreviewed message in front of a driver.
    """
    event_type = EVENT_FOR_TRANSITION.get(target_status)
    if event_type is None:
        return None
    return await enqueue_notification(
        session,
        event_type=event_type,
        appointment_id=appointment_id,
        shipment_id=shipment_id,
        reason=reason,
    )


async def enqueue_option_withdrawn(
    session: AsyncSession, *, appointment_ids: list[str], dock_code: str | None = None
) -> int:
    """FR-SYS-020's "dock down" leg, fanned out over the appointments a block displaces.

    Section 5.1's cascade rule: *"capacity incident -> one run scoped to the affected docks and
    window -> one proposal -> planner applies -> notifications batch out. Not N independent
    escalations."* N *notifications* is right where N escalations is wrong -- each affected driver
    is a different person who has to be told about their own slot -- and `build_dedupe_key`'s
    recipient component is what keeps those N from collapsing into one.

    Returns how many rows were newly enqueued (replays and unroutable recipients excluded from the
    first number by `enqueue_notification` itself).
    """
    written = 0
    for appointment_id in appointment_ids:
        if await enqueue_notification(
            session,
            event_type=OPTION_WITHDRAWN,
            appointment_id=appointment_id,
            dock_code=dock_code,
        ):
            written += 1
    return written


async def notify_after_commit(
    session: AsyncSession, *, limit: int = DEFAULT_DRAIN_BATCH_LIMIT
) -> None:
    """Best-effort immediate drain, for a producer that wants its notification visible *now*.

    **Optional, and the periodic job is the authoritative path.** TECH_STACK section 6 puts
    delivery on the EventBridge sweeper's cadence, and that job alone is sufficient -- this only
    shortens the in-app latency for a driver who is looking at the screen when their slot is
    confirmed, from up-to-a-minute to immediate.

    Call it strictly **after** the business `session.commit()`. Called before, it would drain a row
    that has not committed yet -- it would see nothing (its own claim query runs in the same
    uncommitted transaction and the delivery would then be rolled back with the business write if
    that failed), which is a silent correctness hole rather than a latency question.

    Swallows everything, by construction. A drain fault after a committed booking must not turn a
    successful 200 into a 500 for the caller; the row stays PENDING and the next sweep gets it.
    """
    try:
        await drain_outbox(session, limit=limit)
    except Exception:
        logger.exception("notification outbox: post-commit drain failed; leaving rows PENDING")
