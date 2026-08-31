from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.security import JwtVerifier
from app.core.settings import Settings, get_settings
from app.db.session import db, release_transaction

_FACILITY_OPS_PERMS = [
    "operations:read_facility",
    "shipment:read_facility",
    "exception:read_facility",
    "schedule:read_facility",
    "dock:read_facility",
    "rules:read_facility",
]

# Issue #79: the gate/yard kiosk's own permission set, deliberately a strict subset of
# _FACILITY_OPS_PERMS rather than the same list. Derived from SS7.5.2's five tools plus the one
# read (`GY-G1`) that reaches them -- and from `auth-and-scoping.md`'s "What each role never sees"
# row for this persona ("Scheduling controls. Anything beyond the current facility's yard"), which
# is why `schedule:*` and `rules:*` are absent. `checkin:write_facility` is a new string because
# SS7.5.2 is the first catalog to define a facility-tier *write*; it follows the existing
# `<domain>:<verb>_<tier>` convention.
_GATE_PERMS = [
    "checkin:write_facility",
    "checkin:read_facility",
    "shipment:read_facility",
    "dock:read_facility",
]

_GLOBAL_OPS_PERMS = [
    "operations:read_global",
    "shipment:read_global",
    "exception:read_global",
    "schedule:read_global",
    "dock:read_global",
    "rules:read_global",
]

ROLE_PERMISSIONS: dict[RoleName, list[str]] = {
    RoleName.DRIVER: [
        "driver:read_self",
        "shipment:read_own",
        "appointment:read_own",
        "eta:write_own",
        "chat:own",
    ],
    RoleName.OPERATIONS_EXECUTIVE: list(_FACILITY_OPS_PERMS),
    RoleName.WAREHOUSE_PLANNER: list(_FACILITY_OPS_PERMS),
    RoleName.OPERATIONS_MANAGER: list(_FACILITY_OPS_PERMS),
    RoleName.FACILITY_MANAGER: list(_FACILITY_OPS_PERMS),
    RoleName.ADMIN: list(_GLOBAL_OPS_PERMS),
    RoleName.TRANSPORT_MANAGER: list(_GLOBAL_OPS_PERMS),
    RoleName.REGIONAL_OPERATIONS_HEAD: list(_GLOBAL_OPS_PERMS),
    # E3.3 (issue #27, M3): filled in now that SS7.5.6's catalog exists, as E2.3's placeholder
    # comment said it would be. Read-only by construction -- there is no `*:write_carrier` string
    # here because SS7.5.6 defines no mutating tool, and the naming follows the existing
    # `<domain>:<verb>_<tier>` convention with a new `_carrier` tier rather than reusing
    # `_facility` (carriers are explicitly not facility-scoped). The four domains are SS2's
    # persona table for this role -- shipments, drivers, vehicles -- plus the exceptions raised
    # against those shipments, which SS7.5.6's `list_fleet_exceptions` reads.
    RoleName.CARRIER: [
        "shipment:read_carrier",
        "driver:read_carrier",
        "vehicle:read_carrier",
        "exception:read_carrier",
    ],
    RoleName.GATE_OFFICER: list(_GATE_PERMS),
}

# The shared ops-portal surfaces (exception console, scheduling confirm/reject, search).
# GATE_OFFICER is deliberately absent, and this is the load-bearing half of issue #79's fix:
# adding the role only improves on the old planner-credential mapping if the new role is narrower
# than what it replaces. `auth-and-scoping.md`'s "Gate officer never sees: Scheduling controls"
# is enforced here, by omission, not by a UI decision.
OPS_PORTAL_ROLES = (
    RoleName.OPERATIONS_EXECUTIVE,
    RoleName.WAREHOUSE_PLANNER,
    RoleName.OPERATIONS_MANAGER,
    RoleName.FACILITY_MANAGER,
    RoleName.TRANSPORT_MANAGER,
    RoleName.REGIONAL_OPERATIONS_HEAD,
    RoleName.ADMIN,
)

# Who may work the gate/yard kiosk (`api/v1/routers/gate.py`, SS7.5.2). Named here rather than
# inline in the router so that "which roles know about the kiosk" is answerable from the one file
# that owns role groupings -- and so a test can assert the relationship between this tuple and
# OPS_PORTAL_ROLES directly. `GATE_OFFICER` is in this one and not in that one; that asymmetry is
# issue #79's whole point.
GATE_KIOSK_ROLES = (
    RoleName.GATE_OFFICER,
    RoleName.WAREHOUSE_PLANNER,
    RoleName.FACILITY_MANAGER,
    RoleName.ADMIN,
)


def get_settings_dep() -> Settings:
    return get_settings()


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


# Process-scoped verifiers. A per-request JwtVerifier meant PyJWKClient (whose JWK-set
# cache is per-instance) was rebuilt every request, so every authenticated request paid a
# blocking urllib JWKS fetch + TLS handshake before any application work — and
# security.py's hourly-refresh guard could never be satisfied. Keyed by the auth-relevant
# settings rather than @lru_cache'd on the Settings object, which pydantic makes
# unhashable. Rotation still works: PyJWKClient re-fetches when a token's `kid` is not in
# the cached set, and its JWKSetCache expires on its own 300 s lifespan.
_JWT_VERIFIERS: dict[tuple[str, str, str], JwtVerifier] = {}


def get_jwt_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> JwtVerifier:
    key = (
        settings.supabase_jwks_url,
        settings.supabase_issuer,
        settings.supabase_jwt_audience,
    )
    verifier = _JWT_VERIFIERS.get(key)
    if verifier is None:
        verifier = JwtVerifier(settings)
        _JWT_VERIFIERS[key] = verifier
    return verifier


