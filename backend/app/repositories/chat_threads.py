"""Persistence for `chat_threads` / `chat_messages`.

E5.2 (issues #55, #56, #58): the ops-console coordinator reply path needs to read a thread, write
an `OPERATIONS`-sender message, and read a thread's transcript back. Before this module that SQL
lived inline in `escalation_service.py` (the two `SYSTEM` divider inserts) and nowhere else --
`AGENTS.md`'s "persistence belongs in repositories" rule, applied to the one table pair the
takeover flow actually touches.

Two schema facts every caller here depends on, both verified against
`supabase/migrations/20260805201923_setuhaul_baseline.sql`:

* `chat_messages.message_ts` is `TEXT`, not `timestamptz` (E1.1 converted six tables; this was not
  one of them), so every timestamp bound here is an ISO **string**. Binding a `datetime` raises
  `DataError` -- the mirror image of the bug `eta_service.py:300-310` documents.
* `chat_messages.sender_type` already admits `'OPERATIONS'` in its CHECK constraint
  (baseline SQL:269-270). Nothing in `backend/app/` produced that value before #55; no migration
  is needed to start producing it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_thread_context(session: AsyncSession, thread_id: str) -> dict[str, Any] | None:
    """One thread plus everything a scoped write against it needs, in a single round trip.

    `facility_id` comes from the thread's shipment (`chat_threads` carries none of its own), and
    `driver_user_id` from `users.driver_id` -- the Redis conversation key is namespaced by
    `users.user_id`, not `drivers.driver_id`, so delivering into the driver's live feed is
    impossible without this join. Both are `LEFT JOIN`s: a thread with no shipment, or a driver
    with no user row, must come back as a thread with a `None` there rather than as "not found",
    so the caller can refuse it explicitly instead of silently treating it as missing.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT t.thread_id, t.driver_id, t.shipment_id, t.thread_status,
                       s.destination_facility_id AS facility_id,
                       u.user_id AS driver_user_id
                FROM public.chat_threads t
                LEFT JOIN public.shipments s ON s.shipment_id = t.shipment_id
                LEFT JOIN public.users u ON u.driver_id = t.driver_id
                WHERE t.thread_id = :thread_id
                """
            ),
            {"thread_id": thread_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def insert_message(
    session: AsyncSession,
    *,
    chat_message_id: str,
    thread_id: str,
    sender_type: str,
    sender_reference: str | None,
    message_text: str,
    message_ts: str,
    external_message_id: str | None = None,
) -> None:
    """Insert one `chat_messages` row. `message_ts` must already be an ISO string (see module doc)."""
    await session.execute(
        text(
            """
            INSERT INTO public.chat_messages (
              chat_message_id, thread_id, sender_type, sender_reference, message_text,
              message_ts, external_message_id
            ) VALUES (
              :chat_message_id, :thread_id, :sender_type, :sender_reference, :message_text,
              :message_ts, :external_message_id
            )
            """
        ),
        {
            "chat_message_id": chat_message_id,
            "thread_id": thread_id,
            "sender_type": sender_type,
            "sender_reference": sender_reference,
            "message_text": message_text,
            "message_ts": message_ts,
            "external_message_id": external_message_id,
        },
    )


async def find_message_by_external_id(
    session: AsyncSession, external_message_id: str
) -> dict[str, Any] | None:
    """Second-layer replay guard for `post_operations_message`.

    `chat_messages_external_message_id_uidx` (migration 20260807184700) makes this column unique,
    so a retried send that reuses the same client message id would otherwise fail on an
    `IntegrityError` rather than resolve as a replay. The idempotency table is the first layer;
    this catches a client that varies its `Idempotency-Key` but not its `client_message_id`.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT chat_message_id, thread_id, sender_type, sender_reference, message_text,
                       message_ts
                FROM public.chat_messages
                WHERE external_message_id = :external_message_id
                LIMIT 1
                """
            ),
            {"external_message_id": external_message_id},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_thread_messages(
    session: AsyncSession, thread_id: str, *, limit: int = 200
) -> list[dict[str, Any]]:
    """A thread's durable transcript, oldest first.

    Ordered by `message_ts` (the `ix_chat_messages_thread_time` index's second key), then by id as
    a stable tiebreak -- two rows written inside one transaction can share an ISO timestamp string
    to the microsecond, and an unstable order would reshuffle the takeover divider against the
    message that followed it.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT m.chat_message_id, m.thread_id, m.sender_type, m.sender_reference,
                       m.message_text, m.message_ts, u.full_name AS sender_name
                FROM public.chat_messages m
                LEFT JOIN public.users u ON u.user_id = m.sender_reference
                WHERE m.thread_id = :thread_id
                ORDER BY m.message_ts ASC, m.chat_message_id ASC
                LIMIT :limit
                """
            ),
            {"thread_id": thread_id, "limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def set_thread_status(session: AsyncSession, thread_id: str, thread_status: str) -> None:
    await session.execute(
        text("UPDATE public.chat_threads SET thread_status = :thread_status WHERE thread_id = :thread_id"),
        {"thread_status": thread_status, "thread_id": thread_id},
    )
