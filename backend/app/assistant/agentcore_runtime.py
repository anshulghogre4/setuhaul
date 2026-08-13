"""BFF → AgentCore invoke. Used only when AGENTCORE_RUNTIME_ARN is set (hosted step 9)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import Settings

logger = logging.getLogger(__name__)

_SESSION_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def runtime_session_id(user_id: str, session_id: str) -> str:
    """Sticky AgentCore session from verified identity + browser session. Not a JWT/role."""
    raw = f"setuhaul-{user_id}-{session_id}"
    cleaned = _SESSION_SAFE.sub("-", raw).strip("-") or "setuhaul-session"
    if len(cleaned) < 33:
        cleaned = cleaned + ("0" * (33 - len(cleaned)))
    return cleaned[:256]


def _region_from_arn(arn: str, fallback: str) -> str:
    parts = arn.split(":")
    if len(parts) >= 4 and parts[3]:
        return parts[3]
    return fallback


async def invoke_agentcore(
    *,
    settings: Settings,
    ctx: ExecutionContext,
    message: str,
    thread_id: str | None,
    session_id: str | None,
    client_message_id: str | None,
) -> dict[str, Any]:
    """JWT already verified by FastAPI. Payload is ExecutionContext fields + chat ids."""
    arn = (settings.agentcore_runtime_arn or "").strip()
    if not arn:
        raise AppError(
            "AgentCore runtime is not configured.",
            code="AGENTCORE_UNAVAILABLE",
            status_code=503,
        )
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise AppError(
            "boto3 is required to invoke AgentCore.",
            code="AGENTCORE_UNAVAILABLE",
            status_code=503,
        ) from exc

    sid = session_id or ""
    session = runtime_session_id(ctx.user_id, sid)
    payload = {
        "message": message,
        "thread_id": thread_id,
        "session_id": sid,
        "client_message_id": client_message_id,
        "execution_context": ctx.model_dump(mode="json"),
    }
    region = _region_from_arn(arn, settings.aws_region)
    client = boto3.client(
        "bedrock-agentcore",
        region_name=region,
        config=Config(connect_timeout=10, read_timeout=180, retries={"max_attempts": 0}),
    )
    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            runtimeSessionId=session,
            qualifier="DEFAULT",
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(payload).encode("utf-8"),
        )
        stream = response.get("response")
        if hasattr(stream, "read"):
            raw = stream.read()
        else:
            raw = b"".join(stream or [])
        body = json.loads(raw.decode("utf-8"))
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentCore invoke failed")
        raise AppError(
            "Assistant runtime is unavailable. Retry or use local in-process chat.",
            code="AGENTCORE_UNAVAILABLE",
            status_code=503,
            detail=str(exc)[:200],
        ) from exc

    if isinstance(body, dict) and body.get("error"):
        raise AppError(
            str(body.get("error")),
            code="AGENTCORE_ERROR",
            status_code=502,
        )
    if not isinstance(body, dict):
        raise AppError(
            "AgentCore returned an unexpected payload.",
            code="AGENTCORE_ERROR",
            status_code=502,
        )
    return body
