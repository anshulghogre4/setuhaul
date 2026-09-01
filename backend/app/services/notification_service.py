"""Notification shared tools -- SOLUTION_DESIGN.md section 7.5.8, FR-X-019 .. FR-X-023.

`notifications`/`notification_preferences` (`supabase/migrations/20260825211500_e35_notifications_
and_search.sql`) are the user-facing half of Module 10 (Notification/Outbox).

## What changed 2026-09-02 (issue #94): this file now has a producer, and a defined role

E3.5 shipped these four read/write tools against tables **nothing ever wrote to**, and said so
honestly in this docstring's previous version. `supabase/migrations/20260902093000_notification_
outbox.sql` closes that: `notification_outbox` -- designed in section 6.1 and never migrated until
then -- is now the authoritative event record, written inside the business transaction that causes
it, and `public.notifications` is **the IN_APP channel's delivery record and the user's read
model**, written *only* by that outbox's drain through `deliver_in_app_notification` below.

The division matters, because issue #94's actual finding was that three notification artifacts
existed and none connected:

| Artifact | Job | Written by |
|---|---|---|
| `notification_outbox` | authoritative event + delivery intent, transactional with the business write | `notification_outbox.enqueue_notification` |
| `notifications` (here) | IN_APP delivery record + `is_read`/`read_at` read model | `deliver_in_app_notification`, from the drain, only |
| `operational_messages` | EMAIL delivery status (TECH_STACK section 6) | nothing yet -- no SES client exists |

**Nothing outside the drain may insert a `notifications` row.** A business path that wrote here
directly would be writing a notification that survives its own transaction's rollback, which is the
one thing section 6.1's outbox exists to prevent.

`category` is a fixed three-value grouped model (`ESCALATION`/`APPOINTMENT`/`SYSTEM`), matching
the migration's own `CHECK` constraint -- `Source: assumption, untested`, since section 7.5.8 never
names the groups, only that they are grouped rather than per-event. `notification_outbox`'s
`category` CHECK is byte-identical, because the drain copies the value straight across.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext

NOTIFICATION_CATEGORIES = frozenset({"ESCALATION", "APPOINTMENT", "SYSTEM"})


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------------------------
# The IN_APP channel adapter -- the consumption end of section 6.1's outbox (issue #94)
# --------------------------------------------------------------------------------------------


def in_app_notification_id(outbox_id: str) -> str:
    """A `notifications` id derived deterministically from the outbox row that produced it.

    Not cosmetic. It makes the insert below idempotent by primary key, which is a second,
    independent guarantee on top of `_deliver_one`'s `status = 'PENDING'` row lock: if that guard
    were ever weakened, a re-delivery would collide on this id and do nothing, rather than putting a
    duplicate in the driver's feed. Two cheap mechanisms for "exactly one notification" (NFR-009)
    is the right number when the failure mode is a driver seeing the same slot confirmed twice.

    `NOB-1A2B...` -> `NTF-1A2B...`: the suffix `app.services.ids.new_id` generated is already a
    uuid4 fragment, so it carries all the uniqueness this needs without a second random draw.
    """
    return f"NTF-{outbox_id.split('-', 1)[-1]}"


async def deliver_in_app_notification(session: AsyncSession, outbox_row: dict[str, Any]) -> str:
    """Deliver one outbox row to the in-app feed. Registered as `CHANNEL_ADAPTERS['IN_APP']`.

    Section 3's module 10: *"The outbox keeps a pluggable channel adapter, so adding [a channel]
    later is not a rewrite."* This is that interface's first implementation -- take a claimed row,
    create the channel's own delivery record, return its id. The EMAIL adapter, when an SES client
    exists, is the same signature writing `operational_messages` instead.

    **Does not commit.** `notification_outbox._deliver_one` owns the transaction: this insert and
    the outbox row's transition to DELIVERED commit together or not at all, so the feed can never
    hold a notification the outbox believes is still pending, nor the reverse.

    Raises on a genuine database failure, which is the contract the drain expects -- it catches,
    increments `attempts`, and retries on the next cycle.

    `is_read` is not set here and defaults to 0: delivery and reading are different events with
    different owners, which is exactly why the outbox does not carry read state and this table does.
    """
    notification_id = in_app_notification_id(outbox_row["outbox_id"])
    await session.execute(
        text(
            """
            INSERT INTO public.notifications (
              notification_id, user_id, category, title, body,
              related_entity_type, related_entity_id
            ) VALUES (
              :notification_id, :user_id, :category, :title, :body,
              :related_entity_type, :related_entity_id
            )
            ON CONFLICT (notification_id) DO NOTHING
            """
        ),
        {
            "notification_id": notification_id,
            "user_id": outbox_row["recipient_user_id"],
            "category": outbox_row["category"],
            "title": outbox_row["title"],
            "body": outbox_row["body"],
            "related_entity_type": outbox_row["related_entity_type"],
            "related_entity_id": outbox_row["related_entity_id"],
        },
    )
    return notification_id


async def get_notifications(
    session: AsyncSession,
    ctx: ExecutionContext,
    cursor: str | None = None,
    unread_only: bool = False,
) -> dict[str, Any]:
    """SS7.5.8 `get_notifications` -- `cursor?`, `unread_only?`.

    `cursor` is the `notification_id` of the last row the caller already has (keyset pagination on
    `created_at DESC, notification_id DESC` -- stable under concurrent inserts, unlike an OFFSET).
    Always scoped to `user_id = ctx.user_id`: this feed is never facility- or role-scoped, only
    ever the caller's own (SS7.5.8: "This user's notification feed").
    """
    params: dict[str, Any] = {"user_id": ctx.user_id}
    cursor_filter = ""
    if cursor:
        cursor_row = (
            await session.execute(
                text("SELECT created_at FROM public.notifications WHERE notification_id = :cid AND user_id = :user_id"),
                {"cid": cursor, "user_id": ctx.user_id},
            )
        ).mappings().first()
        if cursor_row is not None:
            cursor_filter = "AND (created_at, notification_id) < (:cursor_created_at, :cursor)"
            params["cursor_created_at"] = cursor_row["created_at"]
            params["cursor"] = cursor
    unread_filter = "AND is_read = 0" if unread_only else ""
    rows = (
        await session.execute(
            text(
                f"""
                SELECT notification_id, category, title, body, related_entity_type,
                       related_entity_id, is_read, created_at, read_at
                FROM public.notifications
                WHERE user_id = :user_id
                  {unread_filter}
                  {cursor_filter}
                ORDER BY created_at DESC, notification_id DESC
                LIMIT 50
                """
            ),
            params,
        )
    ).mappings().all()
    items = [dict(r) for r in rows]
    return {
        "as_of": _as_of(), "source": "postgresql",
        "items": items,
        "next_cursor": items[-1]["notification_id"] if len(items) == 50 else None,
    }


async def mark_notifications_read(
    session: AsyncSession, ctx: ExecutionContext, notification_ids: list[str],
) -> dict[str, Any]:
    """SS7.5.8 `mark_notifications_read` -- `notification_ids[]`. Idempotent by construction: the
    `WHERE is_read = 0` on the UPDATE means re-marking an already-read row is simply a no-op row,
    not an error, and the caller cannot mark another user's notification (`user_id` predicate)."""
    if not notification_ids:
        return {"as_of": _as_of(), "code": "READ", "marked_count": 0}
    now_iso = datetime.now(timezone.utc)
    result = await session.execute(
        text(
            """
            UPDATE public.notifications
            SET is_read = 1, read_at = :now
            WHERE user_id = :user_id AND notification_id = ANY(:ids) AND is_read = 0
            """
        ),
        {"now": now_iso, "user_id": ctx.user_id, "ids": list(notification_ids)},
    )
    await session.commit()
    return {"as_of": _as_of(), "code": "READ", "marked_count": result.rowcount or 0}


