"""The coordinator reply path: posting as `OPERATIONS`, and delivering it to the driver.

E5.2, issues **#55** (no tool posts a message as `sender_type = 'OPERATIONS'`) and **#58** (the
takeover divider is written to `chat_messages` but the driver's feed reads Redis, so it never
arrives). They are one problem and are solved together here.

## The #58 architecture decision, stated once, in the place it is enforced

**PostgreSQL `chat_messages` is the write of record. Redis is a projection of an
already-committed row into the driver's live feed. Never the reverse.**

Rejected alternatives, and why:

* *Make `chat_messages` the driver's read path.* Architecturally the tidiest, and genuinely
  tempting -- but the driver turn path (`run_assistant._prepare_turn`) reads Redis in one
  pipelined round trip that E4.3/E4.4 spent two epics reducing, and **ordinary driver/assistant
  turns are not written to `chat_messages` at all today** (only `eta_service`'s ETA-update
  message is). Switching the read path therefore means first adding a Postgres write to every
  chat turn, then re-tuning the turn's latency budget. That is a milestone, not this pass, and it
  would put a schema/perf change on the critical path of a fix that does not need one.
* *A background sync worker between the two stores.* Over-engineered at this system's stated
  5-concurrent-user calibration (`TECH_STACK.md`). It buys eventual consistency for a problem a
  synchronous post-commit append already solves, and adds a component that can be down.
* *Write only to Redis, matching how driver messages already flow.* Rejected outright: it would
  make Upstash the only record of a human coordinator's commitment to a driver, with a 24h TTL.
  `AGENTS.md` is explicit that Redis is "bounded, non-authoritative conversation/session state"
  and PostgreSQL is the business source of truth. A coordinator's message to a driver during an
  escalation is exactly the kind of thing that must survive past tomorrow and be auditable.

**Consequences, stated plainly rather than discovered later.** The Postgres row always exists once
this returns success. The Redis projection can fail independently -- Upstash unconfigured or down,
or (the ordinary case) no Redis history key for that thread because the driver's 24h window has
expired or they have not used this thread from a live chat session. When it does, the response
carries `delivered: false` with a machine-readable `delivery_reason`; it does **not** pretend the
driver saw it and does **not** fail the write. The known remaining gap: a message posted while the
projection is unavailable is durable but will not appear in the driver's feed even after Redis
recovers, because nothing back-fills Redis from `chat_messages`. Closing that needs the read-path
merge this pass deliberately did not take on.

## Authorization (M15 / NFR-019)

Every scope value is derived server-side. The caller supplies a `thread_id` and message text and
nothing else: the facility is read from the thread's shipment, the driver identity from the
thread's `driver_id`, and the sender from the verified token's `user_id`. There is no argument by
which a client can name a facility, a driver, or a sender.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import Settings
from app.repositories import chat_threads as chat_repo
from app.repositories.scope import assert_facility_write_scope
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id
from app.services.redis_memory import ConversationMemory

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000

# `chat_messages.sender_type`'s CHECK constraint (baseline SQL:269-270). Named here so a typo
# surfaces as an import error rather than a runtime constraint violation mid-takeover.
SENDER_OPERATIONS = "OPERATIONS"
SENDER_SYSTEM = "SYSTEM"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def deliver_to_driver_feed(
    session: AsyncSession,
    *,
    settings: Settings | None,
    thread_id: str,
    content: str,
    sender: str,
    sender_name: str | None,
    message_id: str | None,
    message_ts: str | None = None,
    thread: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one committed `chat_messages` row into the driver's Redis feed.

    Call this **after** the Postgres transaction commits, never inside it: a projection made for a
    write that then rolls back would show the driver a message that does not exist.

    Returns `{"delivered": bool, "reason": str | None}`. Every failure mode is a named reason, not
    an exception -- the caller's own write already succeeded and must not be reported as failed
    because a cache append did not land.
    """
    try:
        return await _deliver_to_driver_feed(
            session, settings=settings, thread_id=thread_id, content=content, sender=sender,
            sender_name=sender_name, message_id=message_id, message_ts=message_ts, thread=thread,
        )
    except Exception as exc:  # noqa: BLE001
        # Blanket catch on purpose, and this is the one place it is right. Every caller reaches
        # here *after* committing a durable `chat_messages` row, so letting an exception escape
        # would make the router return 500 for a write that actually succeeded -- the coordinator
        # would retry and post the message twice. A projection failure downgrades to
        # `delivered: false`; it never rewrites the outcome of the write itself.
        logger.warning("Driver-feed projection failed for %s: %s", thread_id, type(exc).__name__)
        return {"delivered": False, "reason": f"PROJECTION_ERROR:{type(exc).__name__}"}


