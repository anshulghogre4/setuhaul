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
from app.services.redis_memory import (
    RAW_CONTEXT_SIZE,
    ConversationMemory,
    normalize_memory_id,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


def _json_safe(value: Any) -> str:
    return json.dumps(value, default=str)


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
    session_id: str | None = None,
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
    sid = normalize_memory_id(session_id) if session_id else f"SES-LIVE-{uuid4().hex[:12].upper()}"
    memory = ConversationMemory(settings)

    if client_message_id and memory.seen_client_message(
        user_id=ctx.user_id,
        thread_id=tid,
        session_id=sid,
        client_message_id=client_message_id,
    ):
        history = memory.load_history(user_id=ctx.user_id, thread_id=tid, session_id=sid)
        last_asst = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
        return {
            "thread_id": tid,
            "session_id": sid,
            "response": (last_asst or {}).get("content") or "Duplicate message ignored.",
            "tool_calls": [],
            "memory_degraded": memory.degraded,
            "memory_degrade_reason": memory.degrade_reason,
            "summary_created": False,
            "duplicate": True,
            "ux_state": "duplicate_ignored",
        }

    history = memory.load_history(
        user_id=ctx.user_id, thread_id=tid, session_id=sid, limit=RAW_CONTEXT_SIZE
    )
    summaries = memory.load_summaries(user_id=ctx.user_id, thread_id=tid, session_id=sid)
    session_ctx = memory.load_session(user_id=ctx.user_id, thread_id=tid, session_id=sid)

    tools = build_driver_tools(
        session=session,
        ctx=ctx,
        thread_id=tid,
        session_id=sid,
        memory=memory,
        client_message_id=client_message_id,
    )
    tool_map = {t.name: t for t in tools}

    base_llm = build_chat_model(settings)
    llm = base_llm.bind_tools(tools)

    messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT)]
    if summaries:
        summary_block = "\n\n".join(
            f"Summary {index}: {text}" for index, text in enumerate(summaries, start=1)
        )
        messages.append(
            SystemMessage(
                content=(
                    "Earlier conversation summaries (non-authoritative Redis memory; "
                    "verify operational facts with PostgreSQL-backed tools):\n\n"
                    + summary_block[:3000]
                )
            )
        )
    if session_ctx:
        messages.append(
            SystemMessage(
                content="Structured session context (non-authoritative): "
                + json.dumps(session_ctx, default=str)[:2000]
            )
        )
    for turn in history:
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

    for round_idx in range(MAX_TOOL_ROUNDS):
        tool_calls = getattr(ai, "tool_calls", None) or []
        if not tool_calls:
            break
        messages.append(ai)
        should_break_after_round = False
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {}) or {}
            tool = tool_map.get(name or "")
            if tool is None:
                result = json.dumps({"code": "UNKNOWN_TOOL", "message": f"Tool {name} not allowed."})
            else:
                invoke_args = args
                schema = getattr(tool, "args_schema", None)
                if isinstance(args, dict) and schema is not None:
                    allowed = set(getattr(schema, "model_fields", {}) or {})
                    if allowed:
                        invoke_args = {key: value for key, value in args.items() if key in allowed}
                try:
                    result = await tool.ainvoke(invoke_args)
                except AppError as exc:
                    result = json.dumps(
                        {
                            "code": exc.code,
                            "message": exc.message,
                            "detail": exc.detail,
                            "status_code": exc.status_code,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    result = json.dumps(
                        {
                            "code": "TOOL_ERROR",
                            "message": str(exc)[:300],
                            "args_received": args if isinstance(args, dict) else {"raw": str(args)[:200]},
                            "args_invoked": invoke_args
                            if isinstance(invoke_args, dict)
                            else {"raw": str(invoke_args)[:200]},
                        }
                    )

            result_text = result if isinstance(result, str) else _json_safe(result)
            try:
                parsed = json.loads(result_text) if isinstance(result_text, str) else result_text
            except (TypeError, json.JSONDecodeError):
                parsed = {"raw": str(result_text)[:2000]}

            observed_tools.append(
                {
                    "name": name,
                    "args": args,
                    "result": parsed if isinstance(parsed, (dict, list)) else {"raw": str(parsed)[:2000]},
                    "result_preview": str(result_text)[:800],
                }
            )
            try:
                if isinstance(parsed, dict):
                    code = parsed.get("code") or parsed.get("status")
                    if code == "CONFIRMATION_REQUIRED":
                        ux_state = "confirmation_required"
                        confirmation_payload = parsed
                        should_break_after_round = True
                    elif code == "REPAIR_IS_NOT_ETA":
                        ux_state = "clarification_required"
                        should_break_after_round = True
                    elif code == "CAPABILITY_NOT_ENABLED":
                        ux_state = "capability_not_enabled"
                    elif parsed.get("status") == "PERSISTED":
                        ux_state = "persisted_success"
                        confirmation_payload = parsed
                        should_break_after_round = True
            except (TypeError, json.JSONDecodeError, AttributeError):
                pass

            messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id or name or "tool"))

        if should_break_after_round:
            break

        try:
            ai = await llm.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                "LLM failed during tool loop.",
                code="LLM_UNAVAILABLE",
                status_code=503,
                detail=str(exc)[:200],
            ) from exc

    raw_content = ai.content if isinstance(ai.content, str) else json.dumps(ai.content)
    content = raw_content.strip()
    if not content or ux_state in ("confirmation_required", "clarification_required"):
        if observed_tools:
            last_tool = observed_tools[-1]
            try:
                res_dict = json.loads(last_tool.get("result_preview") or "{}")
                if isinstance(res_dict, dict) and res_dict.get("code") == "CONFIRMATION_REQUIRED":
                    shipment_id = res_dict.get("shipment_id") or "your shipment"
                    display_eta = res_dict.get("display_eta") or res_dict.get("declared_eta_ts")
                    content = f"Please confirm that you want to update the ETA for shipment {shipment_id} to {display_eta}."
                elif isinstance(res_dict, dict) and res_dict.get("code") == "REPAIR_IS_NOT_ETA":
                    content = res_dict.get("message") or "Repair duration is not an arrival ETA. Please declare an explicit arrival date and time."
                elif isinstance(res_dict, dict) and res_dict.get("message"):
                    content = str(res_dict["message"])
                elif isinstance(res_dict, dict) and res_dict.get("status") == "PERSISTED":
                    shipment_id = res_dict.get("shipment_id") or "shipment"
                    eta_ts = res_dict.get("declared_eta_ts") or ""
                    content = f"ETA update for {shipment_id} ({eta_ts}) has been confirmed and saved successfully."
                elif isinstance(res_dict, dict) and res_dict.get("feasible_slots"):
                    slots = res_dict["feasible_slots"]
                    content = f"Found {len(slots)} feasible dock slot options for your shipment."
                else:
                    content = f"Operation for {last_tool['name']} completed successfully."
            except Exception:
                content = "Operational request processed successfully."
        else:
            content = "Hello! I am your SetuHaul Logistics Assistant. How can I help you today?"
    new_session = {
        "driver_id": ctx.driver_id,
        "last_intent": observed_tools[-1]["name"] if observed_tools else "chat",
        "thread_id": tid,
        "session_id": sid,
        "ux_state": ux_state,
    }
    if confirmation_payload and confirmation_payload.get("shipment_id"):
        new_session["pending_shipment_id"] = confirmation_payload.get("shipment_id")
        new_session["pending_eta_ts"] = confirmation_payload.get("declared_eta_ts")

    memory.append_turn(
        user_id=ctx.user_id,
        thread_id=tid,
        session_id=sid,
        user_message=message,
        assistant_message=content,
        session=new_session,
        client_message_id=client_message_id,
    )
    # Rolling summary of oldest raw turns when the thread grows (ERICA-style).
    new_summary = await memory.maybe_summarize_history(
        user_id=ctx.user_id,
        thread_id=tid,
        session_id=sid,
        llm=base_llm,
    )

    return {
        "thread_id": tid,
        "session_id": sid,
        "response": content,
        "tool_calls": [
            {
                "name": t["name"],
                "args": t["args"],
                "result": t.get("result"),
                "result_preview": t.get("result_preview"),
            }
            for t in observed_tools
        ],
        "memory_degraded": memory.degraded,
        "memory_degrade_reason": memory.degrade_reason,
        "summary_created": new_summary is not None,
        "ux_state": ux_state,
        "confirmation": confirmation_payload,
        "duplicate": False,
    }
