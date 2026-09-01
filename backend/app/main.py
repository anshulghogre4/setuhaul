from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.routers import (
    admin,
    carrier,
    chat,
    driver,
    gate,
    health_auth,
    internal,
    operations,
    planner,
    scheduling,
    shared,
    shipments,
)
from app.assistant.observability import init_sentry, shutdown_telemetry
from app.core.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.middleware import RequestIdMiddleware
from app.core.settings import assert_region_alignment, get_settings
from app.db.session import db


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    # Co-location guard before anything opens a connection: if compute is in the wrong
    # region, every DB/Redis round trip this process makes crosses a continent, so the
    # process must refuse to start rather than serve correct answers slowly.
    assert_region_alignment(settings)
    db.configure(settings)
    yield
    await db.dispose()
    # Telemetry is flushed here, at shutdown, and never per turn (§10 lever 8).
    shutdown_telemetry()


def create_app() -> FastAPI:
    settings = get_settings()
    # E7.2 (issue #46), DEPLOYMENT.md section 8 (D-3). Before FastAPI() rather than inside the
    # lifespan, for two reasons: Sentry's FastAPI guide asks for init "as early as possible", and
    # the Starlette/FastAPI integrations auto-enable off the installed packages when the SDK
    # initialises -- doing it after the app object exists means the ASGI app is already built.
    # No-op and zero-import while SENTRY_DSN is empty, which is every environment today.
    #
    # This still catches unhandled 500s despite the catch-all handler registered below: Starlette's
    # ServerErrorMiddleware re-raises after its handler has produced the response, precisely so an
    # outer layer can observe the error, and Sentry's middleware sits outside it. Asserted in
    # tests/unit/test_sentry_init.py rather than assumed.
    init_sentry(settings)
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    # CORS first so error responses still get ACAO headers for the browser.
    cors_kwargs: dict = {
        "allow_origins": settings.cors_origin_list,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    regex = (settings.cors_origin_regex or "").strip()
    if regex:
        cors_kwargs["allow_origin_regex"] = regex
    app.add_middleware(CORSMiddleware, **cors_kwargs)
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        """Lightweight alive ping so opening :8000/ is not a 404."""
        return {
            "status": "ok",
            "service": "SetuHaul API",
            "health_live": "/health/live",
            "health_ready": "/health/ready",
            "docs": "/docs",
        }

    app.include_router(health_auth.router)
    app.include_router(driver.router)
    app.include_router(operations.router)
    app.include_router(shipments.router)
    app.include_router(scheduling.router)
    app.include_router(chat.router)
    # E3.3 (issue #27, M3): the SS7.5.6 carrier portal -- five read-only GETs, CARRIER-role only.
    app.include_router(carrier.router)
    # E3.6 (issue #30, M3): SS7.5.1 planner dock-blocking + SS7.5.2 gate/yard writes.
    app.include_router(planner.router)
    app.include_router(gate.router)
    # E3.5 (issue #29, M3): SS7.5.8 shared/cross-cutting tools -- used by every role, owned by none.
    app.include_router(shared.router)
    # E3.4 (issue #28, M3): SS7.5.7 admin console -- users/roles, facility rules, policy, audit.
    app.include_router(admin.router)
    # Machine-callable only (shared-secret header, not a Supabase JWT) -- the M8 expiry sweeper's
    # trigger target. Registered last so it is visibly separate from the user-facing routers.
    app.include_router(internal.router)
    return app


app = create_app()