async def get_notification_preferences(session: AsyncSession, ctx: ExecutionContext) -> dict[str, Any]:
    """SS7.5.8 `get_notification_preferences` -- arguments: none.

    Returns one row per category, defaulting a category with no saved row to the same defaults
    the table's own columns default to (web push + email on, digest off) -- a user who has never
    opened preferences still gets a complete, sensible answer, not three missing rows.
    """
    rows = (
        await session.execute(
            text(
                "SELECT category, channel_web_push, channel_email, digest_mode, updated_at "
                "FROM public.notification_preferences WHERE user_id = :user_id"
            ),
            {"user_id": ctx.user_id},
        )
    ).mappings().all()
    by_category = {r["category"]: dict(r) for r in rows}
    categories = [
        by_category.get(
            category,
            {
                "category": category, "channel_web_push": 1, "channel_email": 1,
                "digest_mode": 0, "updated_at": None,
            },
        )
        for category in sorted(NOTIFICATION_CATEGORIES)
    ]
    return {"as_of": _as_of(), "source": "postgresql", "categories": categories}


async def update_notification_preferences(
    session: AsyncSession, ctx: ExecutionContext, categories: list[dict[str, Any]],
) -> dict[str, Any]:
    """SS7.5.8 `update_notification_preferences` -- `categories` (grouped, not per-event).

    One `UPSERT` per category in the request; categories the caller doesn't mention are left
    untouched, so this is a partial update, not a full replace -- a client changing one category's
    digest_mode does not have to resend the other two unchanged.
    """
    if not categories:
        raise AppError("At least one category is required.", code="INVALID_PREFERENCES", status_code=422)
    now = datetime.now(timezone.utc)
    for entry in categories:
        category = str(entry.get("category", "")).upper()
        if category not in NOTIFICATION_CATEGORIES:
            raise AppError(
                f"Unsupported category '{category}'.", code="INVALID_CATEGORY", status_code=422,
                detail=f"Supported: {', '.join(sorted(NOTIFICATION_CATEGORIES))}.",
            )
        await session.execute(
            text(
                """
                INSERT INTO public.notification_preferences (
                  user_id, category, channel_web_push, channel_email, digest_mode, updated_at
                ) VALUES (:user_id, :category, :web_push, :email, :digest, :updated_at)
                ON CONFLICT (user_id, category) DO UPDATE
                SET channel_web_push = EXCLUDED.channel_web_push,
                    channel_email = EXCLUDED.channel_email,
                    digest_mode = EXCLUDED.digest_mode,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "user_id": ctx.user_id, "category": category,
                "web_push": 1 if entry.get("channel_web_push", True) else 0,
                "email": 1 if entry.get("channel_email", True) else 0,
                "digest": 1 if entry.get("digest_mode", False) else 0,
                "updated_at": now,
            },
        )
    await session.commit()
    return {"as_of": _as_of(), "code": "UPDATED"}
