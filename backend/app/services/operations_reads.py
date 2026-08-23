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

from app.core.execution_context import ExecutionContext
from app.repositories import facilities as facilities_repo
from app.repositories import operations as operations_repo
from app.repositories.scope import resolve_facility_scope

# The operations REST surface reports a broken facility mapping as SCOPE_MISSING rather than
# FORBIDDEN, distinguishing "your identity has no facility" from "that is not your facility".
# The assistant-facing services report FORBIDDEN for both; converging them is a client-visible
# change and deliberately out of scope for E2.2.
_UNMAPPED_CODE = "SCOPE_MISSING"


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope(ctx: ExecutionContext, facility_id: str | None) -> str | None:
    return resolve_facility_scope(ctx, facility_id, unmapped_code=_UNMAPPED_CODE)


async def get_dashboard_summary(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> dict[str, Any]:
    scope_facility = _scope(ctx, facility_id)
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
    scope_facility = _scope(ctx, facility_id)
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
    scope_facility = _scope(ctx, facility_id)
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
    scope_facility = _scope(ctx, facility_id)
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
    scope_facility = _scope(ctx, facility_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": {"facility_id": scope_facility, "read_only": True},
        "facilities": await facilities_repo.list_facilities(session, scope_facility),
        "rules": await facilities_repo.list_facility_rules(session, scope_facility),
        "freshness": "live",
    }
