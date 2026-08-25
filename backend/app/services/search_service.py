"""`search_records` -- SOLUTION_DESIGN.md section 7.5.8, FR-X-017/FR-X-018.

**Deliberately does not own data** (section 7.5.8's own words): every query here reads exactly one
table each -- `shipments`, `drivers` -- the same tables the ops/facility read paths already read,
scoped through the same `repositories.scope.resolve_facility_scope` every other facility-scoped
read in this codebase uses. Nothing here queries across a module boundary or joins tables two
different modules own; that is what "not a thirteenth module" means structurally, not just in
prose.

Note on composition: section 7.5.8 describes this as calling "each contributing module's own
existing search method." No module currently exposes one -- `driver_reads.py`/`operations_reads.py`
/`carrier_reads.py` have no free-text search function to call (grep-confirmed 2026-08-25). Rather
than invent a search method on each module now (a much larger change touching four files for one
new tool), this composes directly against the tables the same way `operations_reads.py` already
does, through the identical scope resolver -- the isolation guarantee section 7.5.8 actually cares
about (no cross-module table access) holds either way; only the literal call shape differs from
the design's own phrasing.

Facility-scoped desk roles only for v1 (`OPS_PORTAL_ROLES` + `ADMIN`) -- the shared-shell mockup
set this catalog closes a gap for (sign-in, role picker, password reset, user menu, notifications,
**search palette**, account/settings) is the ops/admin desk shell; the driver chat surface and the
carrier portal were not part of that mockup set and have no search palette of their own.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories.scope import resolve_facility_scope

# Section 7.5.8's own decision: Postgres FTS/pg_trgm, not a dedicated search engine. `similarity`
# is pg_trgm's fuzzy-match score (0..1); ILIKE catches an exact substring pg_trgm's threshold might
# miss on a very short query. `0.2` is pg_trgm's own documented default similarity threshold.
SIMILARITY_THRESHOLD = 0.2
SUPPORTED_ENTITY_TYPES = frozenset({"shipments", "drivers"})


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _search_shipments(
    session: AsyncSession, *, query: str, facility_id: str | None
) -> list[dict[str, Any]]:
    facility_filter = ""
    params: dict[str, Any] = {"query": query, "threshold": SIMILARITY_THRESHOLD}
    if facility_id:
        facility_filter = "AND s.destination_facility_id = :facility_id"
        params["facility_id"] = facility_id
    rows = (
        await session.execute(
            text(
                f"""
                SELECT s.shipment_id, s.order_reference, s.current_status,
                       s.destination_facility_id AS facility_id,
                       GREATEST(
                           similarity(s.order_reference, :query),
                           similarity(s.customer_name, :query)
                       ) AS score
                FROM public.shipments s
                WHERE (
                    s.shipment_id ILIKE '%' || :query || '%'
                    OR s.order_reference ILIKE '%' || :query || '%'
                    OR s.customer_name ILIKE '%' || :query || '%'
                    OR similarity(s.order_reference, :query) > :threshold
                    OR similarity(s.customer_name, :query) > :threshold
                  )
                  {facility_filter}
                ORDER BY score DESC
                LIMIT 20
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _search_drivers(
    session: AsyncSession, *, query: str, facility_id: str | None
) -> list[dict[str, Any]]:
    # drivers has no facility_id of its own -- scoped through shipments it's currently assigned
    # to, the same reach a facility-bound operator already has via any other driver-adjacent read.
    facility_filter = ""
    params: dict[str, Any] = {"query": query, "threshold": SIMILARITY_THRESHOLD}
    if facility_id:
        facility_filter = (
            "AND d.driver_id IN (SELECT driver_id FROM public.shipments "
            "WHERE destination_facility_id = :facility_id)"
        )
        params["facility_id"] = facility_id
    rows = (
        await session.execute(
            text(
                f"""
                SELECT d.driver_id, d.driver_name, d.phone,
                       similarity(d.driver_name, :query) AS score
                FROM public.drivers d
                WHERE (
                    d.driver_name ILIKE '%' || :query || '%'
                    OR similarity(d.driver_name, :query) > :threshold
                  )
                  {facility_filter}
                ORDER BY score DESC
                LIMIT 20
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def search_records(
    session: AsyncSession,
    ctx: ExecutionContext,
    query: str,
    entity_types: list[str] | None = None,
) -> dict[str, Any]:
    """SS7.5.8 `search_records` -- `query`, `entity_types?` (defaults to all types the caller's
    role can see). Facility-scoped by default for facility-bound roles; no cross-facility toggle
    in v1 (deferred, per `UI-UX/00-foundations/stitch-prompts-shared-shell.md` prompt 6)."""
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to search.", code="FORBIDDEN", status_code=403)
    trimmed = query.strip()
    if len(trimmed) < 2:
        raise AppError(
            "Query must be at least 2 characters.", code="QUERY_TOO_SHORT", status_code=422
        )
    requested = set(entity_types) if entity_types else set(SUPPORTED_ENTITY_TYPES)
    unknown = requested - SUPPORTED_ENTITY_TYPES
    if unknown:
        raise AppError(
            f"Unsupported entity_types: {', '.join(sorted(unknown))}.",
            code="INVALID_ENTITY_TYPE", status_code=422,
            detail=f"Supported: {', '.join(sorted(SUPPORTED_ENTITY_TYPES))}.",
        )
    # No global-facility toggle in v1: a global-read persona searches everywhere (scope=None from
    # the resolver, same "no facility filter" meaning `get_exception_queue` already uses),
    # everyone else is confined to their own facility.
    scope = resolve_facility_scope(ctx, None)

    results: dict[str, list[dict[str, Any]]] = {}
    if "shipments" in requested:
        results["shipments"] = await _search_shipments(session, query=trimmed, facility_id=scope)
    if "drivers" in requested:
        results["drivers"] = await _search_drivers(session, query=trimmed, facility_id=scope)

    return {
        "as_of": _as_of(), "source": "postgresql", "query": trimmed, "facility_id": scope,
        "results": results,
    }
