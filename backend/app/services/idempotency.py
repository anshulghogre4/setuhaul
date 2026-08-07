from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def lookup_idempotency(
    session: AsyncSession,
    *,
    key: str,
    user_id: str,
    route: str,
    request_hash: str,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT idempotency_key, user_id, route, request_hash, response_json, status_code, expires_at
                FROM public.idempotency_requests
                WHERE idempotency_key = :key
                LIMIT 1
                """
            ),
            {"key": key},
        )
    ).mappings().first()
    if row is None:
        return None
    if row["user_id"] != user_id or row["route"] != route:
        raise AppError(
            "Idempotency key belongs to a different command scope.",
            code="IDEMPOTENCY_SCOPE_MISMATCH",
            status_code=409,
        )
    if row["request_hash"] != request_hash:
        raise AppError(
            "Same Idempotency-Key with a different payload.",
            code="IDEMPOTENCY_PAYLOAD_MISMATCH",
            status_code=409,
        )
    return {
        "response": json.loads(row["response_json"]),
        "status_code": int(row["status_code"]),
        "replayed": True,
    }


async def store_idempotency(
    session: AsyncSession,
    *,
    key: str,
    user_id: str,
    route: str,
    request_hash: str,
    response: dict[str, Any],
    status_code: int = 200,
    ttl_hours: int = 24,
) -> None:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)
    await session.execute(
        text(
            """
            INSERT INTO public.idempotency_requests (
              idempotency_key, user_id, route, request_hash, response_json, status_code, created_at, expires_at
            ) VALUES (
              :key, :user_id, :route, :request_hash, :response_json, :status_code, :created_at, :expires_at
            )
            """
        ),
        {
            "key": key,
            "user_id": user_id,
            "route": route,
            "request_hash": request_hash,
            "response_json": json.dumps(response, default=str),
            "status_code": status_code,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        },
    )
