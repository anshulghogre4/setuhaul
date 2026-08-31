"""Read-only fact gathering for the ops co-pilot's resolution suggestion (issue #57).

Every query here is a `SELECT`. Nothing in this module writes, and nothing in the suggestion path
above it writes either -- `AGENTS.md`'s standing rule is that the LLM (and by extension anything
that recommends on its behalf) *orchestrates typed tools and never mutates business tables*, so a
suggestion is a read plus a recommendation and the coordinator presses the button.

**Why a new repository module rather than an addition to `repositories/operations.py`.** That file
is the E2.2 home for the five operations-portal *dashboard* reads (shipment rollups, exception
list, appointment schedule), all of which take an already-resolved facility scope and return list
payloads. These reads take a single `escalation_id` and fan out across six tables to assemble the
evidence for one decision. Different caller, different shape, different lifetime -- and keeping
them apart means the co-pilot can be deleted in one file if the capability is dropped.

**Scope note.** Nothing in this module enforces scope. `services/ops_copilot.py` resolves the
escalation's own `facility_id` and calls `assert_facility_visible` before any of these run
(`M15`/`NFR-019`, and `NFR-020`'s "enforced in the repository layer" is satisfied by
`repositories/scope.py`, which is where this project's scope predicates actually live -- this
module is a peer of it, not a bypass of it).

**Index access paths, checked against `supabase/migrations/`:**

* `escalation_queue` -- primary key on `escalation_id`.
* `chat_threads` -- primary key on `thread_id`, reached through the `LEFT JOIN LATERAL` on
  `shipment_id` that `escalation_service.get_exception_queue` already uses (same shape, so the
  suggestion and the queue row agree on which thread they mean).
* `appointments` -- `ux_current_active_appointment_per_shipment`, the partial unique index on
  `(shipment_id) WHERE is_current = 1 AND appointment_status IN (...)`. Exactly the predicate
  below.
* `eta_updates` -- `ix_eta_updates_shipment_created (shipment_id, created_at DESC)`.
* `chat_messages` -- `ix_chat_messages_thread_time (thread_id, message_ts)`.
* `facility_contacts` -- **no index, deliberately not added.** Six facilities with a handful of
  contacts each; a sequential scan of ~20 rows is the correct plan and an index here would be the
  premature optimisation `NFR-018` explicitly forbids ("no caching layers before a measured
  bottleneck").
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_escalation_with_thread(
    session: AsyncSession, escalation_id: str
) -> dict[str, Any] | None:
    """The escalation row plus its owner's name and its shipment's most recent chat thread.

    `driver_exceptions` ids are deliberately *not* resolved here, unlike
    `escalation_service._escalation_facility_id`. Those rows have no `escalation_status` and no
    `owner_user_id`, so every lifecycle rule the suggestion engine applies would have to invent a
    value for them. The ops console's queue only ever hands out `escalation_queue` ids, so an id
    this returns `None` for is a genuine 404 for this endpoint.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT eq.escalation_id, eq.shipment_id, eq.facility_id, eq.driver_id,
                       eq.escalation_type, eq.escalation_status, eq.severity_code,
                       eq.payload_json, eq.created_at, eq.updated_at, eq.owner_user_id,
                       u.full_name AS owner_name,
                       ct.thread_id, ct.thread_status
                FROM public.escalation_queue eq
                LEFT JOIN public.users u ON u.user_id = eq.owner_user_id
                LEFT JOIN LATERAL (
                  SELECT t.thread_id, t.thread_status
                  FROM public.chat_threads t
                  WHERE t.shipment_id = eq.shipment_id
                  ORDER BY t.opened_at DESC
                  LIMIT 1
                ) ct ON TRUE
                WHERE eq.escalation_id = :eid
                """
            ),
            {"eid": escalation_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_shipment_state(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    """`shipments.current_status` is the decisive fact for the cancel rule, so it is read first-hand.

    `CANCELLED` here is what `flows-and-states.md` Flow 1 step 5 names verbatim as the case for
    Cancel rather than Resolve ("the shipment itself was cancelled elsewhere"). Reading it means
    the suggestion is grounded in the shipment's own row, not in an inference from the escalation.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, current_status, priority_code, required_dock_type,
                       original_eta_ts, latest_eta_ts, destination_facility_id
                FROM public.shipments WHERE shipment_id = :sid
                """
            ),
            {"sid": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_current_appointment(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    """The shipment's live appointment, if it has one, with its slot window and dock.

    This is the *staleness* check, and it is the one genuinely non-obvious thing the co-pilot
    knows: a `NO_FEASIBLE_SLOT` or `PENDING_EXPIRED_UNACTIONED` escalation whose shipment now
    holds a `CONFIRMED` appointment was solved somewhere else and nobody closed the case.

    The predicate matches `ux_current_active_appointment_per_shipment` exactly (partial unique
    index), so this is an index lookup returning at most one row -- no `ORDER BY ... LIMIT 1`
    tiebreak needed, because the index already guarantees uniqueness.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.appointment_status, a.booking_source, a.confirmed_at,
                       a.booked_at, s.slot_start_ts, s.slot_end_ts, s.dock_id
                FROM public.appointments a
                JOIN public.appointment_slots s ON s.slot_id = a.slot_id
                WHERE a.shipment_id = :sid
                  AND a.is_current = 1
                  AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                """
            ),
            {"sid": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_latest_eta_update(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    """Most recent `eta_updates` row -- the grounding for `LOW_CONFIDENCE_ETA`.

    §7.4 gives that reason a *soft* SLA and no stated resolution, so the only honest thing the
    co-pilot can do is report whether a newer, firmer estimate has arrived since the escalation was
    raised. `confidence_code` is a real column with a real CHECK constraint
    (`LOW`/`MEDIUM`/`HIGH`), not a derived score.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT eta_update_id, source_type, declared_eta_ts, confidence_code,
                       delay_reason_code, created_at
                FROM public.eta_updates
                WHERE shipment_id = :sid
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"sid": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_last_thread_message(session: AsyncSession, thread_id: str) -> dict[str, Any] | None:
    """The newest message on the thread -- who spoke last, and when.

    "The driver wrote 40 minutes ago and nobody has answered" is a fact this table carries and a
    coordinator scanning a queue does not have. It is read as a *fact*, never as input to
    generating a reply: the owner's scope for this feature is explicitly a recommended action, not
    a drafted message, and nothing in this path composes driver-facing text.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT chat_message_id, sender_type, message_ts, requires_human_review
                FROM public.chat_messages
                WHERE thread_id = :tid
                ORDER BY message_ts DESC
                LIMIT 1
                """
            ),
            {"tid": thread_id},
        )
    ).mappings().all()
    return dict(row[0]) if row else None


async def list_unroutable_contacts(session: AsyncSession, facility_id: str) -> list[dict[str, Any]]:
    """Active facility contacts missing an email or a phone.

    §7.4's `NOTIFICATION_UNROUTABLE` is seeded by CON005 -- "GGN night-shift contact exists with a
    NULL email" -- and its stated resolution is to *correct the contact record*. This read names
    which contact and which field, which is the whole of what the co-pilot can honestly say about
    that reason: **no tool anywhere in §7.5 updates `facility_contacts`**, so the engine reports
    the broken record and abstains rather than recommending a button that does not exist.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT contact_id, contact_role, contact_name, email, phone
                FROM public.facility_contacts
                WHERE facility_id = :fid
                  AND active_flag = 1
                  AND (email IS NULL OR phone IS NULL)
                ORDER BY contact_role
                """
            ),
            {"fid": facility_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
