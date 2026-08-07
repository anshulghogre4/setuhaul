from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SuccessEnvelope(BaseModel):
    success: bool = True
    message: str = "Operation completed successfully."
    data: Any = None
    timestamp: str = Field(default_factory=utc_now_iso)
    request_id: str


class ErrorDetail(BaseModel):
    code: str
    detail: str
    field: str | None = None


class ErrorEnvelope(BaseModel):
    success: bool = False
    message: str
    errors: list[ErrorDetail] = Field(default_factory=list)
    timestamp: str = Field(default_factory=utc_now_iso)
    request_id: str


def ok(data: Any, request_id: str, message: str = "Operation completed successfully.") -> dict[str, Any]:
    return SuccessEnvelope(data=data, request_id=request_id, message=message).model_dump()


def fail(
    message: str,
    request_id: str,
    *,
    code: str = "ERROR",
    detail: str | None = None,
    field: str | None = None,
) -> dict[str, Any]:
    return ErrorEnvelope(
        message=message,
        request_id=request_id,
        errors=[ErrorDetail(code=code, detail=detail or message, field=field)],
    ).model_dump()
