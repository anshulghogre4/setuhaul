"""Read-only operations-portal payloads.

E2.2 (issue #22): lifted wholesale out of `app/api/v1/routers/operations.py`, which was doing
scope resolution, SQL and response assembly inline. The split is now: router → this service
(resolve scope, assemble payload) → repository (SQL). Mirrors the existing `driver_reads.py`
convention rather than inventing a second one.

Every function here resolves the caller's facility scope through `repositories.scope` before
touching a repository, so a client-supplied `facility_id` can only ever narrow a global-read
persona's view or match an operator's own facility (`M15`/`NFR-019`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories import chat_threads as chat_repo
from app.repositories import facilities as facilities_repo
from app.repositories import operations as operations_repo
from app.repositories.scope import assert_facility_visible, resolve_facility_scope_with_user_scopes

# The operations REST surface reports a broken facility mapping as SCOPE_MISSING rather than
# FORBIDDEN, distinguishing "your identity has no facility" from "that is not your facility".
# The assistant-facing services report FORBIDDEN for both; converging them is a client-visible
# change and deliberately out of scope for E2.2.
_UNMAPPED_CODE = "SCOPE_MISSING"


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _scope(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> str | None:
    # Grants-aware since #106 (2026-09-02): a caller may narrow to any facility their
    # user_scopes rows grant, not only the users.facility_id mirror. Costs a query only
    # in the case that was previously a wrong 403 (see repositories/scope.py).
    return await resolve_facility_scope_with_user_scopes(
        session, ctx, facility_id, unmapped_code=_UNMAPPED_CODE
    )


async def get_dashboard_summary(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> dict[str, Any]:
    scope_facility = await _scope(session, ctx, facility_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": {
            "type": "global" if scope_facility is None and ctx.has_global_read_scope else "facility",
            "facility_id": scope_facility,
            "read_only": True,
        },
        "shipments_by_status": await operations_repo.count_shipments_by_status(session, scope_facility),
        "open_exceptions": await operations_repo.count_open_exceptions(session, scope_facility),
        "freshness": "live",
    }


async def list_exceptions(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> dict[str, Any]:
    scope_facility = await _scope(session, ctx, facility_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": {"facility_id": scope_facility, "read_only": True},
        "items": await operations_repo.list_exceptions(session, scope_facility),
        "freshness": "live",
    }


async def get_appointment_schedule(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> dict[str, Any]:
    scope_facility = await _scope(session, ctx, facility_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": {"facility_id": scope_facility, "read_only": True},
        "items": await operations_repo.list_appointment_schedule(session, scope_facility),
        "freshness": "live",
        "label": "displayed_schedule_not_reserved",
    }


async def get_dock_snapshot(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> dict[str, Any]:
    scope_facility = await _scope(session, ctx, facility_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": {"facility_id": scope_facility, "read_only": True},
        "docks": await facilities_repo.list_docks(session, scope_facility),
        "slots": await facilities_repo.list_appointment_slots(session, scope_facility),
        "freshness": "live",
        "note": "Operational snapshot only; not bookable capacity.",
    }


async def get_facility_constraints(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> dict[str, Any]:
    scope_facility = await _scope(session, ctx, facility_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": {"facility_id": scope_facility, "read_only": True},
        "facilities": await facilities_repo.list_facilities(session, scope_facility),
        "rules": await facilities_repo.list_facility_rules(session, scope_facility),
        "freshness": "live",
    }


async def get_thread_messages(
    session: AsyncSession, ctx: ExecutionContext, thread_id: str, *, limit: int = 200
) -> dict[str, Any]:
    """The durable transcript of one chat thread, for the ops console's detail pane (E5.2).

    Found during E5.2's build: **no endpoint let ops read a thread's `chat_messages` at all.**
    `chat.py`'s `/chat/history` is `require_roles(DRIVER)` and reads Redis, not this table, so a
    coordinator deciding whether to take over a conversation had nothing to read it from -- and
    after taking over, no way to see their own posted messages or the driver's replies.

    This is the one read in the product that is `chat_messages`-backed rather than Redis-backed,
    and that is correct for this caller: the console needs the durable, complete, attributable
    record (including `sender_type = 'OPERATIONS'` rows and the takeover dividers), not the
    driver's bounded 24h view.

    Scope is derived from the thread's shipment, never from an argument (`M15`/`NFR-019`). A thread
    with no shipment has no facility to check against and is refused for facility-bound roles
    rather than served unscoped.
    """
    thread = await chat_repo.get_thread_context(session, thread_id)
    if thread is None:
        raise AppError(f"Thread '{thread_id}' not found.", code="NOT_FOUND", status_code=404)
    facility_id = thread.get("facility_id")
    if facility_id is None:
        if not ctx.has_global_read_scope:
            raise AppError("Thread not in scope.", code="FORBIDDEN", status_code=403)
    else:
        assert_facility_visible(ctx, str(facility_id))

    messages = await chat_repo.list_thread_messages(session, thread_id, limit=limit)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "thread_id": thread_id,
        "thread_status": thread["thread_status"],
        "shipment_id": thread["shipment_id"],
        "driver_id": thread["driver_id"],
        "facility_id": facility_id,
        "messages": messages,
        "freshness": "live",
    }