async def get_db_session() -> AsyncSession:
    if db.session_factory is None:
        raise AppError(
            "Database is not configured.",
            code="DB_UNAVAILABLE",
            status_code=503,
        )
    async with db.session_factory() as session:
        yield session


async def get_execution_context(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    verifier: Annotated[JwtVerifier, Depends(get_jwt_verifier)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> ExecutionContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("Missing bearer token.", code="UNAUTHORIZED", status_code=401)
    token = authorization.split(" ", 1)[1].strip()
    claims = verifier.verify_access_token(token)
    subject = str(claims["sub"])

    row = (
        await session.execute(
            text(
                """
                SELECT u.user_id, u.email, u.full_name, u.role_id, r.role_name,
                       u.driver_id, u.facility_id, u.is_active, u.auth_user_id,
                       u.invited_at, u.invite_accepted_at
                FROM public.users u
                JOIN public.roles r ON r.role_id = u.role_id
                WHERE u.auth_user_id = CAST(:auth_user_id AS uuid)
                LIMIT 1
                """
            ),
            {"auth_user_id": subject},
        )
    ).mappings().first()

    if row is None:
        raise AppError(
            "Authenticated subject is not mapped to an application user.",
            code="USER_UNMAPPED",
            status_code=403,
        )
    if int(row["is_active"]) != 1:
        raise AppError("User account is disabled.", code="USER_DISABLED", status_code=403)

    try:
        role_name = RoleName(str(row["role_name"]))
    except ValueError as exc:
        raise AppError("Unknown role.", code="ROLE_UNKNOWN", status_code=403) from exc

    # E2.3 (issue #23, M15): carrier_id has no column on users -- user_scopes is its source of
    # truth. Only looked up for the CARRIER role; every other role's identity resolution is
    # unchanged from before this migration, which is what issue #23's rollback note requires
    # ("every existing role's scope resolves identically before and after").
    carrier_id: str | None = None
    if role_name == RoleName.CARRIER:
        scope_row = (
            await session.execute(
                text(
                    """
                    SELECT scope_value FROM public.user_scopes
                    WHERE user_id = :user_id AND scope_type = 'CARRIER'
                    LIMIT 1
                    """
                ),
                {"user_id": str(row["user_id"])},
            )
        ).mappings().first()
        carrier_id = str(scope_row["scope_value"]) if scope_row else None

    # ------------------------------------------------------------------------------------------
    # Issue #73: the invite-acceptance stamp. THIS IS THE WRITE SITE, and the reason it lives in
    # an auth dependency rather than an admin tool is the whole point of the fix.
    # ------------------------------------------------------------------------------------------
    #
    # `public.users.last_login_ts` -- same table -- is read by `admin_user_service.list_users` and
    # `account_service.get_account_profile` and written by NOTHING in this application; only
    # `supabase/seed.sql` sets it. That is why `last_login_ts IS NULL` reported every post-seed
    # user as a pending invitation forever. A `invite_accepted_at` column with no guaranteed
    # writer would rot identically, so the writer was chosen before the column was.
    #
    # This dependency is the one place in the backend that cannot be skipped: every authenticated
    # route resolves an ExecutionContext (directly or through `require_roles`), so a request
    # either ran this or was never authenticated. And a JWT whose `sub` matches this row's
    # `auth_user_id` cannot exist until GoTrue itself accepted the user's invite token and issued
    # a session -- so seeing a valid token here IS the acceptance, observed rather than reported
    # by a client that might forget to report it.
    #
    # Cost, traced rather than assumed: both guard columns come back on the row the identity
    # SELECT above already fetched, so the steady state adds zero statements and zero round trips.
    # The UPDATE fires at most once per invited user, ever. `invited_at IS NOT NULL` keeps it from
    # firing at all for seeded/pre-existing accounts, which were never invited through the console
    # and must stay ACTIVE rather than acquiring a meaningless accept stamp -- and it is the
    # invariant `users_accept_implies_invite_chk` pins in the migration.
    #
    # The `AND invite_accepted_at IS NULL` in the WHERE clause is not redundant with the Python
    # guard: two concurrent first requests both read NULL, and the predicate makes the loser a
    # no-op instead of sliding the recorded instant forward.
    #
    # No commit here: `release_transaction` below already commits, so this rides the transaction
    # that is being closed anyway.
    if row["invited_at"] is not None and row["invite_accepted_at"] is None:
        await session.execute(
            text(
                """
                UPDATE public.users SET invite_accepted_at = :accepted_at
                WHERE user_id = :user_id AND invite_accepted_at IS NULL
                """
            ),
            {"accepted_at": datetime.now(timezone.utc), "user_id": str(row["user_id"])},
        )

    # E4.4 (issue #34): close the identity-lookup transaction here rather than leaving it open
    # for the rest of the request -- for the driver chat endpoint that request can run for
    # seconds of LLM think-time, and this dependency runs first, on every authenticated request.
    await release_transaction(session)

    return ExecutionContext(
        request_id=get_request_id(request),
        auth_subject=subject,
        user_id=str(row["user_id"]),
        email=str(row["email"]),
        full_name=str(row["full_name"]),
        role_id=str(row["role_id"]),
        role_name=role_name,
        driver_id=row["driver_id"],
        facility_id=row["facility_id"],
        carrier_id=carrier_id,
        is_active=True,
        permissions=ROLE_PERMISSIONS.get(role_name, []),
    )


def require_roles(*roles: RoleName):
    async def _dep(ctx: Annotated[ExecutionContext, Depends(get_execution_context)]) -> ExecutionContext:
        if ctx.role_name not in roles:
            raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)
        return ctx

    return _dep
