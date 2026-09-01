"""Admin console REST surface (`E3.4`, issue #28, `SOLUTION_DESIGN.md` section 7.5.7).

13 tools across four areas: users/roles, facility rules, policy, audit. Role-gated to `ADMIN`
only -- section 7.5.7's persona table scopes this whole console to that one role, unlike the
`OPS_PORTAL_ROLES` superset other consoles share. Thin by the E2.2 rule: authorise, delegate,
envelope; every real decision (scope validation, the Auth Admin API calls, the rule-type registry,
the read-only simulate/publish split) lives in `admin_user_service.py`/`admin_governance_service.py`.

Three **additions to that catalog**, all pure reads, all flagged rather than folded in silently
(the discipline `routers/planner.py`'s `/docks/{dock_id}/block-impact` established):
`GET /users/{user_id}/removal-impact` (A-G8, issue #76 -- `edge-cases.md` #1's confirmation copy
needs its count *before* the write), `GET /policy/active` (A-G7, issue #75 -- nothing could read
the current policy version, so the new `based_on_version_id` baseline had no source and
`screens.md` section 4's read-only current version had nothing to render), and
`GET /facility-rules/{rule_id}/impact` (A-G6, issue #74 -- `edge-cases.md` #4's High-tier
confirmation names the count of affected appointments *before* the edit commits, and no query
anywhere produced it).

**Two further additions, both writes, added 2026-08-31 (A-G5, issue #73):**
`POST /users/{user_id}/resend-invite` and `POST /users/{user_id}/revoke-invite` -- `screens.md`
section 2's pending row specifies both actions by name and section 7.5.7 has no invite-lifecycle
tool at all. They became implementable only once `users` gained a real lifecycle state; before
that there was no way to know which rows they applied to. `GET /users` also gains an
`include_removed` query parameter (issue #81 / `edge-cases.md` #8).

**A fifth addition, a pure read, added 2026-08-31 (A-G10, issue #78):** `GET /facilities`. Four
tools in section 7.5.7 take a facility id as an argument and nothing anywhere told a caller which
ids exist, so the console derived its options from whatever rows it had already loaded -- leaving a
facility with no users and no rules unpickable, and a newly-opened facility unable to receive its
first user through the UI.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_request_id, get_settings_dep, require_roles
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings
from app.services.admin_governance_service import (
    create_facility_rule,
    export_audit_log,
    get_active_policy_version,
    get_audit_log,
    get_facility_rule_impact,
    list_facility_rules,
    publish_policy_version,
    simulate_policy_weights,
    update_facility_rule,
)
from app.services.admin_user_service import (
    deactivate_user,
    get_user_removal_impact,
    invite_user,
    list_facilities,
    list_users,
    reactivate_user,
    remove_user,
    resend_invite,
    revoke_invite,
    update_user,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

AdminCtx = Annotated[ExecutionContext, Depends(require_roles(RoleName.ADMIN))]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def _require_idempotency_key(idempotency_key: str | None) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    return idempotency_key.strip()


class InviteUserBody(BaseModel):
    """`scope` takes one id or a list (A-G4, issue #72).

    Accepting both keeps every existing single-facility caller byte-identical while letting the
    Users tab's facility multi-select (`flows-and-states.md` Flow 1 step 2) submit what it actually
    collects. Which shape a given role may use, and whether each id exists, is decided in
    `admin_user_service._validate_scope` -- not here; the router only names the wire type.
    """

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    role: str
    scope: str | list[str] | None = None


class UpdateUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    scope: str | list[str] | None = None


class CreateFacilityRuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facility_id: str
    rule_type: str
    rule_value: str
    effective_from: str | None = None
    effective_to: str | None = None
    description: str = ""


class UpdateFacilityRuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_value: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None


class SimulatePolicyBody(BaseModel):
    """`weights` stays `dict[str, Any]` on the wire, but its KEYS are no longer free (A-G1, issue
    #69). The allowlist is derived at runtime from `constraints.json`'s own `score_weights`, so it
    lives in `admin_governance_service._validate_weight_keys` where it can read that file, not in a
    Pydantic literal here that would have to be hand-synchronised with the engine. Same rule for
    `PublishPolicyBody`. Unknown keys used to be silently dropped; they are now a named 422."""

    model_config = ConfigDict(extra="forbid")

    weights: dict[str, Any]
    window_start: datetime
    window_end: datetime


class PublishPolicyBody(BaseModel):
    """`based_on_version_id` is `edge-cases.md` #3's optimistic-concurrency baseline (A-G7, issue
    #75) -- optional on the wire only because the first-ever publish has no baseline to cite; the
    service refuses with `BASE_VERSION_REQUIRED` whenever an active version does exist."""

    model_config = ConfigDict(extra="forbid")

    weights: dict[str, Any]
    based_on_version_id: str | None = None


@router.get("/users")
async def users(
    request: Request, ctx: AdminCtx, session: DbSession,
    role_filter: Annotated[str | None, Query()] = None,
    facility_filter: Annotated[str | None, Query()] = None,
    include_removed: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """`include_removed` defaults to false per `edge-cases.md` #8 ("a genuinely removed user does
    not reappear in search"). It is an addition to section 7.5.7's argument list, flagged here
    rather than folded in silently -- see `list_users`' own docstring."""
    result = await list_users(session, ctx, role_filter, facility_filter, include_removed)
    return ok(result, get_request_id(request))


@router.post("/users/invite")
async def users_invite(
    body: InviteUserBody, request: Request, ctx: AdminCtx, session: DbSession, settings: SettingsDep,
) -> dict[str, Any]:
    try:
        result = await invite_user(session, ctx, settings, email=body.email, role=body.role, scope=body.scope)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/users/{user_id}/update")
async def users_update(
    user_id: str, body: UpdateUserBody, request: Request, ctx: AdminCtx, session: DbSession,
) -> dict[str, Any]:
    try:
        result = await update_user(session, ctx, user_id=user_id, role=body.role, scope=body.scope)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/users/{user_id}/deactivate")
async def users_deactivate(user_id: str, request: Request, ctx: AdminCtx, session: DbSession) -> dict[str, Any]:
    try:
        result = await deactivate_user(session, ctx, user_id)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/users/{user_id}/reactivate")
async def users_reactivate(user_id: str, request: Request, ctx: AdminCtx, session: DbSession) -> dict[str, Any]:
    try:
        result = await reactivate_user(session, ctx, user_id)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/users/{user_id}/resend-invite")
async def users_resend_invite(
    user_id: str, request: Request, ctx: AdminCtx, session: DbSession, settings: SettingsDep,
) -> dict[str, Any]:
    """`screens.md` section 2's Resend action (A-G5, issue #73). Addition to section 7.5.7's
    catalog. Takes `user_id` only -- the address the invite goes to is read from the stored row,
    never accepted from the caller."""
    try:
        result = await resend_invite(session, ctx, settings, user_id=user_id)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/users/{user_id}/revoke-invite")
async def users_revoke_invite(
    user_id: str, request: Request, ctx: AdminCtx, session: DbSession, settings: SettingsDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """`screens.md` section 2's Revoke action (A-G5, issue #73). Addition to section 7.5.7's
    catalog. Carries an `Idempotency-Key` for the same reason `/remove` does -- it deletes a
    Supabase Auth identity, which no retry can undo."""
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await revoke_invite(session, ctx, settings, user_id=user_id, idempotency_key=key)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.get("/users/{user_id}/removal-impact")
async def users_removal_impact(
    user_id: str, request: Request, ctx: AdminCtx, session: DbSession,
) -> dict[str, Any]:
    """Preview -- names how many active escalations this user owns before the admin confirms
    (`edge-cases.md` #1, A-G8/issue #76).

    Not in section 7.5.7's own catalog; flagged as an addition, not silently folded in, per the same
    discipline `routers/planner.py`'s `/docks/{dock_id}/block-impact` already uses.
    """
    result = await get_user_removal_impact(session, ctx, user_id=user_id)
    return ok(result, get_request_id(request))


@router.post("/users/{user_id}/remove")
async def users_remove(
    user_id: str, request: Request, ctx: AdminCtx, session: DbSession, settings: SettingsDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await remove_user(session, ctx, settings, user_id=user_id, idempotency_key=key)
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.get("/facilities")
async def facilities(request: Request, ctx: AdminCtx, session: DbSession) -> dict[str, Any]:
    """The facility list every scope control on this console needs (A-G10, issue #78).

    Addition to section 7.5.7's catalog, flagged rather than folded in silently. Takes no
    arguments -- there is nothing here to scope *by*, and the role gate is the whole authorisation
    decision (M15: authority comes from the verified token, never from a client-supplied id).

    Registered before `/facility-rules` only for readability; the two paths do not overlap, so
    Starlette's ordering is not load-bearing here.
    """
    result = await list_facilities(session, ctx)
    return ok(result, get_request_id(request))


@router.get("/facility-rules")
async def facility_rules(
    request: Request, ctx: AdminCtx, session: DbSession,
    facility_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    result = await list_facility_rules(session, ctx, facility_id)
    return ok(result, get_request_id(request))


@router.post("/facility-rules")
async def facility_rules_create(
    body: CreateFacilityRuleBody, request: Request, ctx: AdminCtx, session: DbSession,
) -> dict[str, Any]:
    try:
        result = await create_facility_rule(
            session, ctx, facility_id=body.facility_id, rule_type=body.rule_type,
            rule_value=body.rule_value, effective_from=body.effective_from,
            effective_to=body.effective_to, description=body.description,
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.get("/facility-rules/{rule_id}/impact")
async def facility_rule_impact(
    rule_id: str, request: Request, ctx: AdminCtx, session: DbSession,
    rule_value: Annotated[str | None, Query()] = None,
    effective_from: Annotated[str | None, Query()] = None,
    effective_to: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Preview -- names the already-committed appointments a tightened rule would newly make
    non-compliant, before the edit commits (`edge-cases.md` #4, A-G6/issue #74).

    The three query parameters are `update_facility_rule`'s own arguments, omitted meaning
    unchanged, so the preview and the write are computed from the same proposal. Not in section
    7.5.7's own catalog; flagged as an addition, not silently folded in, per the same discipline
    `routers/planner.py`'s `/docks/{dock_id}/block-impact` already uses.
    """
    result = await get_facility_rule_impact(
        session, ctx, rule_id=rule_id, rule_value=rule_value,
        effective_from=effective_from, effective_to=effective_to,
    )
    return ok(result, get_request_id(request))


@router.post("/facility-rules/{rule_id}/update")
async def facility_rules_update(
    rule_id: str, body: UpdateFacilityRuleBody, request: Request, ctx: AdminCtx, session: DbSession,
) -> dict[str, Any]:
    try:
        result = await update_facility_rule(
            session, ctx, rule_id=rule_id, rule_value=body.rule_value,
            effective_from=body.effective_from, effective_to=body.effective_to,
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.post("/policy/simulate")
async def policy_simulate(
    body: SimulatePolicyBody, request: Request, ctx: AdminCtx, session: DbSession,
) -> dict[str, Any]:
    result = await simulate_policy_weights(
        session, ctx, weights=body.weights, window_start=body.window_start, window_end=body.window_end
    )
    return ok(result, get_request_id(request))


@router.get("/policy/active")
async def policy_active(request: Request, ctx: AdminCtx, session: DbSession) -> dict[str, Any]:
    """The current version the Policy editor edits away from, and the baseline
    `POST /policy/publish` requires (A-G7, issue #75).

    Not in section 7.5.7's own catalog; flagged as an addition, not silently folded in.
    """
    result = await get_active_policy_version(session, ctx)
    return ok(result, get_request_id(request))


@router.post("/policy/publish")
async def policy_publish(
    body: PublishPolicyBody, request: Request, ctx: AdminCtx, session: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await publish_policy_version(
            session, ctx, weights=body.weights, idempotency_key=key,
            based_on_version_id=body.based_on_version_id,
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result, get_request_id(request))


@router.get("/audit-log")
async def audit_log(
    request: Request, ctx: AdminCtx, session: DbSession,
    actor: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    resource: Annotated[str | None, Query()] = None,
    event: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """section 7.5.7 `get_audit_log` / `FR-ADM-008`.

    `event` is issue #104's addition: `event_type` filters `action_type`, which is a generic CRUD
    verb for every admin-console write, so it cannot express `screens.md` section 5's Event column
    ("Policy published", "User removed"). An unsupported value is a 422 naming the vocabulary, not
    an empty list -- see `admin_governance_service.AUDIT_EVENT_VOCABULARY`. Both filters remain and
    compose.
    """
    result = await get_audit_log(
        session, ctx, actor=actor, event_type=event_type, date_from=date_from, date_to=date_to,
        resource=resource, event=event,
    )
    return ok(result, get_request_id(request))


@router.get("/audit-log/export")
async def audit_log_export(
    ctx: AdminCtx, session: DbSession,
    actor: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    event: Annotated[str | None, Query()] = None,
) -> PlainTextResponse:
    """section 7.5.7 `export_audit_log` -- "same filters as the current view".

    `event` is threaded through for that clause specifically (issue #104): an export that ignored a
    filter the tab can now apply would be exactly the silent full-table dump section 7.5.7 forbids.
    """
    csv_text = await export_audit_log(
        session, ctx, actor=actor, event_type=event_type, date_from=date_from, date_to=date_to,
        event=event,
    )
    return PlainTextResponse(csv_text, media_type="text/csv")
