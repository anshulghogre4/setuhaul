"""Thin AgentCore host. Same run_assistant — no duplicate tools. Used on Runtime only."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from app.assistant.run_assistant import run_assistant
from app.core.execution_context import ExecutionContext
from app.core.settings import DESIGNED_AWS_REGION, assert_region_alignment, get_settings
from app.db.session import db

logger = logging.getLogger(__name__)

# Names only. Values stay in SSM / process env and are never logged.
_SSM_ENV = (
    ("/setuhaul/google-api-key", "GOOGLE_API_KEY"),
    ("/setuhaul/openai-api-key", "OPENAI_API_KEY"),
    ("/setuhaul/upstash-redis-rest-url", "UPSTASH_REDIS_REST_URL"),
    ("/setuhaul/upstash-redis-rest-token", "UPSTASH_REDIS_REST_TOKEN"),
    ("/setuhaul/langsmith-api-key", "LANGSMITH_API_KEY"),
    ("/setuhaul/supabase-url", "SUPABASE_URL"),
    ("/setuhaul/database-url", "DATABASE_URL"),
)

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()
except Exception:  # noqa: BLE001 — FastAPI/local pytest must import this module without the SDK
    app = None  # type: ignore[assignment]


def _hydrate_ssm_into_env() -> int:
    """Copy /setuhaul/* SecureStrings into env. Never prints values."""
    loaded = 0
    missing = [env_key for _, env_key in _SSM_ENV if not (os.environ.get(env_key) or "").strip()]
    if not missing:
        return 0
    try:
        import boto3
    except ImportError:
        logger.warning("ssm hydrate skipped: boto3 missing")
        return 0
    region = (
        os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DESIGNED_AWS_REGION
    ).strip()
    client = boto3.client("ssm", region_name=region)
    for name, env_key in _SSM_ENV:
        if (os.environ.get(env_key) or "").strip():
            continue
        try:
            value = client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
        except Exception:  # noqa: BLE001
            logger.warning("ssm hydrate miss %s", name)
            continue
        if value:
            os.environ[env_key] = value
            loaded += 1
    if not (os.environ.get("LANGSMITH_PROJECT") or "").strip():
        os.environ["LANGSMITH_PROJECT"] = "setuhaul-agentcore"
    get_settings.cache_clear()
    return loaded


def _ensure_db() -> None:
    _hydrate_ssm_into_env()
    settings = get_settings()
    # Same co-location guard as the FastAPI lifespan. AgentCore Runtime never runs that
    # lifespan, so without this call the runtime is the one entrypoint that could drift
    # regions unnoticed — which is exactly what happened (live runtime ARN: us-east-1).
    assert_region_alignment(settings)
    if db.engine is None:
        db.configure(settings)


def _normalize_runtime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept BFF dicts or CLI --prompt-file JSON wrapped as a string prompt."""
    if isinstance(payload.get("execution_context"), dict):
        return payload
    for key in ("prompt", "message", "user_input"):
        raw = payload.get(key)
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text.startswith("{"):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("execution_context"), dict):
            return parsed
    return payload


async def _run_turn(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_runtime_payload(payload)
    message = (payload.get("message") or payload.get("prompt") or payload.get("user_input") or "").strip()
    if not message:
        return {"error": "Provide 'message'."}
    raw_ctx = payload.get("execution_context")
    if not isinstance(raw_ctx, dict):
        return {"error": "Provide verified execution_context from the BFF."}
    ctx = ExecutionContext.model_validate(raw_ctx)
    _ensure_db()
    if db.session_factory is None:
        return {"error": "Database is not configured on the Runtime."}
    settings = get_settings()
    async with db.session_factory() as session:
        return await run_assistant(
            session=session,
            ctx=ctx,
            settings=settings,
            message=message,
            thread_id=payload.get("thread_id"),
            session_id=payload.get("session_id"),
            client_message_id=payload.get("client_message_id"),
        )


if app is not None:

    @app.entrypoint
    async def invoke_agent(payload: dict[str, Any], context: Any) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        try:
            return await _run_turn(body)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AgentCore entrypoint failed")
            return {"error": str(exc)[:300]}


if __name__ == "__main__":
    if app is None:
        raise SystemExit("bedrock-agentcore is not installed. Install it on the Runtime image/CodeZip.")
    app.run()
