"""Admin console -- user/role tools. SOLUTION_DESIGN.md section 7.5.7, FR-ADM-001 .. FR-ADM-005.

Scope is a role-assignment write (M15): `invite_user` sets role and scope **in the same call**,
never a two-step create-then-scope sequence -- section 7.5.7's own stated reason is "closes the
exact gap window M15's foundational-architecture framing exists to prevent" (a user briefly
existing with a role but no scope, or vice versa, is a real authorization gap, not a UX nicety).

`invite_user`/`remove_user` are the only writes in this whole backend that create or delete a real
Supabase Auth login identity -- everything else in this codebase only ever reads the identity
Supabase Auth already resolved. Both therefore need the **service-role key**, not the anon key
E3.5's account tools used: creating/deleting another person's login is an admin operation on
someone else's identity, unlike `sign_out_everywhere`'s self-service shape.

`users.password_hash` is legacy (pre-Supabase-Auth-migration schema; the real credential lives in
`auth.users`, this backend never sees it) -- set to a clear sentinel, the same pattern the M8
sweeper service account already established for "this column exists but nothing reads it as a real
credential."

**Scope is stored in two places on purpose (A-G4, issue #72).** `public.user_scopes` is the
authoritative multi-valued record -- its own migration
(`supabase/migrations/20260823090000_e23_identity_model.sql`) names "a future multi-facility
FACILITY_MANAGER" as the exact reason it is a child table rather than a column -- and
`users.facility_id`/`users.driver_id` are kept in sync with its *first* value as the single-valued
"primary" mirror. That mirror is not redundancy for its own sake: E2.3's migration deliberately
added `user_scopes` *alongside* `users.facility_id` rather than instead of it, because E2.2's
consolidation of the four independent scope-check call sites onto `user_scopes` has not happened
yet, and every one of those call sites still reads `users.facility_id`. Writing only `user_scopes`
here would leave a newly-invited multi-facility user with no scope at all as far as the live
enforcement paths are concerned.

**M15 note**: the `scope` argument *is* a client-supplied id, and that is correct here rather than a
violation -- assigning another user's scope is this tool's entire purpose. What is never taken from
the client is the *caller's own* authority (`ctx.is_admin`, derived from the verified token) or the
existence of the scope target: every facility/driver id is re-validated against its own table
server-side before any write.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings
from app.core.tls import use_system_trust_store
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

PASSWORD_HASH_SENTINEL = "MANAGED_BY_SUPABASE_AUTH"

# Role -> what kind of scope id it takes (SS7.5.7: "scope (facility/carrier/driver id, matching
# role)"). `None` means global -- no scope id accepted or required.
FACILITY_SCOPED_ROLES = frozenset(
    {
        RoleName.OPERATIONS_EXECUTIVE, RoleName.WAREHOUSE_PLANNER,
        RoleName.OPERATIONS_MANAGER, RoleName.FACILITY_MANAGER,
    }
)
GLOBAL_ROLES = frozenset({RoleName.ADMIN, RoleName.TRANSPORT_MANAGER, RoleName.REGIONAL_OPERATIONS_HEAD})

# A-G8 (issue #76): the two terminal escalation statuses, per
# `supabase/migrations/20260823100000_e24_escalation_vocabulary.sql`'s CHECK constraint
# (OPEN / ACKNOWLEDGED / IN_PROGRESS / RESOLVED / CANCELLED). Expressed as "not terminal" rather
# than an allow-list of active values so that adding a sixth, pre-terminal status later cannot
# silently make an owned escalation stop counting.
TERMINAL_ESCALATION_STATUSES = ("RESOLVED", "CANCELLED")

# The three `user_scopes.scope_type` values this console owns -- matching the live CHECK
# constraint. A role change rewrites all three, so a user moved from OPERATIONS_EXECUTIVE to
# DRIVER cannot keep a stale FACILITY row behind.
MANAGED_SCOPE_TYPES = ("FACILITY", "CARRIER", "DRIVER")


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_scope(scope: str | list[str] | None) -> list[str]:
    """Accept `scope` as one id or many, always returning a de-duplicated list (A-G4, issue #72).

    SS7.5.7's argument column reads "scope (facility/carrier/driver id, matching `role`)" --
    singular -- but three of this surface's own design files require more than one:
    `06-admin-console/flows-and-states.md` Flow 1 step 2 specifies a "facility multi-select for
    ops/planner/gate", `screens.md` section 2's first example row is a user scoped to two facilities
    ("Neha B. - Ops - Jaipur, Gurugram"), and `user_scopes`' migration comment names multi-facility
    as the reason the table exists. A bare string stays accepted so every existing single-facility
    caller keeps working unchanged.

    De-duplication is not cosmetic: `user_scopes` carries UNIQUE (user_id, scope_type, scope_value),
    so a form that submits the same facility twice would otherwise fail the insert outright.
    """
    if scope is None:
        return []
    values = [scope] if isinstance(scope, str) else list(scope)
    cleaned: list[str] = []
    for value in values:
        trimmed = str(value).strip()
        if trimmed and trimmed not in cleaned:
            cleaned.append(trimmed)
    return cleaned


def _auth_headers(settings: Settings) -> dict[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise AppError(
            "Supabase Auth admin API is not configured.", code="AUTH_ADMIN_MISCONFIGURED",
            status_code=503,
        )
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


async def _create_auth_user(settings: Settings, email: str) -> str:
    """`POST /auth/v1/invite` -- creates the Supabase Auth identity and sends the invite email in
    one call, returning its `id` (the `auth_user_id` this backend's `users` row points at)."""
    use_system_trust_store()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/invite",
                json={"email": email},
                headers=_auth_headers(settings),
            )
    except httpx.HTTPError as exc:
        raise AppError("Unable to reach Supabase Auth.", code="AUTH_UNAVAILABLE", status_code=503) from exc
    if response.status_code >= 400:
        raise AppError(
            "Supabase Auth refused to create the account.", code="AUTH_INVITE_FAILED",
            status_code=502, detail=response.text[:300],
        )
    auth_user_id = response.json().get("id")
    if not auth_user_id:
        raise AppError("Supabase Auth did not return a user id.", code="AUTH_INVITE_FAILED", status_code=502)
    return str(auth_user_id)


async def _delete_auth_user(settings: Settings, auth_user_id: str) -> None:
    use_system_trust_store()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{auth_user_id}",
                headers=_auth_headers(settings),
            )
    except httpx.HTTPError as exc:
        raise AppError("Unable to reach Supabase Auth.", code="AUTH_UNAVAILABLE", status_code=503) from exc
    # A 404 here means the auth identity is already gone -- treated as success, not a failure,
    # since the end state (no login exists) is what remove_user actually promises.
    if response.status_code >= 400 and response.status_code != 404:
        raise AppError(
            "Supabase Auth refused to delete the account.", code="AUTH_DELETE_FAILED",
            status_code=502, detail=response.text[:300],
        )


