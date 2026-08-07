from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.envelope import fail


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "APP_ERROR",
        status_code: int = 400,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail or message


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=fail(exc.message, _request_id(request), code=exc.code, detail=exc.detail),
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "HTTP_ERROR"
    if exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    return JSONResponse(
        status_code=exc.status_code,
        content=fail(str(exc.detail), _request_id(request), code=code, detail=str(exc.detail)),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "code": "VALIDATION_ERROR",
            "detail": e.get("msg", "Invalid input"),
            "field": ".".join(str(x) for x in e.get("loc", [])),
        }
        for e in exc.errors()
    ]
    body = fail("Validation failed.", _request_id(request), code="VALIDATION_ERROR")
    body["errors"] = errors
    return JSONResponse(status_code=422, content=body)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=fail(
            "Internal server error.",
            _request_id(request),
            code="INTERNAL_ERROR",
            detail=str(exc)[:500],
        ),
    )
