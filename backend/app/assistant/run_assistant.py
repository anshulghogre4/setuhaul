from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Coroutine
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
from app.db.session import release_transaction
from app.services import driver_reads
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


@dataclass
class TurnState:
    """Mutable state threaded through a turn's tool rounds.

    Shared by both entrypoints (`run_assistant`, `stream_assistant_turn`) so the two paths make
    identical decisions from one definition, not two independently-maintained copies of the same
    branching logic.
    """

    observed_tools: list[dict[str, Any]] = field(default_factory=list)
    ux_state: str = "answered"
    confirmation_payload: dict[str, Any] | None = None


@dataclass
class PreparedTurn:
    """Everything both entrypoints need once setup has run and the turn is ready for the LLM
    loop. `_prepare_turn` returns this, or a plain `dict` (see its docstring) when the turn must
    return immediately without ever reaching the LLM."""

    tid: str
    sid: str
    memory: ConversationMemory
    turn: TurnLatency
    full_history: list[dict[str, Any]]
    tools: list[Any]
    tool_map: dict[str, Any]
    base_llm: Any
    llm: Any
    llm_provider: str
    llm_model: str
    messages: list[Any]
    turn_config: Any


async def _prepare_turn(
    *,
    session: AsyncSession,
    ctx: ExecutionContext,
    settings: Settings,
    message: str,
    thread_id: str | None,
    session_id: str | None,
    client_message_id: str | None,
) -> PreparedTurn | dict[str, Any]:
    """Shared setup: identity/settings checks, thread resolution, Redis history load, the
    duplicate-message and escalated-thread-takeover early-return checks, the E4.3 lever-1
    operational-context prefetch (issue #33), and tool/message assembly.

    Returns a plain `dict` -- already the exact shape `run_assistant`/`stream_assistant_turn`
    return to their own caller -- when the turn must end immediately without ever reaching the
    LLM. Both callers must check `isinstance(prepared, dict)` before touching anything else.
    """
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
    turn_context = await memory.load_turn_context(user_id=ctx.user_id, thread_id=tid, session_id=sid)
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
    # 7.5.5). Checked once per turn, before any LLM/tool work starts, since an escalated thread
    # should never reach either.
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
        await memory.append_turn(
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

    # E4.3 lever 1 (issue #33): prefetch operational context instead of making the model spend a
    # tool round trip on it -- one hop costs two LLM inferences (deciding to call the tool, then
    # writing the answer) plus five DB round trips (TECH_STACK.md section 10). tools.py's own
    # docstring already claimed this was prefetched (E3.1); it was not, until now. Degrades
    # gracefully rather than failing the turn: a prefetch error just means the model falls back to
    # calling get_driver_operational_context itself, which is still on the tool allowlist.
    try:
        prefetched_context = await driver_reads.get_driver_operational_context(session, ctx)
        messages.append(
            SystemMessage(
                content=(
                    "Driver operational context (PostgreSQL-backed, prefetched for this turn -- "
                    "shipments, current appointment, latest ETA, facility): "
                    + json.dumps(prefetched_context, default=str)[:4000]
                )
            )
        )
    except Exception:  # noqa: BLE001 -- prefetch is an optimization, never a hard turn dependency
        logger.warning("Operational-context prefetch failed; model will fall back to the tool call", exc_info=True)
    finally:
        # E4.4 (issue #34): close the prefetch's own transaction before the LLM think-time
        # starts, rather than holding the pooled connection idle-in-transaction across it.
        await release_transaction(session)

    if summaries:
        summary_block = "\n\n".join(
            f"Summary {index}: {text_}" for index, text_ in enumerate(summaries, start=1)
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
    # `hist_turn`, deliberately not `turn`: this loop previously reused the outer `turn =
    # TurnLatency()` binding (Python `for` targets are not block-scoped), which meant every
    # thread's *second* message onward silently replaced the latency tracker with a plain history
    # dict -- the next `turn.record_llm(...)` call then raised `AttributeError` and crashed the
    # request. Confirmed live in the last-pushed commit, invisible to every existing test because
    # they all use an empty `history` fixture. Fixed here by simply not shadowing the name.
    for hist_turn in history:
        role = hist_turn.get("role")
        content = str(hist_turn.get("content") or "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=message))

    turn_config = observe_input(len(history), thread_id=tid, session_id=sid)

    return PreparedTurn(
        tid=tid, sid=sid, memory=memory, turn=turn, full_history=full_history,
        tools=tools, tool_map=tool_map, base_llm=base_llm, llm=llm,
        llm_provider=llm_provider, llm_model=llm_model, messages=messages, turn_config=turn_config,
    )


async def _execute_tool_round(
    *,
    session: AsyncSession,
    tool_calls: list[Any],
    tool_map: dict[str, Any],
    invoke_config: Any,
    state: TurnState,
    turn: TurnLatency,
) -> tuple[list[ToolMessage], bool]:
    """Run one round's tool calls against `tool_map`, mutating `state` exactly as the loop always
    has (unknown-tool handling, error shaping, `observed_tools`, and the `ux_state`/
    `confirmation_payload` transitions for CONFIRMATION_REQUIRED/REPAIR_IS_NOT_ETA/
    CAPABILITY_NOT_ENABLED/PERSISTED). Returns the `ToolMessage`s to append to the conversation and
    whether the round should end the loop early (a confirmation gate or a persisted write).
    """
    tool_messages: list[ToolMessage] = []
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
                    {"code": exc.code, "message": exc.message, "detail": exc.detail, "status_code": exc.status_code}
                )
            except Exception as exc:  # noqa: BLE001
                tool_ok = False
                result = json.dumps(
                    {
                        "code": "TOOL_ERROR",
                        "message": str(exc)[:300],
                        "args_received": args if isinstance(args, dict) else {"raw": str(args)[:200]},
                        "args_invoked": invoke_args if isinstance(invoke_args, dict) else {"raw": str(invoke_args)[:200]},
                    }
                )

        if tool is not None:
            # Per-tool DB latency, measured at the call site: every driver tool is
            # a typed PostgreSQL read, and the tool layer itself is out of scope.
            turn.record_tool(tool=str(name or "unknown"), duration_ms=elapsed_ms(tool_started), ok=tool_ok)
            # E4.4 (issue #34): close this tool's own transaction now, not whenever the next DB
            # operation or the request happens to run -- a write tool already commits itself, so
            # this is a no-op there; a read tool never does, which is the actual gap this closes.
            await release_transaction(session)

        result_text = result if isinstance(result, str) else _json_safe(result)
        try:
            parsed = json.loads(result_text) if isinstance(result_text, str) else result_text
        except (TypeError, json.JSONDecodeError):
            parsed = {"raw": str(result_text)[:2000]}

        state.observed_tools.append(
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
                    state.ux_state = "confirmation_required"
                    state.confirmation_payload = parsed
                    should_break_after_round = True
                elif code == "REPAIR_IS_NOT_ETA":
                    state.ux_state = "clarification_required"
                    should_break_after_round = True
                elif code == "CAPABILITY_NOT_ENABLED":
                    state.ux_state = "capability_not_enabled"
                elif parsed.get("status") == "PERSISTED":
                    state.ux_state = "persisted_success"
                    state.confirmation_payload = parsed
                    should_break_after_round = True
        except (TypeError, json.JSONDecodeError, AttributeError):
            pass

        tool_messages.append(ToolMessage(content=str(result_text), tool_call_id=call_id or name or "tool"))

    return tool_messages, should_break_after_round


def _extract_text(content: Any) -> str:
    """Text from a message's `.content`, whichever shape the provider returned.

    E4.1 (issue #31): `langchain-core` 1.x introduced a standard content-blocks format
    (`str | list[str | dict]`, each dict typically `{"type": "text", "text": ...}` alongside
    non-text blocks like reasoning/tool-use) alongside the older plain-`str` shape -- and
    TECH_STACK.md section 7's own spike notes this explicitly: "the 4.x message-content shape
    differs (content blocks, not a plain string), so any code reading `.content` directly needs
    checking." Which shape `gemini-3.7-flash` actually returns via Vertex AI cannot be confirmed
    without live GCP credentials (this issue's own blocker), so this handles both defensively --
    a plain string unchanged, a content-blocks list by concatenating each block's own text (a
    `str` entry or a `{"type": "text", ...}` dict; anything else, e.g. a reasoning block, is
    skipped, not stringified into visible output). Falls back to `""` for anything else rather
    than surfacing a raw `repr`/JSON dump to the driver.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _finalize_content(ai: AIMessage, state: TurnState) -> str:
    """The content-fallback logic: what the driver actually sees when the model's own `content`
    is empty (common right after a tool call) or the loop broke on a confirmation/clarification
    gate."""
    content = _extract_text(ai.content).strip()
    if content and state.ux_state not in ("confirmation_required", "clarification_required"):
        return content
    if not state.observed_tools:
        return "Hello! I am your SetuHaul Logistics Assistant. How can I help you today?"
    last_tool = state.observed_tools[-1]
    try:
        res_dict = json.loads(last_tool.get("result_preview") or "{}")
        if isinstance(res_dict, dict) and res_dict.get("code") == "CONFIRMATION_REQUIRED":
            shipment_id = res_dict.get("shipment_id") or "your shipment"
            display_eta = res_dict.get("display_eta") or res_dict.get("declared_eta_ts")
            return f"Please confirm that you want to update the ETA for shipment {shipment_id} to {display_eta}."
        if isinstance(res_dict, dict) and res_dict.get("code") == "REPAIR_IS_NOT_ETA":
            return res_dict.get("message") or "Repair duration is not an arrival ETA. Please declare an explicit arrival date and time."
        if isinstance(res_dict, dict) and res_dict.get("message"):
            return str(res_dict["message"])
        if isinstance(res_dict, dict) and res_dict.get("status") == "PERSISTED":
            shipment_id = res_dict.get("shipment_id") or "shipment"
            eta_ts = res_dict.get("declared_eta_ts") or ""
            return f"ETA update for {shipment_id} ({eta_ts}) has been confirmed and saved successfully."
        if isinstance(res_dict, dict) and res_dict.get("feasible_slots"):
            slots = res_dict["feasible_slots"]
            return f"Found {len(slots)} feasible dock slot options for your shipment."
        return f"Operation for {last_tool['name']} completed successfully."
    except Exception:
        return "Operational request processed successfully."


async def _persist_and_build_result(
    *,
    prepared: PreparedTurn,
    ctx: ExecutionContext,
    message: str,
    client_message_id: str | None,
    state: TurnState,
    content: str,
    run: Any,
) -> dict[str, Any]:
    """Shared tail: Redis persistence, background summarisation scheduling, latency/tracing
    attachment, and the final response dict -- identical shape whether the turn was blocking or
    streamed."""
    new_session: dict[str, Any] = {
        "driver_id": ctx.driver_id,
        "last_intent": state.observed_tools[-1]["name"] if state.observed_tools else "chat",
        "thread_id": prepared.tid,
        "session_id": prepared.sid,
        "ux_state": state.ux_state,
    }
    if state.confirmation_payload and state.confirmation_payload.get("shipment_id"):
        new_session["pending_shipment_id"] = state.confirmation_payload.get("shipment_id")
        new_session["pending_eta_ts"] = state.confirmation_payload.get("declared_eta_ts")

    await prepared.memory.append_turn(
        user_id=ctx.user_id,
        thread_id=prepared.tid,
        session_id=prepared.sid,
        user_message=message,
        assistant_message=content,
        session=new_session,
        client_message_id=client_message_id,
    )
    # Rolling summary of oldest raw turns when the thread grows (ERICA-style). Deliberately NOT
    # awaited -- see the original inline comment history for why (a full extra LLM inference plus
    # six Upstash round trips, entirely after the driver's answer already exists).
    summary_scheduled = _spawn_background(
        prepared.memory.maybe_summarize_history(
            user_id=ctx.user_id,
            thread_id=prepared.tid,
            session_id=prepared.sid,
            llm=prepared.base_llm,
            known_message_count=len(prepared.full_history) + 2,
        ),
        label="maybe_summarize_history",
    )

    latency = prepared.turn.finish(
        ux_state=state.ux_state,
        redis_ms=prepared.memory.redis_ms,
        redis_ops=prepared.memory.redis_ops,
    )
    # The same numbers on the LangSmith parent run: with no OTEL distro outside
    # AgentCore, the trace is where these are actually readable today.
    attach_run_metrics(run, latency, outputs={"response": content, "ux_state": state.ux_state})
    observe_output(content)

    return {
        "thread_id": prepared.tid,
        "session_id": prepared.sid,
        "response": content,
        "tool_calls": [
            {
                "name": t["name"],
                "args": t["args"],
                "result": t.get("result"),
                "result_preview": t.get("result_preview"),
            }
            for t in state.observed_tools
        ],
        "memory_degraded": prepared.memory.degraded,
        "memory_degrade_reason": prepared.memory.degrade_reason,
        # Summarisation now runs in the background, so the turn cannot report whether a
        # summary was written -- only that one was scheduled. Key kept for wire compat.
        "summary_created": False,
        "summary_scheduled": summary_scheduled,
        "ux_state": state.ux_state,
        "confirmation": state.confirmation_payload,
        "duplicate": False,
        "latency": latency,
    }


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
    prepared = await _prepare_turn(
        session=session, ctx=ctx, settings=settings, message=message, thread_id=thread_id,
        session_id=session_id, client_message_id=client_message_id,
    )
    if isinstance(prepared, dict):
        return prepared

    try:
        return await asyncio.wait_for(
            _run_assistant_loop(
                session=session, prepared=prepared, ctx=ctx, message=message,
                client_message_id=client_message_id,
            ),
            timeout=settings.turn_deadline_seconds,
        )
    except asyncio.TimeoutError as exc:
        # E4.4 (issue #34): the per-call `llm_call_timeout_seconds` bounds one provider round
        # trip; this bounds the whole turn (prefetch already ran, so this covers every LLM/tool
        # call across every round) -- a provider that times out on every retry inside
        # MAX_TOOL_ROUNDS still can't hang the request past a hard wall clock.
        raise AppError(
            "The assistant did not respond in time. Retry, or use deterministic REST actions.",
            code="TURN_DEADLINE_EXCEEDED", status_code=504,
        ) from exc


async def _run_assistant_loop(
    *, session: AsyncSession, prepared: PreparedTurn, ctx: ExecutionContext, message: str,
    client_message_id: str | None,
) -> dict[str, Any]:
    state = TurnState()
    invoke_config = child_invoke_config(prepared.turn_config)

    with chat_turn_trace(
        prepared.turn_config,
        inputs={"message": message, "thread_id": prepared.tid, "session_id": prepared.sid},
    ) as run:
        llm_started = time.perf_counter()
        try:
            ai: AIMessage = await prepared.llm.ainvoke(prepared.messages, config=invoke_config)
        except Exception as exc:  # noqa: BLE001
            prepared.turn.record_llm(
                duration_ms=elapsed_ms(llm_started), provider=prepared.llm_provider,
                model=prepared.llm_model, hop=0, ok=False,
            )
            logger.exception("LLM invoke failed")
            raise AppError(
                "LLM is unavailable. Use deterministic REST actions or retry later.",
                code="LLM_UNAVAILABLE", status_code=503, detail=str(exc)[:200],
            ) from exc
        prepared.turn.record_llm(
            duration_ms=elapsed_ms(llm_started), provider=prepared.llm_provider,
            model=prepared.llm_model, hop=0, usage=getattr(ai, "usage_metadata", None),
        )

        for round_idx in range(MAX_TOOL_ROUNDS):
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                break
            prepared.messages.append(ai)
            prepared.turn.note_hop()

            tool_messages, should_break_after_round = await _execute_tool_round(
                session=session, tool_calls=tool_calls, tool_map=prepared.tool_map,
                invoke_config=invoke_config, state=state, turn=prepared.turn,
            )
            prepared.messages.extend(tool_messages)

            if should_break_after_round:
                break

            llm_started = time.perf_counter()
            try:
                invoke_config = child_invoke_config(
                    prepared.turn_config,
                    extra_metadata=tool_outcome_metadata(state.observed_tools, state.ux_state),
                )
                ai = await prepared.llm.ainvoke(prepared.messages, config=invoke_config)
            except Exception as exc:  # noqa: BLE001
                prepared.turn.record_llm(
                    duration_ms=elapsed_ms(llm_started), provider=prepared.llm_provider,
                    model=prepared.llm_model, hop=round_idx + 1, ok=False,
                )
                raise AppError(
                    "LLM failed during tool loop.", code="LLM_UNAVAILABLE", status_code=503,
                    detail=str(exc)[:200],
                ) from exc
            prepared.turn.record_llm(
                duration_ms=elapsed_ms(llm_started), provider=prepared.llm_provider,
                model=prepared.llm_model, hop=round_idx + 1, usage=getattr(ai, "usage_metadata", None),
            )

        content = _finalize_content(ai, state)
        return await _persist_and_build_result(
            prepared=prepared, ctx=ctx, message=message, client_message_id=client_message_id,
            state=state, content=content, run=run,
        )


async def stream_assistant_turn(
    *,
    session: AsyncSession,
    ctx: ExecutionContext,
    settings: Settings,
    message: str,
    thread_id: str | None = None,
    session_id: str | None = None,
    client_message_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """E4.3 lever 3 (issue #33): SSE-shaped generator, additive alongside `run_assistant` per the
    issue's own rollback note ("ship it behind the existing non-streaming path"). `/chat` and
    `/chat/message` are untouched; this backs a new `/chat/stream` endpoint only.

    Yields `{"event": ..., "data": ...}` dicts (the router formats these as SSE frames):
    - `start` once, with `thread_id`/`session_id` -- the first bytes sent, so TTFT is measurable.
    - `token` for each non-empty content delta as the model generates it. During a tool-deciding
      round these are typically empty/rare (the round is mostly tool-call metadata, not visible
      text); the model's final answer is where real streamed content appears.
    - `status` right before each tool call executes, so a client can show "Checking your
      shipment..." instead of a silent gap during a tool round.
    - `done` once, with the exact same result dict `run_assistant` returns -- a client that only
      wants the final answer can ignore every other event and read this one.
    - `error` instead of raising: once the SSE response has started, HTTP status can no longer
      change, so a mid-turn failure has to be communicated as an event, not an exception.

    Each round accumulates `AIMessageChunk`s from `llm.astream(...)` via LangChain's own `+`
    merge (the same object `run_assistant`'s `ainvoke` would have returned, built incrementally
    instead of all at once) -- so tool-call decisions, `ux_state` transitions, and content
    fallbacks all go through the exact same `_execute_tool_round`/`_finalize_content` this
    module's blocking path uses. Nothing about *what* the turn decides differs; only *how the
    content arrives* differs.
    """
    try:
        prepared = await _prepare_turn(
            session=session, ctx=ctx, settings=settings, message=message, thread_id=thread_id,
            session_id=session_id, client_message_id=client_message_id,
        )
    except AppError as exc:
        yield {"event": "error", "data": {"code": exc.code, "message": exc.message, "status_code": exc.status_code}}
        return

    if isinstance(prepared, dict):
        yield {"event": "start", "data": {"thread_id": prepared["thread_id"], "session_id": prepared["session_id"]}}
        yield {"event": "done", "data": prepared}
        return

    yield {"event": "start", "data": {"thread_id": prepared.tid, "session_id": prepared.sid}}
    # E4.4 (issue #34): a per-round check, not `asyncio.wait_for` (which can't wrap an async
    # generator's overall iteration the way it wraps a single coroutine in `run_assistant`).
    # Combined with `llm_call_timeout_seconds` bounding every individual call, this still gives
    # the streamed turn a real wall-clock ceiling -- checked between rounds so it never cuts off
    # content already in flight.
    deadline = time.monotonic() + settings.turn_deadline_seconds

    state = TurnState()
    invoke_config = child_invoke_config(prepared.turn_config)

    with chat_turn_trace(
        prepared.turn_config,
        inputs={"message": message, "thread_id": prepared.tid, "session_id": prepared.sid},
    ) as run:
        try:
            ai, deltas = await _stream_llm_call(
                prepared.llm, prepared.messages, invoke_config, prepared.turn, prepared.llm_provider,
                prepared.llm_model, hop=0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM stream failed")
            yield {"event": "error", "data": {"code": "LLM_UNAVAILABLE", "message": str(exc)[:200]}}
            return
        for delta in deltas:
            yield {"event": "token", "data": {"content": delta}}

        for round_idx in range(MAX_TOOL_ROUNDS):
            if time.monotonic() > deadline:
                yield {
                    "event": "error",
                    "data": {"code": "TURN_DEADLINE_EXCEEDED", "message": "The assistant did not respond in time."},
                }
                return
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                break
            prepared.messages.append(ai)
            prepared.turn.note_hop()

            for call in tool_calls:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                yield {"event": "status", "data": {"tool": name}}

            tool_messages, should_break_after_round = await _execute_tool_round(
                session=session, tool_calls=tool_calls, tool_map=prepared.tool_map,
                invoke_config=invoke_config, state=state, turn=prepared.turn,
            )
            prepared.messages.extend(tool_messages)

            if should_break_after_round:
                break

            try:
                invoke_config = child_invoke_config(
                    prepared.turn_config,
                    extra_metadata=tool_outcome_metadata(state.observed_tools, state.ux_state),
                )
                ai, deltas = await _stream_llm_call(
                    prepared.llm, prepared.messages, invoke_config, prepared.turn, prepared.llm_provider,
                    prepared.llm_model, hop=round_idx + 1,
                )
                for delta in deltas:
                    yield {"event": "token", "data": {"content": delta}}
            except Exception as exc:  # noqa: BLE001
                yield {"event": "error", "data": {"code": "LLM_UNAVAILABLE", "message": str(exc)[:200]}}
                return

        content = _finalize_content(ai, state)
        result = await _persist_and_build_result(
            prepared=prepared, ctx=ctx, message=message, client_message_id=client_message_id,
            state=state, content=content, run=run,
        )
        yield {"event": "done", "data": result}


async def _stream_llm_call(
    llm: Any, messages: list[Any], invoke_config: Any, turn: TurnLatency, provider: str, model: str, *, hop: int,
) -> tuple[AIMessage, list[str]]:
    """`llm.astream(...)`, accumulated into one final message via LangChain's own `AIMessageChunk`
    `+` merge -- the same object shape `ainvoke` returns, built incrementally. Returns the
    accumulated message and the list of non-empty content deltas observed, in arrival order, so
    the caller can forward them as `token` events immediately rather than after the fact (the
    accumulation itself cannot be streamed to the client -- only the deltas that produced it can).
    """
    llm_started = time.perf_counter()
    accumulated: Any = None
    deltas: list[str] = []
    async for chunk in llm.astream(messages, config=invoke_config):
        accumulated = chunk if accumulated is None else accumulated + chunk
        # `_extract_text`, not a bare `isinstance(..., str)` check: see its own docstring (E4.1,
        # issue #31) -- a content-blocks chunk would otherwise silently stream as empty tokens.
        piece = _extract_text(chunk.content)
        if piece:
            deltas.append(piece)
    turn.record_llm(
        duration_ms=elapsed_ms(llm_started), provider=provider, model=model, hop=hop,
        usage=getattr(accumulated, "usage_metadata", None),
    )
    if accumulated is None:
        raise AppError("LLM returned no output.", code="LLM_UNAVAILABLE", status_code=503)
    return accumulated, deltas