async def _resolve_role_id(session: AsyncSession, role_name: str) -> str:
    row = (
        await session.execute(
            text("SELECT role_id FROM public.roles WHERE role_name = :role_name"),
            {"role_name": role_name},
        )
    ).mappings().first()
    if row is None:
        raise AppError(f"Unknown role '{role_name}'.", code="INVALID_ROLE", status_code=422)
    return str(row["role_id"])


def _scope_type_for(role: RoleName) -> str | None:
    """Which `user_scopes.scope_type` a role takes, or None for a globally-scoped role."""
    if role in GLOBAL_ROLES:
        return None
    if role in FACILITY_SCOPED_ROLES:
        return "FACILITY"
    if role == RoleName.DRIVER:
        return "DRIVER"
    if role == RoleName.CARRIER:
        return "CARRIER"
    raise AppError(f"Unknown role '{role}'.", code="INVALID_ROLE", status_code=422)


async def _validate_scope(session: AsyncSession, role: RoleName, scopes: list[str]) -> None:
    """Raises if `scopes` don't match what `role` requires, or don't point at real rows.

    Only FACILITY roles are multi-valued: a DRIVER user *is* one driver and a CARRIER user belongs
    to one carrier, so more than one id there is a caller error, not a wider grant -- refused by
    name (`SCOPE_NOT_MULTI_VALUED`) rather than silently truncated to the first entry.
    """
    scope_type = _scope_type_for(role)
    if scope_type is None:
        return
    if not scopes:
        raise AppError(
            f"{role.value} role requires a {scope_type.lower()} scope.",
            code="SCOPE_REQUIRED", status_code=422,
        )
    if scope_type != "FACILITY" and len(scopes) > 1:
        raise AppError(
            f"{role.value} role takes exactly one {scope_type.lower()} scope, not {len(scopes)}.",
            code="SCOPE_NOT_MULTI_VALUED", status_code=422,
        )
    if scope_type == "DRIVER":
        exists = (
            await session.execute(
                text("SELECT driver_id FROM public.drivers WHERE driver_id = :id"), {"id": scopes[0]}
            )
        ).mappings().first()
        if exists is None:
            raise AppError(f"Driver '{scopes[0]}' does not exist.", code="INVALID_SCOPE", status_code=422)
        return
    if scope_type == "FACILITY":
        # One round trip for the whole multi-select, not one per facility -- and it names every
        # missing id at once, so a form with two bad entries doesn't have to be resubmitted twice.
        found = (
            await session.execute(
                text("SELECT facility_id FROM public.facilities WHERE facility_id = ANY(:ids)"),
                {"ids": scopes},
            )
        ).scalars().all()
        known = {str(value) for value in found}
        missing = [value for value in scopes if value not in known]
        if missing:
            raise AppError(
                f"Facility '{missing[0]}' does not exist." if len(missing) == 1
                else f"These facilities do not exist: {', '.join(missing)}.",
                code="INVALID_SCOPE", status_code=422,
            )
        return
    # CARRIER: no `carriers` table exists in this schema (carrier identity rides on
    # shipments.carrier_id), so there is nothing to check existence against -- unchanged from the
    # pre-#72 behaviour, stated rather than silently inherited.
    return