async def _deliver_to_driver_feed(
    session: AsyncSession,
    *,
    settings: Settings | None,
    thread_id: str,
    content: str,
    sender: str,
    sender_name: str | None,
    message_id: str | None,
    message_ts: str | None,
    thread: dict[str, Any] | None,
) -> dict[str, Any]:
    if settings is None:
        # A caller that did not thread Settings through. Not fatal: the durable row is written.
        return {"delivered": False, "reason": "SETTINGS_UNAVAILABLE"}

    row = thread if thread is not None else await chat_repo.get_thread_context(session, thread_id)
    if row is None:
        return {"delivered": False, "reason": "THREAD_NOT_FOUND"}
    driver_user_id = row.get("driver_user_id")
    if not driver_user_id:
        # `users.driver_id` has no row for this driver, so the Redis key -- which is namespaced by
        # `users.user_id` -- cannot be built at all.
        return {"delivered": False, "reason": "DRIVER_USER_UNMAPPED"}

    memory = ConversationMemory(settings)
    if memory.degraded:
        return {"delivered": False, "reason": memory.degrade_reason or "REDIS_UNAVAILABLE"}

    session_id = memory.resolve_thread_session_id(user_id=str(driver_user_id), thread_id=thread_id)
    if not session_id:
        # Ordinary and expected: the driver has no live Redis conversation for this thread inside
        # the 24h window. The message is durable; it just has no live feed to appear in.
        return {"delivered": False, "reason": "NO_LIVE_DRIVER_SESSION"}

    ok = await memory.append_agent_side_message(
        user_id=str(driver_user_id),
        thread_id=thread_id,
        session_id=session_id,
        content=content,
        sender=sender,
        sender_name=sender_name,
        message_id=message_id,
        message_ts=message_ts,
    )
    if not ok:
        return {"delivered": False, "reason": memory.degrade_reason or "REDIS_WRITE_FAILED"}
    return {"delivered": True, "reason": None}


