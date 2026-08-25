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
"""

from __future__ import annotations

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


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


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


async def _validate_scope(session: AsyncSession, role: RoleName, scope: str | None) -> None:
    """Raises if `scope` doesn't match what `role` requires, or points at a real row."""
    if role in GLOBAL_ROLES:
        return
    if role == RoleName.DRIVER:
        if not scope:
            raise AppError("DRIVER role requires a driver_id scope.", code="SCOPE_REQUIRED", status_code=422)
        exists = (
            await session.execute(text("SELECT driver_id FROM public.drivers WHERE driver_id = :id"), {"id": scope})
        ).mappings().first()
        if exists is None:
            raise AppError(f"Driver '{scope}' does not exist.", code="INVALID_SCOPE", status_code=422)
        return
    if role in FACILITY_SCOPED_ROLES:
        if not scope:
            raise AppError(f"{role} role requires a facility_id scope.", code="SCOPE_REQUIRED", status_code=422)
        exists = (
            await session.execute(text("SELECT facility_id FROM public.facilities WHERE facility_id = :id"), {"id": scope})
        ).mappings().first()
        if exists is None:
            raise AppError(f"Facility '{scope}' does not exist.", code="INVALID_SCOPE", status_code=422)
        return
    if role == RoleName.CARRIER:
        if not scope:
            raise AppError("CARRIER role requires a carrier_id scope.", code="SCOPE_REQUIRED", status_code=422)
        return
    raise AppError(f"Unknown role '{role}'.", code="INVALID_ROLE", status_code=422)


async def list_users(
    session: AsyncSession, ctx: ExecutionContext, role_filter: str | None = None, facility_filter: str | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `list_users` -- `role_filter?`, `facility_filter?`."""
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    filters = ""
    params: dict[str, Any] = {}
    if role_filter:
        filters += " AND r.role_name = :role_filter"
        params["role_filter"] = role_filter.upper()
    if facility_filter:
        filters += " AND u.facility_id = :facility_filter"
        params["facility_filter"] = facility_filter
    rows = (
        await session.execute(
            text(
                f"""
                SELECT u.user_id, u.full_name, u.email, r.role_name, u.facility_id, u.driver_id,
                       u.is_active, u.last_login_ts
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
    return {"as_of": _as_of(), "source": "postgresql", "items": [dict(r) for r in rows]}


async def invite_user(
    session: AsyncSession, ctx: ExecutionContext, settings: Settings,
    *, email: str, role: str, scope: str | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `invite_user` -- `email`, `role`, `scope` (matching `role`).

    Role and scope are set in the same local write that follows the Supabase Auth call, never a
    two-step "create then scope" sequence -- the whole point section 7.5.7 states. The Auth-side
    invite happens first and is **not itself rolled back** on a later local failure (Supabase Auth
    has no transactional join with this Postgres database); a partial failure here is a real,
    if narrow, forward-fix case (an auth identity with no local `users` row), not a silent gap --
    flagged in the exception detail so an admin retrying `invite_user` with the same email sees
    what actually happened rather than a generic 500.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    try:
        role_enum = RoleName(role.upper())
    except ValueError as exc:
        raise AppError(f"Unknown role '{role}'.", code="INVALID_ROLE", status_code=422) from exc
    await _validate_scope(session, role_enum, scope)
    role_id = await _resolve_role_id(session, role_enum.value)

    auth_user_id = await _create_auth_user(settings, email)

    facility_id = scope if role_enum in FACILITY_SCOPED_ROLES else None
    driver_id = scope if role_enum == RoleName.DRIVER else None
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
        if role_enum == RoleName.CARRIER:
            await session.execute(
                text(
                    "INSERT INTO public.user_scopes (scope_id, user_id, scope_type, scope_value, created_at) "
                    "VALUES (:scope_id, :user_id, 'CARRIER', :carrier_id, :created_at)"
                ),
                {"scope_id": new_id("SCP"), "user_id": user_id, "carrier_id": scope, "created_at": datetime.now(timezone.utc)},
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
            "new_value_json": f'{{"event": "INVITE_USER", "email": "{email}", "role": "{role_enum.value}"}}',
            "created_at": now,
        },
    )
    await session.commit()
    return {"as_of": _as_of(), "code": "INVITED", "user_id": user_id, "email": email, "role": role_enum.value}


async def update_user(
    session: AsyncSession, ctx: ExecutionContext,
    *, user_id: str, role: str | None = None, scope: str | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `update_user` -- `user_id`, `role?`, `scope?`. Local-only: role/scope changes do
    not touch the Supabase Auth identity, which has no concept of this system's roles."""
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    existing = (
        await session.execute(text("SELECT user_id FROM public.users WHERE user_id = :uid"), {"uid": user_id})
    ).mappings().first()
    if existing is None:
        raise AppError(f"User '{user_id}' not found.", code="NOT_FOUND", status_code=404)

    role_id: str | None = None
    facility_id: str | None = None
    driver_id: str | None = None
    if role is not None:
        try:
            role_enum = RoleName(role.upper())
        except ValueError as exc:
            raise AppError(f"Unknown role '{role}'.", code="INVALID_ROLE", status_code=422) from exc
        await _validate_scope(session, role_enum, scope)
        role_id = await _resolve_role_id(session, role_enum.value)
        facility_id = scope if role_enum in FACILITY_SCOPED_ROLES else None
        driver_id = scope if role_enum == RoleName.DRIVER else None

    await session.execute(
        text(
            """
            UPDATE public.users
            SET role_id = COALESCE(:role_id, role_id),
                facility_id = CASE WHEN :role_provided THEN :facility_id ELSE facility_id END,
                driver_id = CASE WHEN :role_provided THEN :driver_id ELSE driver_id END,
                updated_at = :updated_at
            WHERE user_id = :user_id
            """
        ),
        {
            "role_id": role_id, "role_provided": role is not None, "facility_id": facility_id,
            "driver_id": driver_id, "updated_at": datetime.now(timezone.utc).isoformat(), "user_id": user_id,
        },
    )
    await session.commit()
    return {"as_of": _as_of(), "code": "UPDATED", "user_id": user_id}


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

    row = (
        await session.execute(
            text("SELECT user_id, auth_user_id FROM public.users WHERE user_id = :uid"), {"uid": user_id}
        )
    ).mappings().first()
    if row is None:
        raise AppError(f"User '{user_id}' not found.", code="NOT_FOUND", status_code=404)

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
            "new_value_json": '{"event": "REMOVE_USER"}', "created_at": now,
        },
    )
    result = {"as_of": _as_of(), "code": "REMOVED", "user_id": user_id}
    await store_idempotency(session, key=key, user_id=ctx.user_id, route=route, request_hash=req_hash, response=result)
    await session.commit()
    return result
