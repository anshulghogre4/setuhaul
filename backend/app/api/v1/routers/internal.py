"""Internal machine-callable job endpoints -- the target the M8 expiry sweeper is triggered through.

Design citation: `TECH-STACK/TECH_STACK.md` section 5 ("Target: an **authenticated internal endpoint
on the FastAPI service** -- not a separate Lambda. Reuses the existing connection pool and stays
inside the co-located tier"); `SOLUTION_DESIGN.md` M8 / D2 / D9 / section 7.5.1.

## Why a shared secret and not the ordinary JWT path

Every other router here depends on `get_execution_context`, which requires a verified Supabase
access token mapped to a `public.users` row. A scheduled AWS caller has no Supabase session and
cannot mint one. What it *does* have natively is an EventBridge *connection*, whose authorization
methods are exactly "basic, OAuth, and API Key" (AWS EventBridge, "Connections for API targets"),
with the credential held in Secrets Manager on AWS's side. API Key -- a fixed header name and value
-- is therefore the shape this endpoint is built for.

Comparison is `secrets.compare_digest`, per FastAPI's own security guidance (FastAPI, "HTTP Basic
Auth": *"Using `secrets.compare_digest()` ... takes the same time to compare `stanleyjobsox` to
`stanleyjobson` than it takes to compare `johndoe` to `stanleyjobson`"*), on UTF-8 bytes because
that function requires bytes or ASCII-only strings.

**Fail closed.** With `JOB_AUTH_TOKEN` unset the route returns 503 and does nothing, rather than
accepting any caller. An endpoint that releases dock capacity must not be reachable unauthenticated
just because a deploy forgot an environment variable.

## Two constraints the transport imposes on this handler

EventBridge Scheduler cannot call an HTTPS endpoint directly -- its targets are templated AWS-service
targets plus the universal AWS-SDK target (AWS, "Managing targets in EventBridge Scheduler"); HTTPS
endpoints are reached through an EventBridge *API destination*, which is a target of an event-bus
rule or pipe. Whichever way the trigger is wired, an API destination invocation has a **5-second
client execution timeout** and is **retried on 5xx/429/409** (AWS, "API destinations as targets").
So:

1. The sweep is batch-bounded (`EXPIRY_SWEEP_BATCH_LIMIT`) and never unbounded, and each appointment
   commits on its own, so a timeout mid-batch loses no completed work.
2. A retry is safe with no idempotency key: the sweeper's `appointment_status =
   'PENDING_CONFIRMATION'` predicate means a replay finds nothing left to do.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_request_id, get_settings_dep
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.settings import Settings
from app.scheduling.expiry import sweep_expired_appointments

router = APIRouter(prefix="/internal", tags=["internal-jobs"])

JOB_TOKEN_HEADER = "X-SetuHaul-Job-Token"


def require_job_token(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    x_setuhaul_job_token: Annotated[str | None, Header(alias=JOB_TOKEN_HEADER)] = None,
) -> Settings:
    """Authenticate the scheduled caller, or refuse. Returns settings so handlers reuse the same one.

    503 for an unconfigured token and 401 for a wrong one are deliberately different: the first is
    an operator's problem on this side and should page, the second is a caller that must be rejected.
    401 is also on EventBridge's retry list while a plain 4xx is not, which means a genuine
    misconfiguration retries and shows up as sustained failures rather than one silent drop.
    """
    expected = (settings.job_auth_token or "").strip()
    if not expected:
        raise AppError(
            "Internal job authentication is not configured; refusing to run. Set JOB_AUTH_TOKEN.",
            code="JOB_AUTH_UNCONFIGURED",
            status_code=503,
        )
    presented = (x_setuhaul_job_token or "").strip()
    if not presented or not secrets.compare_digest(
        presented.encode("utf-8"), expected.encode("utf-8")
    ):
        raise AppError(
            "Invalid internal job token.",
            code="JOB_AUTH_INVALID",
            status_code=401,
        )
    return settings


@router.post("/jobs/expiry-sweep")
async def run_expiry_sweep(
    request: Request,
    settings: Annotated[Settings, Depends(require_job_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """One M8 sweeper cycle: D9 PENDING expiry (+ D2 HELD, reported unsupported).

    Takes no request body at all, and specifically no `now` -- see `app/core/clock.py` for why a
    caller-supplied instant deciding which appointments expire is refused. Tests force the
    section 9.2 #3 race by calling `sweep_expired_appointments` directly with a `FrozenClock`.
    """
    actor = (settings.job_actor_user_id or "").strip()
    if not actor:
        raise AppError(
            "JOB_ACTOR_USER_ID is not configured; refusing to sweep. The sweeper must attribute "
            "its audit_logs rows to a real public.users row, because SOLUTION_DESIGN.md "
            "section 7.5.1 requires the audit trail to name who applied the expiring transition.",
            code="SWEEPER_ACTOR_UNCONFIGURED",
            status_code=503,
        )
    try:
        result = await sweep_expired_appointments(
            session,
            actor_user_id=actor,
            pending_ttl_minutes=settings.pending_confirmation_ttl_minutes,
            held_ttl_seconds=settings.held_slot_ttl_seconds,
            batch_limit=settings.expiry_sweep_batch_limit,
            # One flag gates both halves of the two-phase path (issue #53). It has to be the same
            # flag `request_slot` reads: sweeping for HELD rows while nothing can create one would
            # query a column that does not exist on a deploy where the migration has not been
            # applied, turning a healthy sweep into a 500 on the D9 leg too.
            held_enabled=settings.two_phase_hold_enabled,
        )
    except Exception:
        # The sweeper commits per appointment, so a rollback here can only discard the partial
        # transaction of the row that failed -- never a release that already committed.
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message=(
            f"Expiry sweep complete: {result.pending_expired} pending appointment(s) expired and "
            "their dock intervals released."
        ),
    )
