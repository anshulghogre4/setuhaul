from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session, get_execution_context, get_request_id
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext
from app.core.settings import Settings, get_settings
from app.db.session import db

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live(request: Request) -> dict[str, Any]:
    return ok({"status": "live"}, get_request_id(request))


@router.get("/health/ready")
async def ready(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "settings_loaded": True,
        "supabase_url_configured": settings.ready_auth,
        "database_url_configured": settings.ready_database,
        "database_reachable": False,
    }
    if settings.ready_database and db.engine is not None:
        try:
            checks["database_reachable"] = await db.ping()
        except Exception:
            checks["database_reachable"] = False

    status = "ready" if checks["database_url_configured"] and checks["database_reachable"] else "degraded"
    body = ok({"status": status, "checks": checks}, get_request_id(request))
    return body


@router.get("/api/v1/auth/me")
async def auth_me(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
) -> dict[str, Any]:
    data = {
        "user_id": ctx.user_id,
        "email": ctx.email,
        "full_name": ctx.full_name,
        "role_id": ctx.role_id,
        "role_name": ctx.role_name,
        "driver_id": ctx.driver_id,
        "facility_id": ctx.facility_id,
        "permissions": ctx.permissions,
        "scope": {
            "type": "global_read_only" if ctx.has_global_read_scope else ("facility" if ctx.facility_id else "self"),
            "facility_id": ctx.facility_id,
            "driver_id": ctx.driver_id,
        },
    }
    return ok(data, get_request_id(request), message="Current user profile.")