async def _write_user_scopes(
    session: AsyncSession, *, user_id: str, role: RoleName, scopes: list[str], now: datetime
) -> None:
    """Replace this user's managed scope rows with exactly `scopes`.

    Always deletes all three managed types before inserting, so a role change (ops -> driver, or
    facility-scoped -> global) can never leave a stale row behind that a future E2.2-consolidated
    scope check would still honour. A globally-scoped role therefore ends with zero rows, which is
    what E2.3's own backfill comment calls the correct representation of global reach ("global
    scope is the absence of a facility constraint, not a row naming every facility").
    """
    await session.execute(
        text("DELETE FROM public.user_scopes WHERE user_id = :uid AND scope_type = ANY(:types)"),
        {"uid": user_id, "types": list(MANAGED_SCOPE_TYPES)},
    )
    scope_type = _scope_type_for(role)
    if scope_type is None or not scopes:
        return
    # One INSERT for the whole multi-select rather than a loop of round trips; ids are generated
    # here rather than in SQL so `new_id` stays the single source of the id format.
    await session.execute(
        text(
            """
            INSERT INTO public.user_scopes (scope_id, user_id, scope_type, scope_value, created_at)
            SELECT s.scope_id, :uid, :stype, s.scope_value, :created_at
            FROM unnest(CAST(:scope_ids AS text[]), CAST(:scope_values AS text[]))
                 AS s(scope_id, scope_value)
            ON CONFLICT (user_id, scope_type, scope_value) DO NOTHING
            """
        ),
        {
            "uid": user_id, "stype": scope_type, "created_at": now,
            "scope_ids": [new_id("SCP") for _ in scopes], "scope_values": scopes,
        },
    )


