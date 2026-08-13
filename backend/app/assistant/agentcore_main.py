"""Thin AgentCore host. Same run_assistant — no duplicate tools. Used on Runtime only."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.assistant.run_assistant import run_assistant
from app.core.execution_context import ExecutionContext
from app.core.settings import get_settings
from app.db.session import db

logger = logging.getLogger(__name__)

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()
except Exception:  # noqa: BLE001 — FastAPI/local pytest must import this module without the SDK
    app = None  # type: ignore[assignment]


def _ensure_db() -> None:
    settings = get_settings()
    if db.engine is None:
        db.configure(settings)


async def _run_turn(payload: dict[str, Any]) -> dict[str, Any]:
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
    def invoke_agent(payload: dict[str, Any], context: Any) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        try:
            return asyncio.run(_run_turn(body))
        except Exception as exc:  # noqa: BLE001
            logger.exception("AgentCore entrypoint failed")
            return {"error": str(exc)[:300]}


if __name__ == "__main__":
    if app is None:
        raise SystemExit("bedrock-agentcore is not installed. Install it on the Runtime image/CodeZip.")
    app.run()
