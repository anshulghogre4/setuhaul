from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.llm import build_chat_model
from app.assistant.prompts import SYSTEM_PROMPT
from app.assistant.tools import build_driver_tools
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import Settings
from app.services.redis_memory import ConversationMemory

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


def _configure_langsmith(settings: Settings) -> None:
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", "setuhaul-sprint2")


async def run_assistant(
    *,
    session: AsyncSession,
    ctx: ExecutionContext,
    settings: Settings,
    message: str,
    thread_id: str | None = None,
    client_message_id: str | None = None,
) -> dict[str, Any]:
    """Bounded ChatOpenAI.bind_tools invoke loop (NOT create_agent / AgentExecutor)."""
    if not ctx.is_driver:
        raise AppError("Chat is driver-scoped in Sprint 2 POC.", code="FORBIDDEN", status_code=403)
    if not settings.ready_llm:
        raise AppError(
            "No LLM API key configured. Set OPENAI_API_KEY, OPENROUTER_API_KEY, or GOOGLE_API_KEY.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )

    _configure_langsmith(settings)
    tid = thread_id or f"THR-LIVE-{ctx.driver_id}-{uuid4().hex[:8].upper()}"
    memory = ConversationMemory(settings)

    if client_message_id and memory.seen_client_message(
        user_id=ctx.user_id, thread_id=tid, client_message_id=client_message_id
    ):
        history = memory.load_history(user_id=ctx.user_id, thread_id=tid)
        last_asst = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
        return {
            "thread_id": tid,
            "response": (last_asst or {}).get("content") or "Duplicate message ignored.",
            "tool_calls": [],
            "memory_degraded": memory.degraded,
            "memory_degrade_reason": memory.degrade_reason,
            "duplicate": True,
            "ux_state": "duplicate_ignored",
        }

    history = memory.load_history(user_id=ctx.user_id, thread_id=tid)
    session_ctx = memory.load_session(user_id=ctx.user_id, thread_id=tid)

    tools = build_driver_tools(session=session, ctx=ctx, thread_id=tid)
    tool_map = {t.name: t for t in tools}

    llm = build_chat_model(settings).bind_tools(tools)

    messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT)]
    if session_ctx:
        messages.append(
            SystemMessage(
                content="Structured session context (non-authoritative): "
                + json.dumps(session_ctx, default=str)[:2000]
            )
        )
    for turn in history[-20:]:
        role = turn.get("role")
        content = str(turn.get("content") or "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=message))

    observed_tools: list[dict[str, Any]] = []
    ux_state = "answered"
    confirmation_payload: dict[str, Any] | None = None

    try:
        ai: AIMessage = await llm.ainvoke(messages)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM invoke failed")
        raise AppError(
            "LLM is unavailable. Use deterministic REST actions or retry later.",
            code="LLM_UNAVAILABLE",
            status_code=503,
            detail=str(exc)[:200],
        ) from exc

    for _ in range(MAX_TOOL_ROUNDS):
        tool_calls = getattr(ai, "tool_calls", None) or []
        if not tool_calls:
            break
        messages.append(ai)
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {}) or {}
            tool = tool_map.get(name or "")
            if tool is None:
                result = json.dumps({"code": "UNKNOWN_TOOL", "message": f"Tool {name} not allowed."})
            else:
                try:
                    result = await tool.ainvoke(args)
                except Exception as exc:  # noqa: BLE001
                    result = json.dumps({"code": "TOOL_ERROR", "message": str(exc)[:300]})

            observed_tools.append({"name": name, "args": args, "result_preview": str(result)[:400]})
            try:
                parsed = json.loads(result) if isinstance(result, str) else result
                if isinstance(parsed, dict):
                    code = parsed.get("code") or parsed.get("status")
                    if code == "CONFIRMATION_REQUIRED":
                        ux_state = "confirmation_required"
                        confirmation_payload = parsed
                    elif code == "REPAIR_IS_NOT_ETA":
                        ux_state = "clarification_required"
                    elif code == "CAPABILITY_NOT_ENABLED":
                        ux_state = "capability_not_enabled"
                    elif parsed.get("status") == "PERSISTED":
                        ux_state = "persisted_success"
            except (TypeError, json.JSONDecodeError):
                pass

            messages.append(ToolMessage(content=str(result), tool_call_id=call_id or name or "tool"))

        try:
            ai = await llm.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                "LLM failed during tool loop.",
                code="LLM_UNAVAILABLE",
                status_code=503,
                detail=str(exc)[:200],
            ) from exc

    content = ai.content if isinstance(ai.content, str) else json.dumps(ai.content)
    new_session = {
        "driver_id": ctx.driver_id,
        "last_intent": observed_tools[-1]["name"] if observed_tools else "chat",
        "thread_id": tid,
        "ux_state": ux_state,
    }
    if confirmation_payload and confirmation_payload.get("shipment_id"):
        new_session["pending_shipment_id"] = confirmation_payload.get("shipment_id")
        new_session["pending_eta_ts"] = confirmation_payload.get("declared_eta_ts")

    memory.append_turn(
        user_id=ctx.user_id,
        thread_id=tid,
        user_message=message,
        assistant_message=content,
        session=new_session,
        client_message_id=client_message_id,
    )

    return {
        "thread_id": tid,
        "response": content,
        "tool_calls": [{"name": t["name"], "args": t["args"]} for t in observed_tools],
        "memory_degraded": memory.degraded,
        "memory_degrade_reason": memory.degrade_reason,
        "ux_state": ux_state,
        "confirmation": confirmation_payload,
        "duplicate": False,
    }
