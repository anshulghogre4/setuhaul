"""Account/identity shared tools -- SOLUTION_DESIGN.md section 7.5.8, FR-X-021 .. FR-X-025.

`get_account_profile` is a pure Postgres read of the identity `get_execution_context` already
resolved. `request_password_reset` and `sign_out_everywhere` are the two tools here that are not
Postgres reads at all: both proxy to Supabase Auth's own HTTP API (`resetPasswordForEmail` /
`signOut`), because password reset and session revocation are Supabase Auth's job, not this
backend's -- there is no local password or session table to write to.

Scope note distinct from every other write in this codebase: both auth-proxy tools act **only on
the caller's own identity** (`section 7.5.8`: "acts on the caller's own identity"). Neither takes
nor accepts a target user id from the caller; `request_password_reset` takes an email precisely
because the caller is, by definition, not yet authenticated when they need it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import Settings
from app.core.tls import use_system_trust_store


class PasswordResetResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    code: str = "RESET_REQUESTED"
    message: str = "If that email is registered, a reset link has been sent."


class SignOutEverywhereResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    code: str
    message: str


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_account_profile(session: AsyncSession, ctx: ExecutionContext) -> dict[str, Any]:
    """SS7.5.8 `get_account_profile` -- arguments: none, identity from the verified token (M15).

    Read-only by design (SS7.5.8: "there is no `update_account_profile`, since Supabase Auth is
    the identity source of record"). `scoped_facilities` reads `user_scopes` rather than the
    single `users.facility_id` column, since that is the only source that can express more than
    one facility per user (the identity model E2.3 built for exactly this).
    """
    row = (
        await session.execute(
            text(
                """
                SELECT u.user_id, u.full_name, u.email, u.phone_number, u.employee_code,
                       r.role_name, u.facility_id, u.driver_id, u.is_active, u.last_login_ts
                FROM public.users u
                JOIN public.roles r ON r.role_id = u.role_id
                WHERE u.user_id = :user_id
                """
            ),
            {"user_id": ctx.user_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Account not found.", code="NOT_FOUND", status_code=404)

    scoped_facilities = (
        await session.execute(
            text(
                "SELECT scope_value FROM public.user_scopes "
                "WHERE user_id = :user_id AND scope_type = 'FACILITY'"
            ),
            {"user_id": ctx.user_id},
        )
    ).scalars().all()

    profile = dict(row)
    profile["scoped_facility_ids"] = list(scoped_facilities)
    profile["as_of"] = _as_of()
    profile["source"] = "postgresql"
    return profile


async def request_password_reset(settings: Settings, email: str) -> PasswordResetResult:
    """SS7.5.8 `request_password_reset` -- `email` only (decided 2026-08-22: email-only for v1).

    Wraps Supabase Auth's public `resetPasswordForEmail` (`POST /auth/v1/recover`), called with
    the anon key -- this is meant to be reachable by an unauthenticated caller who forgot their
    password, so it takes no `ExecutionContext` at all. Returns an **identical response whether or
    not the email matched an account** (`auth-and-scoping.md`'s enumeration-safety rule): the
    upstream call's own success/failure is deliberately not surfaced, since GoTrue's `/recover`
    endpoint itself already returns 200 for both a real and a non-existent email, but this
    function does not trust that implementation detail to hold forever -- it normalises to one
    outcome either way, including on a transport failure, so a network hiccup can never leak
    "that email doesn't exist" by contrast with the success case.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise AppError("Supabase Auth is not configured.", code="AUTH_MISCONFIGURED", status_code=503)
    use_system_trust_store()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/recover",
                json={"email": email},
                headers={"apikey": settings.supabase_anon_key, "Content-Type": "application/json"},
            )
    except httpx.HTTPError:
        # Deliberately swallowed, not raised: a transport failure must produce the exact same
        # response as a real send, or its distinctness from the success case becomes an oracle.
        pass
    return PasswordResetResult(as_of=_as_of())


async def sign_out_everywhere(settings: Settings, access_token: str) -> SignOutEverywhereResult:
    """SS7.5.8 `sign_out_everywhere` -- arguments: none (acts on the caller's own identity).

    Calls Supabase Auth's `POST /auth/v1/logout?scope=global` **using the caller's own bearer
    token**, not the service-role key -- this is a self-service action on the caller's own
    session, not an admin operation on someone else's, so no elevated credential belongs here at
    all. Revokes every refresh token for this user; per SS7.5.8's own stated honesty requirement,
    it does **not** instantly invalidate an access token already issued to another device -- that
    token remains valid until its own short expiry. The caller-facing copy this result feeds
    should say "signs out other devices," never imply an instant kill switch.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise AppError("Supabase Auth is not configured.", code="AUTH_MISCONFIGURED", status_code=503)
    use_system_trust_store()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/logout?scope=global",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
    except httpx.HTTPError as exc:
        raise AppError(
            "Unable to reach Supabase Auth.", code="AUTH_UNAVAILABLE", status_code=503
        ) from exc
    if response.status_code >= 400:
        raise AppError(
            "Supabase Auth refused the sign-out request.", code="AUTH_SIGN_OUT_FAILED",
            status_code=502, detail=response.text[:300],
        )
    return SignOutEverywhereResult(
        as_of=_as_of(), code="SIGNED_OUT_EVERYWHERE",
        message="Other devices have been signed out. Already-issued access tokens remain valid "
        "until they individually expire.",
    )
