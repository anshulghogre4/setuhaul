"""Admin console REST surface (`E3.4`, issue #28, `SOLUTION_DESIGN.md` section 7.5.7).

13 tools across four areas: users/roles, facility rules, policy, audit. Role-gated to `ADMIN`
only -- section 7.5.7's persona table scopes this whole console to that one role, unlike the
`OPS_PORTAL_ROLES` superset other consoles share. Thin by the E2.2 rule: authorise, delegate,
envelope; every real decision (scope validation, the Auth Admin API calls, the rule-type registry,
the read-only simulate/publish split) lives in `admin_user_service.py`/`admin_governance_service.py`.
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
    get_audit_log,
    list_facility_rules,
    publish_policy_version,
    simulate_policy_weights,
    update_facility_rule,
)
from app.services.admin_user_service import (
    deactivate_user,
    invite_user,
    list_users,
    reactivate_user,
    remove_user,
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
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    role: str
    scope: str | None = None


class UpdateUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    scope: str | None = None


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
    model_config = ConfigDict(extra="forbid")

    weights: dict[str, Any]
    window_start: datetime
    window_end: datetime


class PublishPolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: dict[str, Any]


@router.get("/users")
async def users(
    request: Request, ctx: AdminCtx, session: DbSession,
    role_filter: Annotated[str | None, Query()] = None,
    facility_filter: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    result = await list_users(session, ctx, role_filter, facility_filter)
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


@router.post("/policy/publish")
async def policy_publish(
    body: PublishPolicyBody, request: Request, ctx: AdminCtx, session: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    try:
        result = await publish_policy_version(session, ctx, weights=body.weights, idempotency_key=key)
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
) -> dict[str, Any]:
    result = await get_audit_log(
        session, ctx, actor=actor, event_type=event_type, date_from=date_from, date_to=date_to, resource=resource
    )
    return ok(result, get_request_id(request))


@router.get("/audit-log/export")
async def audit_log_export(
    ctx: AdminCtx, session: DbSession,
    actor: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
) -> PlainTextResponse:
    csv_text = await export_audit_log(
        session, ctx, actor=actor, event_type=event_type, date_from=date_from, date_to=date_to
    )
    return PlainTextResponse(csv_text, media_type="text/csv")