async def list_users(
    session: AsyncSession, ctx: ExecutionContext, role_filter: str | None = None, facility_filter: str | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `list_users` -- `role_filter?`, `facility_filter?`.

    Returns `scoped_facility_ids` per row (A-G4, issue #72): `screens.md` section 2's Scope column
    renders a list ("Jaipur, Gurugram"), which the single `users.facility_id` column cannot
    express. `account_service.get_account_profile` already reads the same `user_scopes` rows for
    the signed-in user's own profile -- this is that read, applied to the list.

    `facility_filter` matches on **either** side of the mirror described in the module docstring:
    a user scoped to Jaipur and Gurugram whose primary `users.facility_id` is Jaipur must still
    appear under a Gurugram filter, which a plain `u.facility_id = :facility_filter` misses.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    filters = ""
    params: dict[str, Any] = {}
    if role_filter:
        filters += " AND r.role_name = :role_filter"
        params["role_filter"] = role_filter.upper()
    if facility_filter:
        filters += (
            " AND (u.facility_id = :facility_filter OR EXISTS ("
            "SELECT 1 FROM public.user_scopes fs WHERE fs.user_id = u.user_id"
            " AND fs.scope_type = 'FACILITY' AND fs.scope_value = :facility_filter))"
        )
        params["facility_filter"] = facility_filter
    rows = (
        await session.execute(
            text(
                f"""
                SELECT u.user_id, u.full_name, u.email, r.role_name, u.facility_id, u.driver_id,
                       u.is_active, u.last_login_ts,
                       COALESCE((
                         SELECT array_agg(us.scope_value ORDER BY us.scope_value)
                         FROM public.user_scopes us
                         WHERE us.user_id = u.user_id AND us.scope_type = 'FACILITY'
                       ), ARRAY[]::text[]) AS scoped_facility_ids
                FROM public.users u
                JOIN public.roles r ON r.role_id = u.role_id
                WHERE 1=1 {filters}
                ORDER BY u.full_name
                LIMIT 200
                """
            ),
            params,
        )
    ).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        # A user invited before #72 (or one whose row predates E2.3's backfill) has no
        # `user_scopes` row at all; fall back to the primary mirror rather than rendering an empty
        # Scope cell for a user who genuinely has one facility.
        if not item.get("scoped_facility_ids") and item.get("facility_id"):
            item["scoped_facility_ids"] = [item["facility_id"]]
        else:
            item["scoped_facility_ids"] = list(item.get("scoped_facility_ids") or [])
        items.append(item)
    return {"as_of": _as_of(), "source": "postgresql", "items": items}


async def invite_user(
    session: AsyncSession, ctx: ExecutionContext, settings: Settings,
    *, email: str, role: str, scope: str | list[str] | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `invite_user` -- `email`, `role`, `scope` (one id or many, matching `role`).

    Role and scope are set in the same local write that follows the Supabase Auth call, never a
    two-step "create then scope" sequence -- the whole point section 7.5.7 states. The Auth-side
    invite happens first and is **not itself rolled back** on a later local failure (Supabase Auth
    has no transactional join with this Postgres database); a partial failure here is a real,
    if narrow, forward-fix case (an auth identity with no local `users` row), not a silent gap --
    flagged in the exception detail so an admin retrying `invite_user` with the same email sees
    what actually happened rather than a generic 500.

    Since #72 the scope write covers **every** scoped role, not just CARRIER: a driver invited here
    previously got no `user_scopes` row at all, while every driver E2.3's migration backfilled has
    one -- an inconsistency inside the same table, not merely a missing feature.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    try:
        role_enum = RoleName(role.upper())
    except ValueError as exc:
        raise AppError(f"Unknown role '{role}'.", code="INVALID_ROLE", status_code=422) from exc
    scopes = normalize_scope(scope)
    await _validate_scope(session, role_enum, scopes)
    role_id = await _resolve_role_id(session, role_enum.value)

    auth_user_id = await _create_auth_user(settings, email)

    # The single-valued mirror: first entry wins, and it is the one every not-yet-consolidated
    # scope-check call site still reads (module docstring).
    facility_id = scopes[0] if role_enum in FACILITY_SCOPED_ROLES and scopes else None
    driver_id = scopes[0] if role_enum == RoleName.DRIVER and scopes else None
    user_id = new_id("USR")
    now = datetime.now(timezone.utc).isoformat()
    try:
        await session.execute(
            text(
                """
                INSERT INTO public.users (
                  user_id, role_id, full_name, email, password_hash, driver_id, facility_id,
                  is_active, created_at, auth_user_id
                ) VALUES (
                  :user_id, :role_id, :full_name, :email, :password_hash, :driver_id, :facility_id,
                  1, :created_at, CAST(:auth_user_id AS uuid)
                )
                """
            ),
            {
                "user_id": user_id, "role_id": role_id, "full_name": email.split("@")[0],
                "email": email, "password_hash": PASSWORD_HASH_SENTINEL, "driver_id": driver_id,
                "facility_id": facility_id, "created_at": now, "auth_user_id": auth_user_id,
            },
        )
        await _write_user_scopes(
            session, user_id=user_id, role=role_enum, scopes=scopes, now=datetime.now(timezone.utc)
        )
    except Exception as exc:
        raise AppError(
            "Auth account created but the local user record failed -- retry or contact an "
            "administrator to reconcile the orphaned Supabase Auth identity.",
            code="INVITE_PARTIALLY_FAILED", status_code=500, detail=f"auth_user_id={auth_user_id}",
        ) from exc

    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id, old_value_json,
              new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :actor_id, 'CREATE', 'users', :entity_id, NULL, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "actor_id": ctx.user_id, "entity_id": user_id,
            # FR-ADM-009: the audit row records the scope that was granted, not just the role --
            # "who could see what, from when" is unanswerable from a role name alone once scope is
            # multi-valued. json.dumps, not an f-string, so an id containing a quote can't corrupt
            # the stored JSON.
            "new_value_json": json.dumps(
                {"event": "INVITE_USER", "email": email, "role": role_enum.value, "scope": scopes}
            ),
            "created_at": now,
        },
    )
    await session.commit()
    return {
        "as_of": _as_of(), "code": "INVITED", "user_id": user_id, "email": email,
        "role": role_enum.value, "scope_values": scopes,
    }


async def update_user(
    session: AsyncSession, ctx: ExecutionContext,
    *, user_id: str, role: str | None = None, scope: str | list[str] | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `update_user` -- `user_id`, `role?`, `scope?`. Local-only: role/scope changes do
    not touch the Supabase Auth identity, which has no concept of this system's roles.

    **A scope-only edit is now a real edit (A-G4, issue #72).** Before, `scope` was silently
    ignored whenever `role` was absent, so `update_user(user_id, scope=[JAI, GGN])` returned
    `UPDATED` having changed nothing -- and adding a second facility to a user whose role is not
    changing is precisely the common case `flows-and-states.md` Flow 2 describes. When `role` is
    absent the role is re-read **from the database**, never inferred from the caller's payload, so
    the scope is validated against the role the user actually holds.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    existing = (
        await session.execute(
            text(
                "SELECT u.user_id, r.role_name FROM public.users u "
                "JOIN public.roles r ON r.role_id = u.role_id WHERE u.user_id = :uid"
            ),
            {"uid": user_id},
        )
    ).mappings().first()
    if existing is None:
        raise AppError(f"User '{user_id}' not found.", code="NOT_FOUND", status_code=404)

    scopes = normalize_scope(scope)
    effective_role: RoleName | None = None
    if role is not None:
        try:
            effective_role = RoleName(role.upper())
        except ValueError as exc:
            raise AppError(f"Unknown role '{role}'.", code="INVALID_ROLE", status_code=422) from exc
    elif scope is not None:
        try:
            effective_role = RoleName(str(existing["role_name"]).upper())
        except ValueError as exc:
            raise AppError(
                f"User '{user_id}' holds role '{existing['role_name']}', which this console cannot scope.",
                code="INVALID_ROLE", status_code=422,
            ) from exc

    role_id: str | None = None
    facility_id: str | None = None
    driver_id: str | None = None
    if effective_role is not None:
        await _validate_scope(session, effective_role, scopes)
        facility_id = scopes[0] if effective_role in FACILITY_SCOPED_ROLES and scopes else None
        driver_id = scopes[0] if effective_role == RoleName.DRIVER and scopes else None
    if role is not None:
        role_id = await _resolve_role_id(session, effective_role.value)

    # `scope_write` is true for a role change *or* a scope-only change; both rewrite the mirror
    # columns, and a role change to a global role correctly clears them.
    scope_write = effective_role is not None
    await session.execute(
        text(
            """
            UPDATE public.users
            SET role_id = COALESCE(:role_id, role_id),
                facility_id = CASE WHEN :scope_write THEN :facility_id ELSE facility_id END,
                driver_id = CASE WHEN :scope_write THEN :driver_id ELSE driver_id END,
                updated_at = :updated_at
            WHERE user_id = :user_id
            """
        ),
        {
            "role_id": role_id, "scope_write": scope_write, "facility_id": facility_id,
            "driver_id": driver_id, "updated_at": datetime.now(timezone.utc).isoformat(), "user_id": user_id,
        },
    )
    if scope_write:
        await _write_user_scopes(
            session, user_id=user_id, role=effective_role, scopes=scopes,
            now=datetime.now(timezone.utc),
        )
    await session.commit()
    return {
        "as_of": _as_of(), "code": "UPDATED", "user_id": user_id,
        "role": effective_role.value if effective_role is not None else None,
        "scope_values": scopes,
    }


async def _set_active(session: AsyncSession, ctx: ExecutionContext, user_id: str, active: bool) -> dict[str, Any]:
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    row = (
        await session.execute(
            text(
                "UPDATE public.users SET is_active = :active, updated_at = :updated_at "
                "WHERE user_id = :user_id RETURNING user_id, is_active"
            ),
            {"active": 1 if active else 0, "updated_at": datetime.now(timezone.utc).isoformat(), "user_id": user_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError(f"User '{user_id}' not found.", code="NOT_FOUND", status_code=404)
    await session.commit()
    return {"as_of": _as_of(), "code": "REACTIVATED" if active else "DEACTIVATED", "user_id": user_id}


async def deactivate_user(session: AsyncSession, ctx: ExecutionContext, user_id: str) -> dict[str, Any]:
    """SS7.5.7 `deactivate_user` -- reversible, distinct from `remove_user`."""
    return await _set_active(session, ctx, user_id, active=False)


async def reactivate_user(session: AsyncSession, ctx: ExecutionContext, user_id: str) -> dict[str, Any]:
    """SS7.5.7 `reactivate_user` -- reverses `deactivate_user`."""
    return await _set_active(session, ctx, user_id, active=True)


async def get_user_removal_impact(
    session: AsyncSession, ctx: ExecutionContext, *, user_id: str
) -> dict[str, Any]:
    """The read behind `edge-cases.md` #1's locked confirmation copy -- "This user owns 2 active
    escalations - they will show as unowned once removed" (A-G8, issue #76).

    That sentence has to be renderable **before** the admin confirms, and `remove_user` itself is
    the wrong place to produce it: by the time it returns, the removal has already happened. This is
    a pure read, deliberately shaped like `planner_service.get_dock_block_impact` -- the same
    "confirmation dialog needs a count before the write" problem, already solved once in this
    codebase, so it is solved the same way here rather than a second way.

    **Not in section 7.5.7's own catalog**: flagged as an addition rather than silently folded in,
    the same discipline `get_dock_block_impact`'s docstring uses. `remove_user` re-counts inside its
    own transaction and never trusts this result -- this is advisory copy, not a gate.

    "Owns" means `escalation_queue.owner_user_id`, the column E3.2's migration added for exactly
    this ownership concept. An OPEN escalation has no owner (an owner is set at
    `acknowledge_escalation`), so it correctly contributes nothing to this count.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    user = (
        await session.execute(
            text("SELECT user_id, full_name, email, is_active FROM public.users WHERE user_id = :uid"),
            {"uid": user_id},
        )
    ).mappings().first()
    if user is None:
        raise AppError(f"User '{user_id}' not found.", code="NOT_FOUND", status_code=404)

    owned = (
        await session.execute(
            text(
                """
                SELECT escalation_id, shipment_id, facility_id, escalation_status, severity_code,
                       CAST(count(*) OVER () AS integer) AS total_count
                FROM public.escalation_queue
                WHERE owner_user_id = :uid AND escalation_status <> ALL(:terminal)
                ORDER BY created_at
                LIMIT 50
                """
            ),
            {"uid": user_id, "terminal": list(TERMINAL_ESCALATION_STATUSES)},
        )
    ).mappings().all()

    # The window count is evaluated before LIMIT, so the headline number in the confirmation copy
    # stays true even when the sample list below is truncated.
    total = int(owned[0]["total_count"]) if owned else 0

    return {
        "as_of": _as_of(), "source": "postgresql", "user_id": user_id,
        "full_name": user["full_name"], "email": user["email"],
        "active_escalation_count": total,
        "active_escalations": [
            {k: v for k, v in dict(row).items() if k != "total_count"} for row in owned
        ],
        # Flow 4: Remove is Hidden, not Disabled, on the signed-in admin's own account. The server
        # states the fact; the client does not have to compare ids itself to discover it.
        "is_self": user_id == ctx.user_id,
    }


async def remove_user(
    session: AsyncSession, ctx: ExecutionContext, settings: Settings, *, user_id: str, idempotency_key: str,
) -> dict[str, Any]:
    """SS7.5.7 `remove_user` -- `user_id`, `Idempotency-Key`. Permanent; High-tier destructive
    action (`components.md` section 19). Deletes the Supabase Auth identity (so the account can
    never log in again) and locally **deactivates rather than hard-deletes** the `users` row --
    `audit_logs`/`escalation_queue.resolved_by_user_id` and similar FKs reference `users.user_id`,
    so a hard delete would either cascade-destroy audit history or fail outright. `REMOVED` still
    means "this person cannot use the system again," which is what the design promises; it does
    not mean the row is gone.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    key = (idempotency_key or "").strip()
    if not key:
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)

    route = f"POST /api/v1/admin/users/{user_id}/remove"
    req_hash = payload_hash({"user_id": user_id})
    replay = await lookup_idempotency(session, key=key, user_id=ctx.user_id, route=route, request_hash=req_hash)
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    # A-G8 (issue #76): the owned-escalation count is re-computed here, inside the transaction that
    # actually removes the user, not carried over from `get_user_removal_impact`'s preview -- the
    # same "never trust the preview" discipline `block_dock` uses against `get_dock_block_impact`.
    # A correlated subquery rather than a second round trip: this read already exists.
    row = (
        await session.execute(
            text(
                """
                SELECT u.user_id, u.auth_user_id,
                       CAST((
                         SELECT count(*) FROM public.escalation_queue e
                         WHERE e.owner_user_id = u.user_id
                           AND e.escalation_status <> ALL(:terminal)
                       ) AS integer) AS active_escalation_count
                FROM public.users u
                WHERE u.user_id = :uid
                """
            ),
            {"uid": user_id, "terminal": list(TERMINAL_ESCALATION_STATUSES)},
        )
    ).mappings().first()
    if row is None:
        raise AppError(f"User '{user_id}' not found.", code="NOT_FOUND", status_code=404)
    orphaned_escalations = int(row["active_escalation_count"] or 0)

    if row["auth_user_id"]:
        await _delete_auth_user(settings, str(row["auth_user_id"]))

    now = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text("UPDATE public.users SET is_active = 0, updated_at = :updated_at WHERE user_id = :uid"),
        {"updated_at": now, "uid": user_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id, old_value_json,
              new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :actor_id, 'DELETE', 'users', :entity_id, NULL, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "actor_id": ctx.user_id, "entity_id": user_id,
            # Records how much work this removal orphaned, so "why did N escalations go unowned
            # last Tuesday" is answerable from the audit log alone (FR-ADM-009).
            "new_value_json": json.dumps(
                {"event": "REMOVE_USER", "orphaned_active_escalations": orphaned_escalations}
            ),
            "created_at": now,
        },
    )
    result = {
        "as_of": _as_of(), "code": "REMOVED", "user_id": user_id,
        "active_escalation_count": orphaned_escalations,
    }
    await store_idempotency(session, key=key, user_id=ctx.user_id, route=route, request_hash=req_hash, response=result)
    await session.commit()
    return result
