from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.routers import (
    chat,
    driver,
    health_auth,
    internal,
    operations,
    scheduling,
    shipments,
)
from app.assistant.observability import shutdown_telemetry
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
    # Machine-callable only (shared-secret header, not a Supabase JWT) -- the M8 expiry sweeper's
    # trigger target. Registered last so it is visibly separate from the five user-facing routers.
    app.include_router(internal.router)
    return app


app = create_app()
