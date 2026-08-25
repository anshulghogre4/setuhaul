"""Notification shared tools -- SOLUTION_DESIGN.md section 7.5.8, FR-X-019 .. FR-X-022.

`notifications`/`notification_preferences` (`supabase/migrations/20260825211500_e35_notifications_
and_search.sql`) are new tables -- Module 10 (Notification/Outbox) is entirely unbuilt (confirmed
live 2026-08-25: no such table existed anywhere before this migration), the same class of gap E3.2
found for the Sequencer. Unlike the Sequencer, these tools are not blocked by that: a user can set
preferences and read a correctly-empty feed today. **No producer is wired here or anywhere else in
this pass** -- nothing in the codebase inserts a `notifications` row yet, so the feed being empty
right now is expected, not a bug. Wiring every write path that should notify someone (escalation
creation, appointment confirm/reject, etc.) is separate, cross-cutting scope, left as a known gap
rather than silently assumed complete.

`category` is a fixed three-value grouped model (`ESCALATION`/`APPOINTMENT`/`SYSTEM`), matching
the migration's own `CHECK` constraint -- `Source: assumption, untested`, since section 7.5.8 never
names the groups, only that they are grouped rather than per-event.
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
