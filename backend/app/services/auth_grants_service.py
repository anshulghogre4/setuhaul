"""`grants[]` for `GET /api/v1/auth/me` -- GitHub issue #52.

## Sub-issue 1, answered from the schema rather than assumed

Issue #52 asks whether a single `public.users` row ever needs **more than one active role**, or
whether "multi-role" is really "one role, multiple facility/carrier scopes". The schema answers it
outright, and the answer is the second one:

  * `public.users.role_id TEXT NOT NULL` with a single `FOREIGN KEY(role_id) REFERENCES
    roles(role_id)` (`supabase/migrations/20260805201923_setuhaul_baseline.sql`, `CREATE TABLE
    users`). One column, one FK, no join table -- **an account cannot hold two roles.**
  * `public.user_scopes(user_id, scope_type, scope_value)` with `UNIQUE (user_id, scope_type,
    scope_value)` and no per-user cap (`20260823090000_e23_identity_model.sql`). Its own migration
    comment states the intent: *"A user can hold more than one scope row (e.g. a future
    multi-facility FACILITY_MANAGER), so this is a proper child table, not a single nullable
    column on users."*
  * The admin console already provisions that arity: `admin_user_service` writes N `FACILITY`
    rows for the multi-scope roles and mirrors only the first into `users.facility_id`.

So a grant here is **one (role x scope) pair**, never a second role. Nothing in this module invents
multi-role support the database cannot express, and `role_name` is identical on every entry by
construction.

## Derivation rules (M15: scope is derived server-side, never accepted as an argument)

This module takes **no client input at all** -- only the `ExecutionContext` that
`get_execution_context` already resolved from a verified JWT plus the `public.users` row. There is
no facility id, carrier id or role name a caller can supply that reaches these queries.

  1. **DRIVER -> exactly one `DRIVER` grant.** A driver *does* carry a `FACILITY` scope row (E2.3's
     migration backfilled one for every user with a non-NULL `users.facility_id`, drivers
     included), but that row is a backfill artifact, not reach: `ROLE_PERMISSIONS[DRIVER]`
     (`core/deps.py`) is entirely `*_self` / `*_own`, and no driver tool takes a facility scope.
     Rendering "Jaipur" as a driver's grant would state a scope they do not have.
  2. **A carrier-portal role holding a `CARRIER` scope row -> one `CARRIER` grant.** `carrier_id`
     is already resolved by `get_execution_context` from `user_scopes`, and it is the only thing
     that grants carrier reach (issue #101) -- so a `TRANSPORT_MANAGER` *with* a carrier row is the
     carrier persona and gets the carrier grant, while one *without* falls through to rule 3 and
     gets its global facility reach instead.
  3. **Everything else -> one grant per facility in scope**, from `user_scopes(scope_type =
     'FACILITY')` unioned with the `users.facility_id` mirror, sorted by id for a stable order.
  4. **No facility rows and a global-read persona -> one `GLOBAL` grant.** Deliberately not one row
     per facility: E2.3's migration says it directly -- *"global scope is the absence of a facility
     constraint, not a row naming every facility"* -- and `has_global_read_scope`
     (`execution_context.py`) is the exact predicate `resolve_facility_scope` branches on.
  5. **Otherwise -> one `NONE` grant.** The list is never empty, so a consumer can always render an
     identity header without a length check.

## Cost

Zero extra statements for a driver or a carrier (rules 1 and 2 return without touching the
database). Two for a facility/ops persona, and the second is skipped when the first returns
nothing. `/auth/me` is read once per session by the frontend (`core/auth/auth-provider.tsx` keys
the read on the auth subject, not the rotating token), so this is not a hot path -- two readable
statements were preferred over one clever UNION for that reason, not for want of a single query.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.execution_context import CARRIER_PORTAL_ROLES, ExecutionContext, RoleName

# `user_scopes.scope_type` values are constrained to ('FACILITY','CARRIER','DRIVER') by the table's
# own CHECK. `GLOBAL` and `NONE` are NOT scope-row types and never appear in that column -- they
# describe the two cases where a role's reach is expressed by the *absence* of a scope row, which
# is why they are named here and not read from the database.
SCOPE_FACILITY = "FACILITY"
SCOPE_CARRIER = "CARRIER"
SCOPE_DRIVER = "DRIVER"
SCOPE_GLOBAL = "GLOBAL"
SCOPE_NONE = "NONE"


def _grant(
    role_name: RoleName,
    scope_type: str,
    *,
    facility_id: str | None = None,
    facility_name: str | None = None,
    carrier_id: str | None = None,
) -> dict[str, Any]:
    """One grant object. The key set is fixed and identical on every entry.

    A superset of the three fields `frontend/src/core/auth/identity-mapping.ts`'s widening recipe
    asked for (`role_name`, `facility_id`, `carrier_id`): `scope_type` is added so the client never
    has to infer which kind of scope a grant is from which id happens to be non-null, and
    `facility_name` so a facility the frontend has no hardcoded short name for still renders as a
    real name instead of a raw `FAC-...` id.
    """
    return {
        "role_name": role_name.value,
        "scope_type": scope_type,
        "facility_id": facility_id,
        "facility_name": facility_name,
        "carrier_id": carrier_id,
    }


async def _facility_ids_in_scope(session: AsyncSession, ctx: ExecutionContext) -> list[str]:
    """`user_scopes` FACILITY rows unioned with the `users.facility_id` mirror, sorted.

    Both sources are read because they are kept in sync only in one direction:
    `admin_user_service` mirrors the *first* facility into `users.facility_id` while writing every
    one of them to `user_scopes`, and E2.3's backfill went the other way. Reading only `user_scopes`
    would drop a pre-E2.3 account that never got a scope row; reading only the column would drop
    every facility after the first. The union is the only shape that is correct for both.
    """
    rows = (
        await session.execute(
            text(
                "SELECT scope_value FROM public.user_scopes "
                "WHERE user_id = :user_id AND scope_type = 'FACILITY'"
            ),
            {"user_id": ctx.user_id},
        )
    ).scalars().all()

    ids = {str(value) for value in rows if value}
    if ctx.facility_id:
        ids.add(str(ctx.facility_id))
    # Sorted, not insertion-ordered: the role picker renders these as a list a human chooses from,
    # and a list that reorders itself between two sign-ins of the same account is a UI defect.
    return sorted(ids)


async def _facility_names(session: AsyncSession, facility_ids: list[str]) -> dict[str, str]:
    """id -> `facilities.facility_name`, for the ids in scope only.

    `= ANY(:ids)` rather than an IN-list built by string interpolation -- the same bound-array shape
    `admin_user_service._validate_scope` already uses against this table.
    """
    if not facility_ids:
        return {}
    rows = (
        await session.execute(
            text("SELECT facility_id, facility_name FROM public.facilities WHERE facility_id = ANY(:ids)"),
            {"ids": facility_ids},
        )
    ).mappings().all()
    return {str(row["facility_id"]): str(row["facility_name"]) for row in rows}


async def resolve_grants(session: AsyncSession, ctx: ExecutionContext) -> list[dict[str, Any]]:
    """Every (role x scope) pair the authenticated caller holds. Never empty.

    Additive: `/auth/me` keeps returning `role_name`, `facility_id` and `scope` unchanged, which is
    what issue #52's own rollback note requires ("no existing `/auth/me` consumer behaviour changes
    unless a `grants[]` field is added alongside the existing `role_name`").
    """
    role = ctx.role_name

    # Rule 1 -- see the module docstring. Returns before any query.
    if role == RoleName.DRIVER:
        return [_grant(role, SCOPE_DRIVER)]

    # Rule 2. `ctx.carrier_id` is non-None only when a `user_scopes(scope_type='CARRIER')` row
    # exists for this user (`core/deps.py`), so this is a real scope row, not role seniority.
    if role in CARRIER_PORTAL_ROLES and ctx.carrier_id:
        return [_grant(role, SCOPE_CARRIER, carrier_id=ctx.carrier_id)]

    # Rule 3.
    facility_ids = await _facility_ids_in_scope(session, ctx)
    if facility_ids:
        names = await _facility_names(session, facility_ids)
        return [
            _grant(role, SCOPE_FACILITY, facility_id=fid, facility_name=names.get(fid))
            for fid in facility_ids
        ]

    # Rules 4 and 5.
    if ctx.has_global_read_scope:
        return [_grant(role, SCOPE_GLOBAL)]
    return [_grant(role, SCOPE_NONE)]