async def post_operations_message(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    thread_id: str,
    message_text: str,
    idempotency_key: str,
    client_message_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Issue #55 -- `post_operations_message`. The tool §7.5.5 never defined and the console needs.

    §7.5.5's catalog covers acknowledge/reassign/take-over/hand-back/resolve/cancel and states that
    co-pilot drafting "produces text a human still sends through the ordinary chat-send path". The
    ordinary chat-send path is `POST /chat`, which **runs the assistant** -- precisely what
    `take_over_thread` just switched off. So there was no path at all; this is it. Argument shape
    follows the rest of §7.5.5: an id the caller already legitimately holds, an `Idempotency-Key`
    because the write is consequential, and no scope argument (M15).

    Typed outcomes rather than exceptions for business refusals, matching `ALREADY_ACTIONED` /
    `NOT_IN_PROGRESS` / `ALREADY_TAKEN_OVER` in `escalation_service.py`:

    * `POSTED` -- row written; `delivered` says whether the driver's live feed also got it.
    * `NOT_TAKEN_OVER` -- the thread is not `ESCALATED`, so no coordinator has taken it over and
      the assistant is still answering. Posting here would interleave a human and the bot in the
      same conversation with neither aware of the other. `delivered` is `false`, unambiguously.

    `Idempotency-Key` is **required**, unlike `resolve_escalation`'s optional one: this write is a
    message a driver reads and nobody can unsend, and the console's composer is a retry-prone
    surface. A replay returns the original row rather than posting twice.
    """
    text_body = (message_text or "").strip()
    if not text_body:
        raise AppError("Message text is required.", code="EMPTY_MESSAGE", status_code=422)
    if len(text_body) > MAX_MESSAGE_LENGTH:
        raise AppError(
            f"Message text exceeds {MAX_MESSAGE_LENGTH} characters.",
            code="MESSAGE_TOO_LONG",
            status_code=422,
        )
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError(
            "Insufficient permissions to post as Operations.", code="FORBIDDEN", status_code=403
        )

    route = f"POST /api/v1/operations/threads/{thread_id}/messages"
    req_hash = payload_hash({"thread_id": thread_id, "message_text": text_body})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    thread = await chat_repo.get_thread_context(session, thread_id)
    if thread is None:
        raise AppError(f"Thread '{thread_id}' not found.", code="NOT_FOUND", status_code=404)

    facility_id = thread.get("facility_id")
    if not facility_id:
        # A thread with no shipment has no facility, so there is no scope to check it against.
        # Refused rather than written unscoped -- the M15 failure mode is silently allowing a
        # write nobody could have authorised.
        raise AppError(
            "This thread has no shipment, so it cannot be scoped to a facility.",
            code="THREAD_UNSCOPED",
            status_code=409,
        )
    assert_facility_write_scope(ctx, str(facility_id))

    if str(thread["thread_status"]) != "ESCALATED":
        return {
            "code": "NOT_TAKEN_OVER",
            "thread_id": thread_id,
            "thread_status": str(thread["thread_status"]),
            "delivered": False,
            "delivery_reason": "THREAD_NOT_TAKEN_OVER",
        }

    # Second replay layer: `chat_messages_external_message_id_uidx` is unique, so a client that
    # varied its Idempotency-Key but reused its client_message_id would otherwise hit a raw
    # IntegrityError instead of being told this message already exists.
    external_id = (client_message_id or idempotency_key).strip()
    existing = await chat_repo.find_message_by_external_id(session, external_id)
    if existing is not None:
        return {
            "code": "POSTED",
            "chat_message_id": existing["chat_message_id"],
            "thread_id": existing["thread_id"],
            "sender_type": existing["sender_type"],
            "sender_name": ctx.full_name,
            "message_text": existing["message_text"],
            "message_ts": existing["message_ts"],
            "delivered": False,
            "delivery_reason": "DUPLICATE_CLIENT_MESSAGE_ID",
            "idempotent_replay": True,
        }

    message_id = new_id("MSG")
    message_ts = _now_iso()
    await chat_repo.insert_message(
        session,
        chat_message_id=message_id,
        thread_id=thread_id,
        sender_type=SENDER_OPERATIONS,
        sender_reference=ctx.user_id,
        message_text=text_body,
        message_ts=message_ts,
        external_message_id=external_id,
    )

    result: dict[str, Any] = {
        "code": "POSTED",
        "chat_message_id": message_id,
        "thread_id": thread_id,
        "sender_type": SENDER_OPERATIONS,
        "sender_name": ctx.full_name,
        "message_text": text_body,
        "message_ts": message_ts,
        # Stored as `false` on purpose: the idempotency record is written before the projection
        # runs, and a *replay* delivers nothing new, so `false` is the honest value for it.
        "delivered": False,
        "delivery_reason": None,
    }
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result,
    )
    await session.commit()

    # Post-commit, deliberately: see this module's docstring. The durable row exists whatever
    # happens next.
    delivery = await deliver_to_driver_feed(
        session,
        settings=settings,
        thread_id=thread_id,
        content=text_body,
        sender=SENDER_OPERATIONS,
        sender_name=ctx.full_name,
        message_id=message_id,
        message_ts=message_ts,
        thread=thread,
    )
    return {**result, "delivered": delivery["delivered"], "delivery_reason": delivery["reason"]}
