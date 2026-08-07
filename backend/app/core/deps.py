from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.security import JwtVerifier
from app.core.settings import Settings, get_settings
from app.db.session import db

ROLE_PERMISSIONS: dict[RoleName, list[str]] = {
    RoleName.DRIVER: [
        "driver:read_self",
        "shipment:read_own",
        "appointment:read_own",
        "eta:write_own",
        "chat:own",
    ],
    RoleName.OPERATIONS_EXECUTIVE: [
        "operations:read_facility",
        "shipment:read_facility",
        "exception:read_facility",
        "schedule:read_facility",
        "dock:read_facility",
        "rules:read_facility",
    ],
    RoleName.ADMIN: [
        "operations:read_global",
        "shipment:read_global",
        "exception:read_global",
        "schedule:read_global",
        "dock:read_global",
        "rules:read_global",
    ],
}


def get_settings_dep() -> Settings:
    return get_settings()


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def get_jwt_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> JwtVerifier:
    return JwtVerifier(settings)


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
                       u.driver_id, u.facility_id, u.is_active, u.auth_user_id
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
        is_active=True,
        permissions=ROLE_PERMISSIONS.get(role_name, []),
    )


def require_roles(*roles: RoleName):
    async def _dep(ctx: Annotated[ExecutionContext, Depends(get_execution_context)]) -> ExecutionContext:
        if ctx.role_name not in roles:
            raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)
        return ctx

    return _dep
