from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Coroutine
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.llm import build_chat_model
from app.assistant.observability import (
    TurnLatency,
    attach_run_metrics,
    chat_turn_trace,
    child_invoke_config,
    elapsed_ms,
    model_labels,
    observe_input,
    observe_output,
    tool_outcome_metadata,
)
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

# asyncio keeps only a weak reference to a running task, so a fire-and-forget task can be
# garbage-collected mid-flight. Hold a strong reference until it finishes.
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _json_safe(value: Any) -> str:
    return json.dumps(value, default=str)


def _spawn_background(coro: Coroutine[Any, Any, Any], *, label: str) -> bool:
    """Run post-answer housekeeping off the driver's critical path.

    Used for work whose result the current response does not depend on. Returns False
    when there is no running loop (a synchronous caller), in which case the coroutine is
    closed rather than left un-awaited.
    """

    def _done(task: asyncio.Task[Any]) -> None:
        _BACKGROUND_TASKS.discard(task)
        if task.cancelled():
            logger.warning("background task cancelled: %s", label)
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("background task failed: %s (%s)", label, type(exc).__name__)

    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        coro.close()
        return False
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_done)
    return True


def _configure_langsmith(settings: Settings) -> None:
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        project = (settings.langsmith_project or "setuhaul-agentcore").strip()
        os.environ["LANGSMITH_PROJECT"] = project
        os.environ["LANGCHAIN_PROJECT"] = project


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
    # Per-turn latency accumulator (TECH_STACK.md section 10's six measurements).
    # Started before the first Redis round trip so turn_ms and TTFT cover the whole turn
    # the driver waits on, not just the model calls.
    turn = TurnLatency()

    # One pipelined Upstash round trip for history + summaries + session state,
    # reused below for the duplicate-message check instead of a second fetch.
    turn_context = memory.load_turn_context(user_id=ctx.user_id, thread_id=tid, session_id=sid)
    full_history = turn_context["history"]
    summaries = turn_context["summaries"]
    session_ctx = turn_context["session"]

    if client_message_id and any(
        m.get("client_message_id") == client_message_id for m in full_history
    ):
        last_asst = next((m for m in reversed(full_history) if m.get("role") == "assistant"), None)
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
            "latency": turn.finish(
                ux_state="duplicate_ignored",
                redis_ms=memory.redis_ms,
                redis_ops=memory.redis_ops,
            ),
        }

    # E3.2 (issue #26): a coordinator's take_over_thread sets chat_threads.thread_status =
    # 'ESCALATED' to disable assistant auto-reply on this thread (SOLUTION_DESIGN.md section
    # 7.5.5). Before this epic nothing in the turn path ever read thread_status at all -- the
    # assistant kept auto-replying regardless of a live takeover. Checked once per turn, before
    # any LLM/tool work starts, since an escalated thread should never reach either.
    thread_status_row = (
        await session.execute(
            text("SELECT thread_status FROM public.chat_threads WHERE thread_id = :tid"), {"tid": tid}
        )
    ).mappings().first()
    if thread_status_row is not None and str(thread_status_row["thread_status"]) == "ESCALATED":
        notice = (
            "Your message has been received. An operations coordinator is currently handling "
            "this conversation directly and will respond shortly."
        )
        memory.append_turn(
            user_id=ctx.user_id, thread_id=tid, session_id=sid,
            user_message=message, assistant_message=notice, client_message_id=client_message_id,
        )
        return {
            "thread_id": tid,
            "session_id": sid,
            "response": notice,
            "tool_calls": [],
            "memory_degraded": memory.degraded,
            "memory_degrade_reason": memory.degrade_reason,
            "summary_created": False,
            "duplicate": False,
            "ux_state": "escalated_takeover",
            "latency": turn.finish(
                ux_state="escalated_takeover",
                redis_ms=memory.redis_ms,
                redis_ops=memory.redis_ops,
            ),
        }

    history = full_history[-RAW_CONTEXT_SIZE:]

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
    llm_provider, llm_model = model_labels(base_llm)

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

    turn_config = observe_input(len(history), thread_id=tid, session_id=sid)
    invoke_config = child_invoke_config(turn_config)

    with chat_turn_trace(
        turn_config,
        inputs={"message": message, "thread_id": tid, "session_id": sid},
    ) as run:
        llm_started = time.perf_counter()
        try:
            ai: AIMessage = await llm.ainvoke(messages, config=invoke_config)
        except Exception as exc:  # noqa: BLE001
            turn.record_llm(
                duration_ms=elapsed_ms(llm_started),
                provider=llm_provider,
                model=llm_model,
                hop=0,
                ok=False,
            )
            logger.exception("LLM invoke failed")
            raise AppError(
                "LLM is unavailable. Use deterministic REST actions or retry later.",
                code="LLM_UNAVAILABLE",
                status_code=503,
                detail=str(exc)[:200],
            ) from exc
        turn.record_llm(
            duration_ms=elapsed_ms(llm_started),
            provider=llm_provider,
            model=llm_model,
            hop=0,
            usage=getattr(ai, "usage_metadata", None),
        )

        for round_idx in range(MAX_TOOL_ROUNDS):
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                break
            messages.append(ai)
            turn.note_hop()
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
                    tool_started = time.perf_counter()
                    tool_ok = True
                    try:
                        result = await tool.ainvoke(invoke_args, config=invoke_config)
                    except AppError as exc:
                        tool_ok = False
                        result = json.dumps(
                            {
                                "code": exc.code,
                                "message": exc.message,
                                "detail": exc.detail,
                                "status_code": exc.status_code,
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        tool_ok = False
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

                if tool is not None:
                    # Per-tool DB latency, measured at the call site: every driver tool is
                    # a typed PostgreSQL read, and the tool layer itself is out of scope.
                    turn.record_tool(
                        tool=str(name or "unknown"),
                        duration_ms=elapsed_ms(tool_started),
                        ok=tool_ok,
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

            llm_started = time.perf_counter()
            try:
                invoke_config = child_invoke_config(
                    turn_config,
                    extra_metadata=tool_outcome_metadata(observed_tools, ux_state),
                )
                ai = await llm.ainvoke(messages, config=invoke_config)
            except Exception as exc:  # noqa: BLE001
                turn.record_llm(
                    duration_ms=elapsed_ms(llm_started),
                    provider=llm_provider,
                    model=llm_model,
                    hop=round_idx + 1,
                    ok=False,
                )
                raise AppError(
                    "LLM failed during tool loop.",
                    code="LLM_UNAVAILABLE",
                    status_code=503,
                    detail=str(exc)[:200],
                ) from exc
            turn.record_llm(
                duration_ms=elapsed_ms(llm_started),
                provider=llm_provider,
                model=llm_model,
                hop=round_idx + 1,
                usage=getattr(ai, "usage_metadata", None),
            )

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
        # known_message_count avoids a separate LLEN round trip: full_history was the
        # pre-append count, and append_turn just pushed exactly 2 more messages.
        #
        # Deliberately NOT awaited: a full extra LLM inference plus six Upstash round
        # trips, on roughly one turn in three, entirely after the driver's answer
        # already exists. The summary is only read by the *next* turn, so awaiting it
        # spent ~1.9 s of a 2.5 s per-turn budget (NFR-002) on housekeeping. If the task
        # is lost to a container recycle, the next turn crosses the threshold again and
        # retries.
        summary_scheduled = _spawn_background(
            memory.maybe_summarize_history(
                user_id=ctx.user_id,
                thread_id=tid,
                session_id=sid,
                llm=base_llm,
                known_message_count=len(full_history) + 2,
            ),
            label="maybe_summarize_history",
        )

        latency = turn.finish(
            ux_state=ux_state,
            redis_ms=memory.redis_ms,
            redis_ops=memory.redis_ops,
        )
        # The same numbers on the LangSmith parent run: with no OTEL distro outside
        # AgentCore, the trace is where these are actually readable today.
        attach_run_metrics(
            run, latency, outputs={"response": content, "ux_state": ux_state}
        )
        observe_output(content)

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
            # Summarisation now runs in the background, so the turn cannot report whether a
            # summary was written — only that one was scheduled. Key kept for wire compat.
            "summary_created": False,
            "summary_scheduled": summary_scheduled,
            "ux_state": ux_state,
            "confirmation": confirmation_payload,
            "duplicate": False,
            "latency": latency,
        }
