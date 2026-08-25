"""Shared/cross-cutting REST surface (`E3.5`, issue #29, `SOLUTION_DESIGN.md` section 7.5.8).

Used by every role, owned by none -- `search_records`, notifications, account profile,
password reset, sign-out-everywhere. Thin by the E2.2 rule: authorise, delegate, envelope.

Two endpoints here are deliberately **not** gated by `get_execution_context`:
`request_password_reset` is reachable by a caller who is, by definition, not authenticated (they
forgot their password); everything else requires a verified identity, matching `health_auth.py`'s
own `/health/*` vs `/auth/me` split.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_execution_context, get_request_id, get_settings_dep
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import Settings
from app.services.account_service import get_account_profile, request_password_reset, sign_out_everywhere
from app.services.notification_service import (
    get_notification_preferences,
    get_notifications,
    mark_notifications_read,
    update_notification_preferences,
)
from app.services.search_service import search_records

router = APIRouter(prefix="/api/v1", tags=["shared"])

AnyCtx = Annotated[ExecutionContext, Depends(get_execution_context)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


class MarkNotificationsReadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_ids: list[str] = Field(min_length=1, max_length=50)


class NotificationPreferenceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    channel_web_push: bool = True
    channel_email: bool = True
    digest_mode: bool = False


class UpdateNotificationPreferencesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[NotificationPreferenceEntry] = Field(min_length=1, max_length=10)


class PasswordResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Plain str, not pydantic's EmailStr: that needs the `email-validator` package, not installed
    # in this project. A light structural check here is enough -- Supabase Auth's own /recover
    # endpoint is the real validator, and this tool must return the same response either way
    # (enumeration-safety), so over-validating client-side buys nothing.
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/search")
async def search(
    request: Request,
    ctx: AnyCtx,
    session: DbSession,
    query: Annotated[str, Query(min_length=1)],
    entity_types: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    result = await search_records(session, ctx, query, entity_types)
    return ok(result, get_request_id(request))


@router.get("/notifications")
async def notifications(
    request: Request,
    ctx: AnyCtx,
    session: DbSession,
    cursor: Annotated[str | None, Query()] = None,
    unread_only: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    result = await get_notifications(session, ctx, cursor, unread_only)
    return ok(result, get_request_id(request))


@router.post("/notifications/mark-read")
async def notifications_mark_read(
    body: MarkNotificationsReadBody,
    request: Request,
    ctx: AnyCtx,
    session: DbSession,
) -> dict[str, Any]:
    result = await mark_notifications_read(session, ctx, body.notification_ids)
    return ok(result, get_request_id(request))


@router.get("/notification-preferences")
async def notification_preferences(
    request: Request,
    ctx: AnyCtx,
    session: DbSession,
) -> dict[str, Any]:
    result = await get_notification_preferences(session, ctx)
    return ok(result, get_request_id(request))


@router.post("/notification-preferences")
async def update_notification_preferences_endpoint(
    body: UpdateNotificationPreferencesBody,
    request: Request,
    ctx: AnyCtx,
    session: DbSession,
) -> dict[str, Any]:
    result = await update_notification_preferences(
        session, ctx, [entry.model_dump() for entry in body.categories]
    )
    return ok(result, get_request_id(request))


@router.get("/account-profile")
async def account_profile(
    request: Request,
    ctx: AnyCtx,
    session: DbSession,
) -> dict[str, Any]:
    result = await get_account_profile(session, ctx)
    return ok(result, get_request_id(request))


@router.post("/password-reset")
async def password_reset(
    body: PasswordResetBody,
    request: Request,
    settings: SettingsDep,
) -> dict[str, Any]:
    """No `get_execution_context` dependency -- reachable without a valid session, by design."""
    result = await request_password_reset(settings, body.email)
    return ok(result.model_dump(), get_request_id(request))


@router.post("/sign-out-everywhere")
async def sign_out_everywhere_endpoint(
    request: Request,
    ctx: AnyCtx,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Uses the caller's own bearer token, not the service-role key -- see
    `account_service.sign_out_everywhere`'s docstring for why. `get_execution_context` (via
    `AnyCtx`) already validated this same header once; re-reading it here is the only way to
    forward the raw token, since `ExecutionContext` deliberately carries only derived claims.
    """
    del ctx  # already proved the caller is authenticated; the raw token below is what's forwarded
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("Missing bearer token.", code="UNAUTHORIZED", status_code=401)
    token = authorization.split(" ", 1)[1].strip()
    result = await sign_out_everywhere(settings, token)
    return ok(result.model_dump(), get_request_id(request))
